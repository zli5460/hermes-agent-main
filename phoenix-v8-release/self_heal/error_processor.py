"""
不死鸟 Phoenix V8 — 错误处理10步法
V4.7: 4步法（验证→重试→替代→报告）来源: Manus
V4.6: 升级为10步排查法，来源: 主控Agent投喂手册V7

10步排查法口诀：
1. 剥离情绪  → 描述问题，不加主观判断
2. 定真问题  → 区分"表象"和"根因"
3. 判类型    → 配置/代码/网络/权限/数据问题
4. 圈边界    → 问题影响范围
5. 拆细碎    → 拆成最小可验证单元
6. 找根因    → 逐一排查，用命令验证
7. 选方案    → 列出≥2个方案，标注风险
8. 控风险    → 破坏性操作前备份
9. 明权责    → P0/P1/P2判定
10. 常固化   → 根因和方案写入记忆防复发
"""

import time
import re
from typing import Optional, Dict, Any, List

# 错误类型分类
ERROR_TYPES = {
    "config": ["配置", "config", "yaml", "json", "env", "环境变量", "setting"],
    "code": ["代码", "code", "syntax", "import", "undefined", "null", "type error", "attribute"],
    "network": ["网络", "network", "timeout", "connection", "dns", "proxy", "404", "502", "503"],
    "permission": ["权限", "permission", "denied", "forbidden", "403", "unauthorized", "401"],
    "data": ["数据", "data", "empty", "null", "missing", "corrupt", "format"],
}

# P0/P1/P2 权限级别
PERMISSION_LEVELS = {
    "P0": "必须请示 — 删除文件、修改SOUL.md、系统配置、付费API、无法回滚的操作",
    "P1": "需要备案 — 修改记忆文件、创建文件、修改配置、调用API",
    "P2": "自主执行 — 读取文件、查询命令、生成报告、发送消息",
}


