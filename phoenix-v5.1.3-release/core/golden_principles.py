"""不死鸟 Phoenix V5.1 — Golden Principles（品味编码 + 防幻觉）
来源: OpenAI Harness Engineering + Andrej Karpathy + 主控Agent投喂手册V7

V4.6升级：新增7种幻觉检测 + 三轮自验证 + enforcement机制
"""

from typing import List, Dict

class GoldenPrinciples:
    """品味编码原则库 + 防幻觉检测"""
    
    PRINCIPLES = [
        # === Karpathy 4条准则 ===
        {
            "id": "think_before_coding",
            "name": "先想后做（Karpathy）",
            "rule": "不要假设，不要隐藏困惑，展示权衡",
            "source": "Andrej Karpathy",
            "examples": [
                "明确陈述假设，不确定就问",
                "有多种解释时全部呈现",
                "有更简单的方式直接说",
                "困惑时停止，说出困惑点",
            ],
        },
        {
            "id": "simplicity_first",
            "name": "简洁优先（Karpathy）",
            "rule": "只写解决问题的最少代码，不要预设",
            "source": "Andrej Karpathy",
            "examples": [
                "没有超出需求范围的功能",
                "不要为单一用途写抽象",
                "不要加入没被要求的灵活性",
                "200行能简化到50行就重写",
            ],
        },
        {
            "id": "surgical_changes",
            "name": "手术式改动（Karpathy）",
            "rule": "只改必须改的，只清理自己的烂摊子",
            "source": "Andrej Karpathy",
            "examples": [
                "不要改进相邻代码/注释/格式",
                "不要重构没坏的东西",
                "匹配现有风格",
                "发现不相关死代码提出来但不删",
            ],
        },
        {
            "id": "goal_driven",
            "name": "目标驱动（Karpathy）",
            "rule": "定义成功标准，循环直到验证",
            "source": "Andrej Karpathy",
            "examples": [
                "Add validation → 写测试让它们通过",
                "Fix bug → 写复现测试让它通过",
                "多步骤任务陈述简要计划",
                "强成功标准让AI独立循环",
            ],
        },
        # === OpenAI Harness 准则 ===
        {
            "id": "verify",
            "name": "验证优先",
            "rule": "必须验证数据边界 > YOLO式猜测",
            "examples": [
                "输入输出都要检查",
                "边界条件必须覆盖",
                "失败要优雅降级",
            ],
        },
        {
            "id": "feedback",
            "name": "反馈闭环",
            "rule": "每次执行都要有反馈",
            "examples": [
                "成功要记录，失败要分析",
                "模型表现要追踪",
                "抗体要持续更新",
            ],
        },
        {
            "id": "autonomy",
            "name": "自主性",
            "rule": "能自己解决的不问用户",
            "examples": [
                "错误自动重试/降级",
                "重复问题自动缓存",
                "记忆自动提取和同步",
            ],
        },
        {
            "id": "transparency",
            "name": "透明性",
            "rule": "内部决策要有日志",
            "examples": [
                "路由选择要记录原因",
                "错误处理要记录步骤",
                "进化过程要可追溯",
            ],
        },
        {
            "id": "efficiency",
            "name": "效率优先",
            "rule": "省token、省时间、省资源",
            "examples": [
                "正则分类零成本",
                "缓存命中不调API",
                "微压缩减少传输",
            ],
        },
        {
            "id": "safety",
            "name": "安全第一",
            "rule": "危险操作必须确认",
            "examples": [
                "删除文件要用户确认",
                "API key不能明文输出",
                "预算超限要告警",
            ],
        },
        # === V4.6 新增：7种幻觉检测（来源：主控Agent投喂手册V7） ===
        {
            "id": "hallucination_fabrication",
            "name": "事实捏造检测",
            "rule": "声称做了某件事但实际未执行 — 最常见的幻觉",
            "source": "主控Agent投喂手册V7",
            "severity": "critical",
            "examples": [
                "声称文件已写入但未验证",
                "声称命令已执行但无输出",
                "声称修复了bug但未测试",
            ],
        },
        {
            "id": "hallucination_path",
            "name": "路径幻觉检测",
            "rule": "引用不存在的文件路径或命令",
            "source": "主控Agent投喂手册V7",
            "severity": "critical",
            "examples": [
                "引用/tmp下已被清理的文件",
                "使用不存在的CLI命令",
                "硬编码路径但实际不存在",
            ],
        },
        {
            "id": "hallucination_capability",
            "name": "能力幻觉检测",
            "rule": "声称具备某项能力但实际无法执行",
            "source": "主控Agent投喂手册V7",
            "severity": "high",
            "examples": [
                "声称能生成图片但没有生图API",
                "声称能访问某网站但被墙",
                "声称能调用某模型但没有key",
            ],
        },
        {
            "id": "hallucination_memory",
            "name": "记忆幻觉检测",
            "rule": "声称记得之前的对话内容但跨会话实际无记忆",
            "source": "主控Agent投喂手册V7",
            "severity": "high",
            "examples": [
                '说"上次我们讨论过"但实际没查session',
                '说"我记得你之前说过"但没有证据',
                "混淆不同会话的内容",
            ],
        },
        {
            "id": "hallucination_status",
            "name": "状态幻觉检测",
            "rule": "声称某个服务/任务正在运行但未验证",
            "source": "主控Agent投喂手册V7",
            "severity": "high",
            "examples": [
                '说"Gateway正在运行"但没检查进程',
                '说"测试通过了"但没看输出',
                '说"部署成功了"但没验证',
            ],
        },
        {
            "id": "hallucination_number",
            "name": "数字幻觉检测",
            "rule": "凭空给出统计数据、版本号、时间戳",
            "source": "主控Agent投喂手册V7",
            "severity": "medium",
            "examples": [
                "编造不存在的版本号",
                "凭空给出性能数据",
                "猜测时间戳而非查询",
            ],
        },
        {
            "id": "hallucination_logic",
            "name": "逻辑幻觉检测",
            "rule": "结论与前提不符但表述得很自信",
            "source": "主控Agent投喂手册V7",
            "severity": "medium",
            "examples": [
                "数据显示A但结论是B",
                '前提说"部分完成"但结论说"全部完成"',
                "忽略了明显的矛盾",
            ],
        },
    ]
    
    # V4.6: 幻觉严重级别映射
    HALLUCINATION_SEVERITY = {
        "critical": "必须立即停止并修正",
        "high": "需要验证后才能继续",
        "medium": "记录并提醒",
    }

    def check(self, action: str, context: Dict = None) -> List[Dict]:
        """检查操作是否符合原则"""
        context = context or {}
        violations = []
        for principle in self.PRINCIPLES:
            if self._violates(action, context, principle):
                violations.append(principle)
        return violations

    def check_hallucination(self, output: str, context: Dict = None) -> List[Dict]:
        """V4.6: 检测输出中的幻觉 — 三轮自验证"""
        context = context or {}
        detected = []
        for principle in self.PRINCIPLES:
            if not principle["id"].startswith("hallucination_"):
                continue
            if self._detect_hallucination(output, context, principle):
                detected.append({
                    "type": principle["id"],
                    "name": principle["name"],
                    "severity": principle.get("severity", "medium"),
                    "rule": principle["rule"],
                })
        return detected

    def _detect_hallucination(self, output: str, context: Dict, principle: Dict) -> bool:
        """检测具体幻觉类型"""
        pid = principle["id"]
        out = output.lower()

        if pid == "hallucination_fabrication":
            # 声称完成但无验证证据
            claims_done = any(w in out for w in ["已完成", "搞定了", "成功了", "写入了", "修复了"])
            has_evidence = context.get("has_command_output") or context.get("verified")
            return claims_done and not has_evidence

        if pid == "hallucination_path":
            # 引用路径但未验证存在
            import re
            paths = re.findall(r'[/\\][\w./\\-]+', output)
            for path in paths:
                if not context.get(f"path_exists:{path}", True):
                    return True
            return False

        if pid == "hallucination_capability":
            # 声称能力但上下文表明不可用
            capability_claims = ["我可以", "我能", "支持", "具备"]
            if any(c in out for c in capability_claims):
                if context.get("capability_unavailable"):
                    return True
            return False

        if pid == "hallucination_memory":
            # 声称记得之前的内容
            memory_claims = ["上次", "之前", "记得", "以前", "之前讨论过"]
            if any(m in out for m in memory_claims):
                if not context.get("session_searched"):
                    return True
            return False

        if pid == "hallucination_status":
            # 声称状态但未验证
            status_claims = ["正在运行", "已启动", "正常", "在线"]
            if any(s in out for s in status_claims):
                if not context.get("status_verified"):
                    return True
            return False

        if pid == "hallucination_number":
            # 编造数字
            import re
            numbers = re.findall(r'\d+\.?\d*%?', output)
            if numbers and context.get("numbers_unverified"):
                return True
            return False

        if pid == "hallucination_logic":
            # 结论与前提矛盾
            if context.get("logic_contradiction"):
                return True
            return False

        return False

    def _violates(self, action: str, context: Dict, principle: Dict) -> bool:
        """检查是否违反原则 — 逐条实现"""
        action_lower = action.lower()
        pid = principle["id"]

        if pid == "safety":
            dangerous = ("delete", "rm ", "drop ", "truncate", "format", "kill -9")
            if any(d in action_lower for d in dangerous):
                return not context.get("confirmed", False)
            return False

        if pid == "verify":
            if context.get("has_input") and not context.get("validated", False):
                return True
            return False

        if pid == "feedback":
            if context.get("executed") and not context.get("recorded", False):
                return True
            return False

        if pid == "autonomy":
            error = (context.get("error") or "").lower()
            if error and any(e in error for e in ("timeout", "rate limit", "429")):
                if context.get("asks_user", False):
                    return True
            return False

        if pid == "transparency":
            if context.get("is_decision") and not context.get("logged", False):
                return True
            return False

        if pid == "efficiency":
            if context.get("is_repeat_call") and not context.get("cache_checked", False):
                return True
            return False

        if pid == "think_before_coding":
            if context.get("has_ambiguity") and not context.get("clarified", False):
                return True
            return False

        if pid == "simplicity_first":
            loc = context.get("lines_of_code", 0)
            req = context.get("required_loc", 0)
            if req and loc > req * 3:
                return True
            return False

        if pid == "surgical_changes":
            if context.get("unrelated_changes", 0) > 0:
                return True
            return False

        if pid == "goal_driven":
            if context.get("is_task_start") and not context.get("success_criteria"):
                return True
            return False

        return False

    # ===== V4.6: Enforcement 执行时强制检查 =====
    
    def enforce(self, action: str, context: Dict = None) -> Dict:
        """
        V4.6: 执行时强制检查 — 不是声明式规则，而是执行时拦截
        
        Returns:
            {"allowed": bool, "violations": list, "hallucinations": list, "action_required": str}
        """
        context = context or {}
        violations = self.check(action, context)
        hallucinations = self.check_hallucination(action, context)
        
        # critical级别幻觉直接拦截
        critical = [h for h in hallucinations if h.get("severity") == "critical"]
        if critical:
            return {
                "allowed": False,
                "violations": violations,
                "hallucinations": hallucinations,
                "action_required": f"检测到critical级幻觉: {critical[0]['name']} — 必须提供可验证证据",
            }
        
        # safety违反直接拦截
        safety_violations = [v for v in violations if v["id"] == "safety"]
        if safety_violations:
            return {
                "allowed": False,
                "violations": violations,
                "hallucinations": hallucinations,
                "action_required": "安全原则违反 — 需要用户确认",
            }
        
        # 其他违规记录但不拦截
        return {
            "allowed": True,
            "violations": violations,
            "hallucinations": hallucinations,
            "action_required": None,
        }

    def get_all(self) -> List[Dict]:
        """获取所有原则"""
        return self.PRINCIPLES

principles = GoldenPrinciples()
