"""
Phoenix V8 复杂度评估器（ComplexityAssessor）
规则驱动，<5ms，判断任务是否需要分解
"""

import re
from dataclasses import dataclass


@dataclass
class ComplexityAssessment:
    """复杂度评估结果"""
    needs_planning: bool  # 是否需要分解
    complexity_score: float  # 0-1 复杂度分数
    reason: str  # 评估原因
    signals: dict  # 各维度信号


class ComplexityAssessor:
    """复杂度评估器（纯规则，<5ms）"""
    
    def _is_simple_task(self, message: str) -> bool:
        """快速判断是否是简单任务（V4.7 精确版）"""
        msg = message.strip()

        # 算术题（精确匹配：包含"等于"或纯数字运算）
        if re.match(r"^\s*\d+\s*[+\-*/]\s*\d+\s*(?:等于|=)?\s*$", msg):
            return True
        # 多个算术题也算简单（"算一下 3+5 和 2+4"）
        if re.match(r"^(?:算|计算).*\d+\s*[+\-*/]\s*\d+", msg):
            return True

        # 简单问候
        if len(msg) < 10 and any(kw in msg for kw in ["你好", "在吗", "好的", "谢谢", "嗯", "哦"]):
            return True

        # 记忆指令
        if re.match(r"^(我叫|记住|帮我记)", msg):
            return True

        return False
    
    # 分解触发词（强信号）- V4.7 精确版
    DECOMPOSE_STRONG = [
        r"(?<!\d)\+(?!\d)(?!.*等于)",  # + 但不是算术题
        r"(?<!\w)和(?!\w)(?!.*(?:都|也|很|不错|好))",  # "和" 但不是"天气和心情都不错"
        r"以及",
        r"分别",
        r"同时",
    ]
    
    # 分解触发词（弱信号）
    DECOMPOSE_WEAK = [
        r"然后",
        r"接着",
        r"之后",
    ]
    
    def assess(self, message: str) -> ComplexityAssessment:
        """
        评估任务复杂度
        
        Returns:
            ComplexityAssessment
        """
        # 快速排除：简单任务不需要分解
        if self._is_simple_task(message):
            return ComplexityAssessment(
                needs_planning=False,
                complexity_score=0.0,
                reason="简单任务",
                signals={},
            )
        
        signals = {}
        
        # 信号1：包含分解触发词
        strong_triggers = sum(1 for p in self.DECOMPOSE_STRONG if re.search(p, message))
        weak_triggers = sum(1 for p in self.DECOMPOSE_WEAK if re.search(p, message))
        signals["strong_triggers"] = strong_triggers
        signals["weak_triggers"] = weak_triggers
        
        # 信号2：消息长度（长消息通常更复杂）
        signals["message_length"] = len(message)
        
        # 信号3：涉及的主题数量
        topics = self._count_topics(message)
        signals["topic_count"] = topics
        
        # 计算复杂度分数
        score = 0.0
        score += strong_triggers * 0.3  # 强触发词
        score += weak_triggers * 0.1   # 弱触发词
        score += min(topics * 0.2, 0.6)  # 主题数（上限0.6）
        score += min(len(message) / 1000, 0.2)  # 长度（上限0.2）
        
        # 判断是否需要分解
        needs_planning = score >= 0.5 or strong_triggers >= 2
        
        # 生成原因
        if needs_planning:
            reasons = []
            if strong_triggers >= 2:
                reasons.append(f"包含{strong_triggers}个分解触发词")
            if topics >= 3:
                reasons.append(f"涉及{topics}个独立主题")
            if len(message) > 200:
                reasons.append("消息较长，可能包含多个子任务")
            reason = "；".join(reasons) if reasons else "复杂度评分达标"
        else:
            reason = "任务简单，不需要分解"
        
        return ComplexityAssessment(
            needs_planning=needs_planning,
            complexity_score=min(score, 1.0),
            reason=reason,
            signals=signals,
        )
    
    def _count_topics(self, message: str) -> int:
        """估算涉及的主题数量"""
        # 简单启发式：按分隔符分割
        parts = re.split(r'[+和以及、，]', message)
        # 过滤掉太短的部分
        meaningful_parts = [p.strip() for p in parts if p.strip() and len(p.strip()) > 3]
        return len(meaningful_parts)