class ErrorProcessor:
    """错误处理10步法（V4.6升级）"""

    def __init__(self, antibody_library=None, circuit_breaker=None):
        self._antibody = antibody_library
        self._circuit = circuit_breaker
        self._retry_count = 0
        self._max_retries = 3
    
    def process_error(self, error: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        10步错误处理（兼容旧4步API）
        
        Returns:
            {"steps": [...], "handled": bool, "action": str, "diagnosis": dict}
        """
        context = context or {}
        result = {"steps": [], "handled": False, "action": None, "diagnosis": {}}
        
        # ===== 前置阶段：10步排查 =====
        diagnosis = self.diagnose(error, context)
        result["diagnosis"] = diagnosis
        
        # ===== 执行阶段：基于诊断结果处理 =====
        
        # Step 6-7: 找根因 + 选方案（已由diagnose完成）
        result["steps"].append({
            "step": "6-7", "name": "根因分析+方案选择",
            "root_cause": diagnosis["root_cause"],
            "error_type": diagnosis["error_type"],
            "solutions": diagnosis["solutions"],
        })
        
        # Step 8: 控风险
        risk_level = diagnosis.get("permission_level", "P2")
        result["steps"].append({
            "step": 8, "name": "风险控制",
            "permission_level": risk_level,
            "needs_backup": risk_level in ("P0", "P1"),
        })
        
        # Step 9: 明权责
        if risk_level == "P0":
            result["handled"] = False
            result["action"] = "need_user_approval"
            result["steps"].append({
                "step": 9, "name": "权限判定",
                "level": "P0", "action": "必须请示用户"
            })
            return result
        
        # Step 2-3: 尝试修复（兼容旧逻辑）
        step2 = self._step2_retry(error, context)
        result["steps"].append(step2)
        if step2["fixed"]:
            result["handled"] = True
            result["action"] = "retry_fix"
            return result
        
        # Step 3: 替代方案
        step3 = self._step3_alternative(error, context)
        result["steps"].append(step3)
        if step3.get("alternatives"):
            result["handled"] = True
            result["action"] = "alternative_fix"
            return result
        
        # Step 4: 报告 + 生成抗体
        step4 = self._step4_report(error, context)
        result["steps"].append(step4)
        result["handled"] = False
        result["action"] = "report_and_antibody"
        
        return result

    def diagnose(self, error: str, context: Dict = None) -> Dict:
        """
        10步排查法完整诊断（可独立调用）
        
        Returns:
            {"error_type": str, "root_cause": str, "solutions": list, 
             "permission_level": str, "scope": str}
        """
        context = context or {}
        
        # Step 1: 剥离情绪 — 纯描述问题
        clean_error = self._strip_emotion(error)
        
        # Step 2: 定真问题 — 区分表象和根因
        root_cause = self._find_root_cause(clean_error, context)
        
        # Step 3: 判类型
        error_type = self._classify_error(clean_error)
        
        # Step 4: 圈边界
        scope = self._assess_scope(clean_error, context)
        
        # Step 5: 拆细碎
        sub_issues = self._split_issues(clean_error)
        
        # Step 7: 选方案
        solutions = self._select_solutions(error_type, root_cause, context)
        
        # Step 9: 明权责
        permission_level = self._determine_permission(error_type, solutions)
        
        # Step 10: 常固化（标记需要记录）
        needs_recording = True
        
        return {
            "clean_error": clean_error,
            "root_cause": root_cause,
            "error_type": error_type,
            "scope": scope,
            "sub_issues": sub_issues,
            "solutions": solutions,
            "permission_level": permission_level,
            "needs_recording": needs_recording,
        }

    # ===== 10步排查法各步骤实现 =====

    def _strip_emotion(self, error: str) -> str:
        """Step 1: 剥离情绪 — 只保留事实描述"""
        # 移除主观判断词
        emotional_words = ["好像", "可能", "也许", "感觉", "糟糕", "坏了", "完蛋", "怎么办"]
        clean = error
        for word in emotional_words:
            clean = clean.replace(word, "")
        return clean.strip()

    def _find_root_cause(self, error: str, context: Dict) -> str:
        """Step 2: 定真问题 — 区分表象和根因"""
        error_lower = error.lower()
        
        # 常见表象→根因映射
        mappings = [
            ("connection refused", "服务未启动或端口被占用"),
            ("connection reset", "网络中断或服务端关闭连接"),
            ("timeout", "请求超时，可能是网络慢或服务端处理时间过长"),
            ("404", "资源不存在，检查URL或文件路径"),
            ("403", "权限不足，检查认证信息"),
            ("401", "未认证，检查API Key或Token"),
            ("500", "服务端内部错误"),
            ("no module named", "Python模块未安装"),
            ("command not found", "命令未安装或不在PATH中"),
            ("permission denied", "文件权限不足"),
            ("file not found", "文件不存在，检查路径"),
        ]
        
        for pattern, cause in mappings:
            if pattern in error_lower:
                return cause
        
        return f"需要进一步排查: {error[:80]}"

    def _classify_error(self, error: str) -> str:
        """Step 3: 判类型"""
        error_lower = error.lower()
        scores = {}
        for etype, keywords in ERROR_TYPES.items():
            scores[etype] = sum(1 for kw in keywords if kw in error_lower)
        
        if max(scores.values()) > 0:
            return max(scores, key=scores.get)
        return "unknown"

    def _assess_scope(self, error: str, context: Dict) -> str:
        """Step 4: 圈边界"""
        if context.get("is_system_wide"):
            return "系统级 — 影响整个服务"
        if context.get("is_single_task"):
            return "任务级 — 仅影响当前任务"
        if any(w in error.lower() for w in ["gateway", "daemon", "service"]):
            return "服务级 — 影响后台服务"
        return "任务级 — 仅影响当前任务"

    def _split_issues(self, error: str) -> List[str]:
        """Step 5: 拆细碎"""
        # 按换行或分号拆分多个错误
        issues = re.split(r'[\n;]+', error)
        return [i.strip() for i in issues if i.strip() and len(i.strip()) > 5]

    def _select_solutions(self, error_type: str, root_cause: str, context: Dict) -> List[Dict]:
        """Step 7: 选方案"""
        solutions = []
        
        if error_type == "network":
            solutions.append({"方案": "检查网络连接和代理设置", "风险": "低", "优先级": 1})
            solutions.append({"方案": "切换备用节点或使用代理", "风险": "低", "优先级": 2})
        
        elif error_type == "permission":
            solutions.append({"方案": "检查并更新认证信息", "风险": "低", "优先级": 1})
            solutions.append({"方案": "联系管理员获取权限", "风险": "无", "优先级": 2})
        
        elif error_type == "code":
            solutions.append({"方案": "检查代码语法和依赖", "风险": "低", "优先级": 1})
            solutions.append({"方案": "回滚到上一个正常版本", "风险": "中", "优先级": 2})
        
        elif error_type == "config":
            solutions.append({"方案": "检查配置文件格式和值", "风险": "低", "优先级": 1})
            solutions.append({"方案": "恢复默认配置", "风险": "中", "优先级": 2})
        
        elif error_type == "data":
            solutions.append({"方案": "检查数据格式和完整性", "风险": "低", "优先级": 1})
            solutions.append({"方案": "从备份恢复数据", "风险": "中", "优先级": 2})
        
        else:
            solutions.append({"方案": "收集更多信息后重新诊断", "风险": "无", "优先级": 1})
            solutions.append({"方案": "向用户求助并附上完整错误信息", "风险": "无", "优先级": 2})
        
        return solutions

    def _determine_permission(self, error_type: str, solutions: List[Dict]) -> str:
        """Step 9: 明权责"""
        high_risk = any(s.get("风险") in ("高", "中") for s in solutions)
        if error_type == "permission" or high_risk:
            return "P1"
        return "P2"

    # ===== 兼容旧4步法的内部方法 =====

    def _step2_retry(self, error: str, context: Dict) -> Dict:
        """Step 2: 尝试修复（重试/修正参数）"""
        retryable = any(w in error.lower() for w in [
            "timeout", "timed out", "rate limit", "429", "503",
            "connection", "network", "temporary",
        ])

        if not retryable:
            return {"step": 2, "name": "尝试修复", "retryable": False, "fixed": False}

        retry_fn = context.get("retry_fn")
        if retry_fn and callable(retry_fn) and self._retry_count < self._max_retries:
            self._retry_count += 1
            try:
                wait_time = min(2 ** self._retry_count, 10)
                time.sleep(wait_time)
                result = retry_fn()
                self._retry_count = 0
                return {"step": 2, "name": "尝试修复", "retryable": True, "fixed": True, "result": result}
            except Exception as e:
                return {"step": 2, "name": "尝试修复", "retryable": True, "fixed": False, "retry_error": str(e)}

        return {"step": 2, "name": "尝试修复", "retryable": True, "fixed": False}
    
    def _step3_alternative(self, error: str, context: Dict) -> Dict:
        """Step 3: 尝试替代方案"""
        model = context.get("model", "")
        alternatives = {
            "mimo-v2.5": ["gpt-5.4-mini", "claude-haiku-4.5"],
            "claude-opus-4.7": ["gpt-5.5", "gemini-2.5-pro"],
        }
        alt_models = alternatives.get(model, [])
        return {"step": 3, "name": "替代方案", "alternatives": alt_models, "fixed": len(alt_models) > 0}
    
    def _step4_report(self, error: str, context: Dict) -> Dict:
        """Step 4: 报告失败，生成新抗体"""
        if self._antibody:
            antibody = self._antibody.generate(
                trigger=error, trigger_type="error",
                action="fallback_to_alternative",
                description=f"自动处理: {error[:50]}"
            )
            return {"step": 4, "name": "报告并生成抗体", "antibody_id": antibody.id if antibody else None, "fixed": False}
        return {"step": 4, "name": "报告失败", "fixed": False}
