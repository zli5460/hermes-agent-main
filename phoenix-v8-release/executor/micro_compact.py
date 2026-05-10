"""
不死鸟 Phoenix V8 — 微压缩引擎

每次工具调用完，自动压缩结果，防止上下文膨胀。

压缩策略：
- 工具结果超过阈值 → 压缩成摘要
- 保留关键信息（数字、路径、错误信息）
- 丢弃废话（日志、重复、格式化噪音）
"""

import re
from typing import Optional


class MicroCompactor:
    """
    微压缩器

    用法:
        compactor = MicroCompactor(max_lines=5, compress_threshold=500)
        compressed = compactor.compress(tool_result)
    """

    def __init__(self, max_lines: int = 5, compress_threshold: int = 500):
        self._max_lines = max_lines
        self._compress_threshold = compress_threshold

    def compress(self, content: str, tool_name: str = "") -> str:
        """
        压缩工具结果

        Args:
            content: 工具返回的原始内容
            tool_name: 工具名称（用于针对性压缩）

        Returns:
            压缩后的内容
        """
        if not content:
            return content

        # 不够长，不压缩
        if len(content) < self._compress_threshold:
            return content

        # 按工具类型压缩
        if tool_name in ("terminal", "execute_code"):
            return self._compress_terminal(content)
        elif tool_name in ("web_search", "web_extract"):
            return self._compress_web(content)
        elif tool_name in ("read_file",):
            return self._compress_file(content)
        else:
            return self._compress_generic(content)

    def _compress_terminal(self, content: str) -> str:
        """压缩终端输出"""
        lines = content.strip().split("\n")
        if len(lines) <= self._max_lines:
            return content

        # 提取关键信息
        key_lines = []
        errors = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 错误信息保留
            if any(kw in line.lower() for kw in ("error", "err", "fail", "exception", "traceback")):
                errors.append(line)
                continue

            # 数字/路径/结果保留
            if re.search(r"(?:\d+\.\d+\.\d+|/\S+|http\S+|[a-f0-9]{8,}|success|完成|done|ok)", line, re.IGNORECASE):
                key_lines.append(line)

        # 组装
        parts = []
        if errors:
            parts.append(f"❌ 错误: {'; '.join(errors[:2])}")
        if key_lines:
            parts.append(f"✅ 关键: {'; '.join(key_lines[:3])}")

        original_lines = len(lines)
        parts.append(f"📊 原始{original_lines}行，已压缩")

        return "\n".join(parts)

    def _compress_web(self, content: str) -> str:
        """压缩网页内容"""
        lines = content.strip().split("\n")
        if len(lines) <= self._max_lines:
            return content

        # 保留标题和关键段落
        key_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # 标题
            if line.startswith("#"):
                key_lines.append(line)
            # 包含链接的
            elif "http" in line:
                key_lines.append(line)
            # 包含数字的（可能是数据）
            elif re.search(r"\d{2,}", line):
                key_lines.append(line)

        if key_lines:
            summary = "\n".join(key_lines[:self._max_lines])
            return f"{summary}\n\n📊 原始{len(lines)}行，已压缩到关键内容"
        else:
            # 取前N行
            return "\n".join(lines[:self._max_lines]) + f"\n\n📊 原始{len(lines)}行，已截断"

    def _compress_file(self, content: str) -> str:
        """压缩文件内容"""
        lines = content.strip().split("\n")
        if len(lines) <= self._max_lines * 2:
            return content

        # 保留头部+尾部
        head = lines[:self._max_lines]
        tail = lines[-2:] if len(lines) > self._max_lines else []
        omitted = len(lines) - len(head) - len(tail)

        result = "\n".join(head)
        if omitted > 0:
            result += f"\n... ({omitted}行省略) ...\n"
        if tail:
            result += "\n".join(tail)

        return result

    def _compress_generic(self, content: str) -> str:
        """通用压缩"""
        lines = content.strip().split("\n")
        if len(lines) <= self._max_lines:
            return content

        # 去空行
        non_empty = [l for l in lines if l.strip()]
        if len(non_empty) <= self._max_lines:
            return "\n".join(non_empty)

        # 取前N行 + 统计
        head = non_empty[:self._max_lines]
        return "\n".join(head) + f"\n\n📊 原始{len(lines)}行({len(content)}字符)，已压缩"

    def should_compress(self, content: str) -> bool:
        """判断是否需要压缩"""
        return len(content) >= self._compress_threshold

    def get_stats(self, original: str, compressed: str) -> dict:
        """获取压缩统计"""
        orig_len = len(original)
        comp_len = len(compressed)
        ratio = comp_len / orig_len if orig_len > 0 else 1.0
        return {
            "original_chars": orig_len,
            "compressed_chars": comp_len,
            "compression_ratio": f"{ratio:.1%}",
            "chars_saved": orig_len - comp_len,
        }
