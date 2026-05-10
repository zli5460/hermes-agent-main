"""
不死鸟 Phoenix V8 — 自动记忆提取引擎

不用用户说"记住这个"，AI自动判断什么值得记。

两种模式：
1. 规则提取（零成本）：关键词匹配，即时生效
2. LLM提取（可选）：复杂语义理解，按需开启

提取类别：
- 用户偏好（沟通风格、习惯）
- 环境信息（工具、配置、路径）
- 重要事实（人名、项目、关系）
- 纠错内容（用户纠正过的错误）
- 技能知识（解决问题的方法）
"""

import re
import json
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExtractedMemory:
    """提取的记忆条目"""
    content: str                        # 记忆内容
    category: str                       # 类别
    confidence: float                   # 置信度 (0-1)
    source: str                         # 来源: "rule" / "llm"
    extracted_at: float = 0.0           # 提取时间
    applied: bool = False               # 是否已应用

    def __post_init__(self):
        if not self.extracted_at:
            self.extracted_at = time.time()

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "category": self.category,
            "confidence": self.confidence,
            "source": self.source,
            "extracted_at": self.extracted_at,
            "applied": self.applied,
        }


class AutoExtractor:
    """
    自动记忆提取器

    用法:
        extractor = AutoExtractor()
        memories = extractor.extract("记住：我的API key是sk-abc123，以后不要用gpt-4")
        # → 自动提取到 "API key配置" 和 "不要用gpt-4的偏好"
    """

    # ===== 规则库 =====

    # 类别1：用户偏好（直接指令）
    PREFERENCE_PATTERNS = [
        (r"(?:记住|以后|以后都|永远|不要|别|禁止)[:\s：]*(.{3,50})", 0.95),
        (r"(?:我喜欢|我习惯|我偏好|我觉得好的是)[:\s：]*(.{3,50})", 0.90),
        (r"(?:不要用|别用|禁止用|换成)[:\s：]*(.{3,30})", 0.95),
        (r"(?:以后|从现在开始)(?:就|都)?[:\s：]*(.{3,50})", 0.85),
        (r"(?:叫我|称呼我)[:\s：]*(.{2,20})", 0.95),
    ]

    # 类别2：环境信息（配置/路径/工具）
    # 注意：API Key 只记录"有key"这个事实，绝不存原值（安全）
    ENVIRONMENT_PATTERNS = [
        (r"sk-[a-zA-Z0-9]{20,}", "api_key_present", 0.99),
        (r"tp-[a-zA-Z0-9]{20,}", "api_key_present", 0.99),
        (r"ghp_[a-zA-Z0-9]{36}", "api_key_present", 0.99),
        (r"(https?://[^\s]+\.(com|io|ai|dev)/[^\s]{5,})", "url", 0.85),
        (r"(~?/[\w/.\-]+)", "file_path", 0.85),
        (r"(port[:\s]+(\d{4,5}))", "port", 0.90),
    ]

    # 类别3：纠错内容（用户纠正AI的错误）
    CORRECTION_PATTERNS = [
        (r"(?:不对|不是|错了|搞错了|搞反了|应该.{2,20}不是)[:\s：]*(.{3,50})", 0.95),
        (r"(?:你理解错了|我说的是|我的意思是)[:\s：]*(.{3,50})", 0.95),
        (r"(?:不是这样|这样不对|改过来)[:\s：]*(.{0,50})", 0.85),
    ]

    # 类别4：重要事实（人名/项目/关系）
    FACT_PATTERNS = [
        (r"(?:我(?:是|叫|的(?:名字|公司|团队)))[:\s：]*(.{2,30})", 0.85),
        (r"(?:我们(?:公司|团队|项目))(?:叫|是)[:\s：]*(.{2,30})", 0.85),
        (r"((?:飞书|Telegram|微信|Discord|Slack)(?:的|上)?[:\s：]*.{2,30})", 0.80),
    ]

    # 类别5：技能知识（解决方法）
    SKILL_PATTERNS = [
        (r"(?:用(?:这个|以下)方法|这样做.{2,5}就行|正确的做法是)[:\s：]*(.{3,80})", 0.80),
        (r"(?:遇到.{2,20}(?:就|要))[:\s：]*(.{3,50})", 0.75),
    ]

    # 需要忽略的噪音
    NOISE_PATTERNS = [
        r"^(?:嗯|哦|好|是的|对|行|OK|ok|好的|可以|没问题|收到)$",
        r"^(?:哈哈|嘿嘿|😂|👍|✅|🙏).{0,5}$",
        r"^.{1,3}$",  # 太短的
    ]

    def __init__(self, memory_file: Optional[str] = None):
        self._memory_file = Path(memory_file) if memory_file else None
        self._extracted: list[ExtractedMemory] = []
        self._dedup_set: set[str] = set()  # 去重

        if self._memory_file and self._memory_file.exists():
            self._load_extracted()

    def extract(self, message: str, role: str = "user") -> list[ExtractedMemory]:
        """
        从消息中提取记忆

        Args:
            message: 消息内容
            role: 发送者角色 ("user" / "assistant")

        Returns:
            提取的记忆列表
        """
        memories = []
        message = message.strip()

        # 噪音过滤
        if self._is_noise(message):
            return memories

        # 规则提取
        memories.extend(self._extract_preferences(message))
        memories.extend(self._extract_environment(message))
        memories.extend(self._extract_corrections(message, role))
        memories.extend(self._extract_facts(message))
        memories.extend(self._extract_skills(message))

        # 同一轮里先做一次“长内容优先”归一化，避免一句话拆出多条子串记忆
        memories = self._prefer_longer_memories(memories)

        # 去重
        unique_memories = []
        for m in memories:
            key = f"{m.category}:{m.content[:50]}"
            if key not in self._dedup_set:
                self._dedup_set.add(key)
                unique_memories.append(m)

        # 保存
        self._extracted.extend(unique_memories)
        if unique_memories:
            self._save_extracted()

        return unique_memories

    def extract_from_conversation(self, messages: list[dict]) -> list[ExtractedMemory]:
        """
        从完整对话历史中批量提取

        Args:
            messages: [{"role": "user/assistant", "content": "..."}, ...]

        Returns:
            所有提取的记忆
        """
        all_memories = []
        for msg in messages:
            content = msg.get("content", "")
            role = msg.get("role", "user")
            if isinstance(content, list):
                # 处理多模态消息
                content = " ".join(
                    block.get("text", "")
                    for block in content
                    if isinstance(block, dict) and block.get("type") == "text"
                )
            memories = self.extract(content, role)
            all_memories.extend(memories)
        return all_memories

    def get_unapplied(self) -> list[ExtractedMemory]:
        """获取未应用的记忆"""
        return [m for m in self._extracted if not m.applied]

    def mark_applied(self, memory: ExtractedMemory):
        """标记记忆已应用"""
        memory.applied = True
        self._save_extracted()

    def get_stats(self) -> dict:
        """获取提取统计"""
        by_category = {}
        by_source = {"rule": 0, "llm": 0}
        for m in self._extracted:
            by_category[m.category] = by_category.get(m.category, 0) + 1
            by_source[m.source] = by_source.get(m.source, 0) + 1
        return {
            "total": len(self._extracted),
            "unapplied": len(self.get_unapplied()),
            "by_category": by_category,
            "by_source": by_source,
        }

    # ===== 内部方法 =====

    def _is_noise(self, message: str) -> bool:
        """判断是否为噪音"""
        for pattern in self.NOISE_PATTERNS:
            if re.match(pattern, message, re.IGNORECASE):
                return True
        return False

    def _extract_preferences(self, message: str) -> list[ExtractedMemory]:
        """提取用户偏好"""
        memories = []
        for pattern, confidence in self.PREFERENCE_PATTERNS:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                content = match.group(1).strip()
                if len(content) >= 3:
                    memories.append(ExtractedMemory(
                        content=content,
                        category="preference",
                        confidence=confidence,
                        source="rule",
                    ))
        return memories

    def _extract_environment(self, message: str) -> list[ExtractedMemory]:
        """提取环境信息"""
        memories = []
        for pattern, sub_category, confidence in self.ENVIRONMENT_PATTERNS:
            match = re.search(pattern, message)
            if match:
                # API Key 只存类别，不存具体内容（安全）
                if sub_category.startswith("api_key"):
                    memories.append(ExtractedMemory(
                        content="用户有API Key配置",
                        category="environment",
                        confidence=confidence,
                        source="rule",
                    ))
                else:
                    content = match.group(1).strip() if match.lastindex else match.group(0).strip()
                    memories.append(ExtractedMemory(
                        content=content,
                        category="environment",
                        confidence=confidence,
                        source="rule",
                    ))
        return memories

    def _extract_corrections(self, message: str, role: str) -> list[ExtractedMemory]:
        """提取纠错内容（只有用户纠错才提取）"""
        if role != "user":
            return []
        memories = []
        for pattern, confidence in self.CORRECTION_PATTERNS:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                content = match.group(1).strip()
                if len(content) >= 3:
                    memories.append(ExtractedMemory(
                        content=f"[纠错] {content}",
                        category="correction",
                        confidence=confidence,
                        source="rule",
                    ))
        return memories

    def _extract_facts(self, message: str) -> list[ExtractedMemory]:
        """提取重要事实"""
        memories = []
        for pattern, confidence in self.FACT_PATTERNS:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                content = match.group(1).strip()
                if len(content) >= 2:
                    memories.append(ExtractedMemory(
                        content=content,
                        category="fact",
                        confidence=confidence,
                        source="rule",
                    ))
        return memories

    def _extract_skills(self, message: str) -> list[ExtractedMemory]:
        """提取技能知识"""
        memories = []
        for pattern, confidence in self.SKILL_PATTERNS:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                content = match.group(1).strip()
                if len(content) >= 5:
                    memories.append(ExtractedMemory(
                        content=content,
                        category="skill",
                        confidence=confidence,
                        source="rule",
                    ))
        return memories

    def _prefer_longer_memories(self, memories: list[ExtractedMemory]) -> list[ExtractedMemory]:
        """优先保留更完整的记忆，减少同一句话被拆成多个子串。"""
        if len(memories) <= 1:
            return memories

        selected: list[ExtractedMemory] = []
        for mem in sorted(memories, key=lambda m: (m.category, -len(m.content), -m.confidence)):
            if any(
                mem.category == other.category and mem.content in other.content and len(mem.content) < len(other.content)
                for other in selected
            ):
                continue
            selected.append(mem)
        return selected

    def _save_extracted(self):
        """持久化到磁盘"""
        if not self._memory_file:
            return
        try:
            self._memory_file.parent.mkdir(parents=True, exist_ok=True)
            data = [m.to_dict() for m in self._extracted]
            self._memory_file.write_text(
                json.dumps(data, indent=2, ensure_ascii=False)
            )
        except Exception:
            return

    def _load_extracted(self):
        """从磁盘加载"""
        try:
            data = json.loads(self._memory_file.read_text())
            for item in data:
                mem = ExtractedMemory(**item)
                self._extracted.append(mem)
                self._dedup_set.add(f"{mem.category}:{mem.content[:50]}")
        except Exception:
            return

    def _llm_extract(self, text):
        """V4: LLM深度提取，失败返回[]"""
        try:
            import os, json
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key: return []
            import anthropic
            client = anthropic.Anthropic(api_key=api_key, timeout=5.0)
            prompt = f"从消息提取记忆，返回JSON数组: [{{'content':str,'category':'preference|environment|fact','confidence':0-1}}]\n消息: {text[:1000]}\n只返回JSON"
            resp = client.messages.create(model="claude-3-haiku-20240307", max_tokens=500, messages=[{"role":"user","content":prompt}])
            out = resp.content[0].text.strip()
            s,e = out.find("["), out.rfind("]")
            if s<0 or e<0: return []
            data = json.loads(out[s:e+1])
            return [ExtractedMemory(content=i["content"], category=i.get("category","fact"), confidence=float(i.get("confidence",0.7)), source="llm") for i in data if isinstance(i,dict) and i.get("content","").strip()]
        except Exception: return []
    def extract_with_fallback(self, text, min_rule_count=1):
        """V4: 先规则→LLM降级链"""
        rule = self.extract(text)
        if len(rule) >= min_rule_count: return rule
        llm = self._llm_extract(text)
        if llm:
            seen = {m.content for m in rule}
            for m in llm:
                if m.content not in seen: rule.append(m)
        return rule
