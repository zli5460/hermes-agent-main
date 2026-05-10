"""
不死鸟 Phoenix V5.1 — 深压缩引擎

对话历史超过阈值时，自动压缩旧消息为摘要。
保证上下文不膨胀，同时不丢失关键信息。

策略：
- 保留最近N条消息（不压缩）
- 旧消息压缩成一段摘要
- 摘要注入系统prompt
"""

import re
from dataclasses import dataclass


@dataclass
class CompressResult:
    """压缩结果"""
    compressed_messages: list           # 压缩后的消息列表
    summary: str                        # 生成的摘要
    original_tokens: int                # 原始token估算
    compressed_tokens: int              # 压缩后token估算
    messages_removed: int               # 移除的消息数


class DeepCompactor:
    """
    深压缩器

    用法:
        compactor = DeepCompactor(context_threshold=4000, keep_last_n=3)
        result = compactor.compress(messages)
        # result.compressed_messages 是压缩后的对话
        # result.summary 是旧消息的摘要
    """

    def __init__(self, context_threshold_tokens: int = 4000,
                 keep_last_n: int = 3, summary_max_tokens: int = 500):
        self._threshold = context_threshold_tokens
        self._keep_last_n = keep_last_n
        self._summary_max = summary_max_tokens

    def estimate_tokens(self, text: str) -> int:
        """
        粗略估算token数（中英混合）

        英文：~4字符/token
        中文：~1.5字符/token
        """
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        other_chars = len(text) - chinese_chars
        return int(chinese_chars / 1.5 + other_chars / 4)

    def should_compress(self, messages: list) -> bool:
        """判断是否需要压缩"""
        total_text = " ".join(
            msg.get("content", "") for msg in messages
            if isinstance(msg.get("content", ""), str)
        )
        return self.estimate_tokens(total_text) > self._threshold

    def compress(self, messages: list) -> CompressResult:
        """
        压缩对话历史

        Args:
            messages: [{"role": "user/assistant", "content": "..."}, ...]

        Returns:
            CompressResult
        """
        if len(messages) <= self._keep_last_n:
            total_text = " ".join(m.get("content", "") for m in messages if isinstance(m.get("content", ""), str))
            return CompressResult(
                compressed_messages=messages,
                summary="",
                original_tokens=self.estimate_tokens(total_text),
                compressed_tokens=self.estimate_tokens(total_text),
                messages_removed=0,
            )

        # 分割：旧消息 vs 保留消息
        old_messages = messages[:-self._keep_last_n]
        keep_messages = messages[-self._keep_last_n:]
        
        # V4.6: 保护规则类消息不被压缩
        protected = [m for m in old_messages if self._is_protected(m.get("content", ""))]
        compressible = [m for m in old_messages if not self._is_protected(m.get("content", ""))]
        
        # 只压缩非保护消息
        summary = self._generate_summary(compressible) if compressible else ""

        # 组装：摘要作为system/user消息 + 受保护消息 + 保留消息
        summary_message = {
            "role": "system",
            "content": f"[历史对话摘要]\n{summary}",
        }
        
        compressed = [summary_message] + protected + keep_messages

        # 计算统计
        original_text = " ".join(m.get("content", "") for m in messages if isinstance(m.get("content", ""), str))
        compressed_text = " ".join(m.get("content", "") for m in compressed if isinstance(m.get("content", ""), str))

        return CompressResult(
            compressed_messages=compressed,
            summary=summary,
            original_tokens=self.estimate_tokens(original_text),
            compressed_tokens=self.estimate_tokens(compressed_text),
            messages_removed=len(old_messages),
        )

    def _generate_summary(self, messages: list) -> str:
        """
        生成对话摘要（规则方式，零成本）

        提取：
        - 用户的关键问题
        - AI的关键回答
        - 做出的决定
        - 提取的记忆
        """
        user_topics = []
        assistant_decisions = []
        actions_taken = []

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if not isinstance(content, str) or not content.strip():
                continue

            if role == "user":
                # 提取用户的关键点（去除短回复）
                if len(content) > 10 and not self._is_filler(content):
                    topic = content[:80]
                    if len(content) > 80:
                        topic += "..."
                    user_topics.append(topic)
            elif role == "assistant":
                # 提取助手的决策/结论
                if len(content) > 20:
                    conclusion = self._extract_conclusion(content)
                    if conclusion:
                        assistant_decisions.append(conclusion)
            elif role == "tool":
                # 工具调用结果
                if len(content) > 50:
                    actions_taken.append(f"工具调用结果({len(content)}字符)")

        # 组装摘要
        parts = []
        if user_topics:
            parts.append(f"用户关注: {'; '.join(user_topics[:5])}")
        if assistant_decisions:
            parts.append(f"关键决策: {'; '.join(assistant_decisions[:3])}")
        if actions_taken:
            parts.append(f"执行操作: {'; '.join(actions_taken[:3])}")

        summary = "\n".join(parts) if parts else "（无关键内容）"

        # 限制长度
        if len(summary) > self._summary_max * 4:
            summary = summary[:self._summary_max * 4] + "..."

        return summary

    def _is_filler(self, text: str) -> bool:
        """判断是否为废话"""
        fillers = [
            r"^(?:嗯|哦|好|是的|对|行|OK|ok|好的|可以|没问题|收到|谢谢|感谢|哈哈)$",
            r"^(?:👍|✅|🙏|😂).{0,3}$",
        ]
        for pattern in fillers:
            if re.match(pattern, text.strip(), re.IGNORECASE):
                return True
        return False

    # ===== V4.6: 规则保护 =====
    
    PROTECTED_KEYWORDS = [
        "记住", "不要忘", "以后都", "永远", "每次都要",  # 永久规则
        "不对", "不是", "记错了", "搞错了", "错了",       # 纠正规则
        "原则", "规范", "红线", "禁止", "必须",            # 行为规则
        "P0", "P1", "权限",                               # 权限规则
    ]
    
    def _is_protected(self, text: str) -> bool:
        """V4.6: 判断是否为受保护内容（规则/纠正/原则）— 不可压缩"""
        if not text:
            return False
        return any(kw in text for kw in self.PROTECTED_KEYWORDS)

    def _extract_conclusion(self, text: str) -> str:
        """从长文本中提取结论"""
        lines = text.strip().split("\n")

        # 找结论性句子
        conclusion_patterns = [
            r"(?:总结|结论|总之|所以|最终|综上|简言之)[：:](.{10,80})",
            r"(?:建议|推荐|方案是)(.{10,80})",
            r"(?:✅|✓).{5,60}",
        ]

        for line in lines:
            for pattern in conclusion_patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    return match.group(0)[:60]

        # 没找到结论 → 取最后一段非空行
        for line in reversed(lines):
            line = line.strip()
            if len(line) > 15 and not line.startswith("#"):
                return line[:60]

        return ""

    def get_compression_ratio(self, result: CompressResult) -> float:
        """获取压缩比"""
        if result.original_tokens == 0:
            return 1.0
        return result.compressed_tokens / result.original_tokens
