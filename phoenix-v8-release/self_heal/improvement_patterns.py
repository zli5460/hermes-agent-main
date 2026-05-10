"""
Phoenix V8+ — 改进模式库

借鉴 self-evolution 项目，为Phoenix添加：
1. 结构化改进模板 — 标准化的改进流程
2. 模式识别 — 从历史中提取改进模式
3. 最佳实践固化 — 成功经验自动沉淀

从"出错→修"升级到"出错→分析→模板→预防"。
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


@dataclass
class ImprovementPattern:
    """改进模式"""
    id: str
    name: str
    category: str           # "performance" / "reliability" / "cost" / "security"
    trigger: str            # 触发条件描述
    steps: List[str]        # 改进步骤
    success_rate: float = 0  # 历史成功率
    times_applied: int = 0
    times_succeeded: int = 0
    created_at: float = 0
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "trigger": self.trigger,
            "steps": self.steps,
            "success_rate": self.success_rate,
            "times_applied": self.times_applied,
            "times_succeeded": self.times_succeeded,
        }


class ImprovementPatterns:
    """
    改进模式库
    
    核心能力：
    1. 内置标准改进模板
    2. 从错误中自动学习新模式
    3. 追踪每个模式的成功率
    4. 成功模式自动沉淀为最佳实践
    """
    
    def __init__(self, data_dir: Optional[str] = None):
        self._data_dir = Path(data_dir or Path.home() / ".hermes/phoenix/data")
        self._data_dir.mkdir(parents=True, exist_ok=True)
        
        # 内置模式
        self._patterns: Dict[str, ImprovementPattern] = {}
        self._load_patterns()
        self._init_builtin_patterns()
    
    def _init_builtin_patterns(self) -> None:
        """初始化内置改进模式"""
        builtins = [
            ImprovementPattern(
                id="perf_api_timeout",
                name="API超时优化",
                category="performance",
                trigger="API调用超时（timeout）",
                steps=[
                    "检查网络连通性（ping/curl测试）",
                    "检查目标端点是否正常（健康检查）",
                    "尝试备用端点（fallback provider）",
                    "调整超时参数（从30s→60s→120s逐步增加）",
                    "如果持续超时，切换到本地模型",
                ],
            ),
            ImprovementPattern(
                id="perf_rate_limit",
                name="限流处理",
                category="performance",
                trigger="API返回429（rate limit）",
                steps=[
                    "识别限流的Provider",
                    "计算等待时间（根据Retry-After头）",
                    "等待后重试",
                    "如果频繁限流，降低请求频率",
                    "考虑升级API套餐或切换Provider",
                ],
            ),
            ImprovementPattern(
                id="rel_error_spike",
                name="错误激增处理",
                category="reliability",
                trigger="5分钟内同一错误出现5次以上",
                steps=[
                    "暂停当前任务",
                    "分析错误模式（是否同一根因）",
                    "检查API状态页面",
                    "切换到备用模型/Provider",
                    "通知用户当前状况",
                    "等恢复后自动切回",
                ],
            ),
            ImprovementPattern(
                id="cost_optimization",
                name="成本优化",
                category="cost",
                trigger="小时成本超过预算阈值",
                steps=[
                    "分析成本来源（哪个模型/任务消耗最多）",
                    "检查是否有不必要的重复调用",
                    "将非关键任务降级到更便宜的模型",
                    "启用响应缓存（避免重复查询）",
                    "设置更严格的预算告警",
                ],
            ),
            ImprovementPattern(
                id="sec_key_leak",
                name="密钥泄露处理",
                category="security",
                trigger="检测到疑似密钥泄露",
                steps=[
                    "立即停止相关操作",
                    "确认泄露范围（哪些日志/文件包含密钥）",
                    "清理泄露的密钥",
                    "轮换密钥（生成新的）",
                    "更新所有引用该密钥的配置",
                    "记录事件并告警",
                ],
            ),
            ImprovementPattern(
                id="perf_memory_usage",
                name="内存优化",
                category="performance",
                trigger="内存使用超过80%",
                steps=[
                    "触发垃圾回收",
                    "清理过期的缓存数据",
                    "压缩大文件（如日志）",
                    "减少并发任务数",
                    "如果持续高占用，重启服务",
                ],
            ),
        ]
        
        for pattern in builtins:
            if pattern.id not in self._patterns:
                pattern.created_at = time.time()
                self._patterns[pattern.id] = pattern
        
        self._save_patterns()
    
    def _load_patterns(self) -> None:
        """加载已保存的模式"""
        patterns_file = self._data_dir / "improvement_patterns.json"
        if patterns_file.exists():
            try:
                data = json.loads(patterns_file.read_text())
                for d in data.get("patterns", []):
                    valid_fields = {k: v for k, v in d.items()
                                   if k in ImprovementPattern.__dataclass_fields__}
                    p = ImprovementPattern(**valid_fields)
                    self._patterns[p.id] = p
            except (json.JSONDecodeError, OSError, TypeError, KeyError):
                pass
    
    def _save_patterns(self) -> None:
        """保存模式"""
        patterns_file = self._data_dir / "improvement_patterns.json"
        patterns_file.write_text(json.dumps({
            "patterns": [p.to_dict() for p in self._patterns.values()],
            "last_updated": time.time(),
        }, indent=2, ensure_ascii=False))
    
    def match_pattern(self, error_message: str) -> Optional[ImprovementPattern]:
        """
        根据错误信息匹配改进模式
        
        返回最匹配的模式（如果有的话）
        """
        error_lower = error_message.lower()
        
        # 关键词匹配
        keyword_map = {
            "perf_api_timeout": ["timeout", "timed out", "超时", "连接超时"],
            "perf_rate_limit": ["429", "rate limit", "too many requests", "限流"],
            "rel_error_spike": ["500", "502", "503", "internal server error"],
            "cost_optimization": ["budget", "预算", "cost", "成本", "额度"],
            "sec_key_leak": ["api_key", "secret", "token", "密钥", "泄露"],
            "perf_memory_usage": ["memory", "内存", "oom", "out of memory"],
        }
        
        best_match = None
        best_score = 0
        
        for pattern_id, keywords in keyword_map.items():
            score = sum(1 for kw in keywords if kw in error_lower)
            if score > best_score:
                best_score = score
                best_match = self._patterns.get(pattern_id)
        
        return best_match if best_match and best_score > 0 else None
    
    def record_application(self, pattern_id: str, success: bool) -> None:
        """记录模式的应用结果"""
        if pattern_id in self._patterns:
            p = self._patterns[pattern_id]
            p.times_applied += 1
            if success:
                p.times_succeeded += 1
            p.success_rate = p.times_succeeded / max(p.times_applied, 1)
            self._save_patterns()
    
    def add_pattern(self, pattern: ImprovementPattern) -> None:
        """添加新模式（从错误中学习）"""
        pattern.created_at = time.time()
        self._patterns[pattern.id] = pattern
        self._save_patterns()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取模式库统计"""
        patterns = list(self._patterns.values())
        return {
            "total_patterns": len(patterns),
            "builtin": sum(1 for p in patterns if p.times_applied == 0),
            "learned": sum(1 for p in patterns if p.times_applied > 0),
            "avg_success_rate": f"{sum(p.success_rate for p in patterns) / max(len(patterns), 1):.0%}",
            "most_effective": max(patterns, key=lambda p: p.success_rate).name if patterns else "无",
        }
    
    def get_all_patterns(self) -> List[Dict[str, Any]]:
        """获取所有模式"""
        return [p.to_dict() for p in self._patterns.values()]
