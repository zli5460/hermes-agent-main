"""
Phoenix V5.1 — 结构化记忆（Structured Memory）

参考DeerFlow的UserContext/HistoryContext/Facts分层设计
"""

import json
import time
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional


@dataclass
class ContextSection:
    """上下文分区"""
    summary: str = ""
    updated_at: float = 0


@dataclass
class UserContext:
    """用户上下文"""
    work_context: ContextSection = None
    personal_context: ContextSection = None
    top_of_mind: ContextSection = None

    def __post_init__(self):
        if self.work_context is None:
            self.work_context = ContextSection()
        if self.personal_context is None:
            self.personal_context = ContextSection()
        if self.top_of_mind is None:
            self.top_of_mind = ContextSection()


@dataclass
class HistoryContext:
    """历史上下文"""
    recent_months: ContextSection = None
    earlier_context: ContextSection = None
    long_term_background: ContextSection = None

    def __post_init__(self):
        if self.recent_months is None:
            self.recent_months = ContextSection()
        if self.earlier_context is None:
            self.earlier_context = ContextSection()
        if self.long_term_background is None:
            self.long_term_background = ContextSection()


@dataclass
class MemoryFact:
    """记忆事实"""
    id: str
    content: str
    category: str = "context"
    confidence: float = 0.5


class StructuredMemory:
    """结构化记忆管理器"""

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.user_context = UserContext()
        self.history_context = HistoryContext()
        self.facts: List[MemoryFact] = []
        self._load()

    def _load(self):
        """加载结构化记忆"""
        # 加载用户上下文
        uc_file = self.data_dir / "user_context.json"
        if uc_file.exists():
            try:
                data = json.loads(uc_file.read_text())
                self.user_context = UserContext(
                    work_context=ContextSection(**data.get("work_context", {})),
                    personal_context=ContextSection(**data.get("personal_context", {})),
                    top_of_mind=ContextSection(**data.get("top_of_mind", {}))
                )
            except Exception as exc:
                _ = exc

        # 加载历史上下文
        hc_file = self.data_dir / "history_context.json"
        if hc_file.exists():
            try:
                data = json.loads(hc_file.read_text())
                self.history_context = HistoryContext(
                    recent_months=ContextSection(**data.get("recent_months", {})),
                    earlier_context=ContextSection(**data.get("earlier_context", {})),
                    long_term_background=ContextSection(**data.get("long_term_background", {}))
                )
            except Exception as exc:
                _ = exc

        # 加载事实
        facts_file = self.data_dir / "memory_facts.json"
        if facts_file.exists():
            try:
                data = json.loads(facts_file.read_text())
                self.facts = [MemoryFact(**f) for f in data]
            except Exception as exc:
                _ = exc

    def _save(self):
        """保存结构化记忆"""
        # 保存用户上下文
        uc_file = self.data_dir / "user_context.json"
        uc_file.write_text(json.dumps(asdict(self.user_context), indent=2, ensure_ascii=False))

        # 保存历史上下文
        hc_file = self.data_dir / "history_context.json"
        hc_file.write_text(json.dumps(asdict(self.history_context), indent=2, ensure_ascii=False))

        # 保存事实
        facts_file = self.data_dir / "memory_facts.json"
        facts_file.write_text(json.dumps([asdict(f) for f in self.facts], indent=2, ensure_ascii=False))

    def update_work_context(self, summary: str):
        """更新工作上下文"""
        self.user_context.work_context.summary = summary
        self.user_context.work_context.updated_at = time.time()
        self._save()

    def update_personal_context(self, summary: str):
        """更新个人上下文"""
        self.user_context.personal_context.summary = summary
        self.user_context.personal_context.updated_at = time.time()
        self._save()

    def update_top_of_mind(self, summary: str):
        """更新当前关注"""
        self.user_context.top_of_mind.summary = summary
        self.user_context.top_of_mind.updated_at = time.time()
        self._save()

    def add_fact(self, content: str, category: str = "context", confidence: float = 0.5) -> MemoryFact:
        """添加事实"""
        fact = MemoryFact(
            id=f"fact_{int(time.time())}",
            content=content,
            category=category,
            confidence=confidence
        )
        self.facts.append(fact)
        self._save()
        return fact

    def get_context_prompt(self) -> str:
        """生成上下文提示词"""
        lines = ["## 用户上下文"]

        if self.user_context.work_context.summary:
            lines.append(f"- 工作: {self.user_context.work_context.summary}")
        if self.user_context.personal_context.summary:
            lines.append(f"- 个人: {self.user_context.personal_context.summary}")
        if self.user_context.top_of_mind.summary:
            lines.append(f"- 当前关注: {self.user_context.top_of_mind.summary}")

        if self.facts:
            lines.append("\n## 已知事实")
            for fact in self.facts[-10:]:  # 只取最近10条
                lines.append(f"- [{fact.category}] {fact.content}")

        return "\n".join(lines)
