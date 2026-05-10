"""
不死鸟 Phoenix V5.1 — 日记系统

最小可用实现：按天写入 / 读取 / 最近摘要。
用于记录系统每天做了什么，方便回溯和审计。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class DiaryEntry:
    date: str
    title: str
    content: str
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat(timespec="seconds")


class DiaryStore:
    def __init__(self, diary_file: Optional[str] = None):
        self._file = Path(diary_file) if diary_file else None
        self._entries: list[DiaryEntry] = []
        if self._file and self._file.exists():
            self._load()

    def write(self, title: str, content: str, date: Optional[str] = None) -> DiaryEntry:
        date = date or datetime.now().strftime("%Y-%m-%d")
        # Guard against recursive/huge content — truncate to 500 chars max
        if len(content) > 500:
            content = content[:500] + "...[truncated]"
        entry = DiaryEntry(date=date, title=title, content=content)
        self._entries.append(entry)
        self._save()
        return entry

    def append_session_summary(self, summary: str, title: str = "会话总结") -> DiaryEntry:
        return self.write(title=title, content=summary)

    def read(self, date: str) -> list[DiaryEntry]:
        return [e for e in self._entries if e.date == date]

    def recent(self, limit: int = 5) -> list[DiaryEntry]:
        return self._entries[-limit:]

    def to_prompt(self, limit: int = 3) -> str:
        recent = self.recent(limit)
        if not recent:
            return ""
        lines = ["## 最近日记"]
        for entry in recent:
            lines.append(f"- {entry.date} {entry.title}: {entry.content[:160]}")
        return "\n".join(lines)

    def stats(self) -> dict[str, int]:
        return {"entries": len(self._entries)}

    def _save(self):
        if not self._file:
            return
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            # 硬上限：最多保留500条条目，防无限截断
            if len(self._entries) > 500:
                self._entries = self._entries[-500:]
            # 防止文件过大：超过1MB只保留最近30天
            if self._file.exists() and self._file.stat().st_size > 1024 * 1024:
                from datetime import timedelta
                cutoff = (datetime.now() - timedelta(days=30)).isoformat()
                self._entries = [e for e in self._entries if e.created_at >= cutoff]
            self._file.write_text(
                json.dumps([asdict(e) for e in self._entries], ensure_ascii=False, indent=2)
            )
        except Exception:
            return

    def _load(self):
        try:
            data = json.loads(self._file.read_text())
            self._entries = [DiaryEntry(**item) for item in data]
        except Exception:
            self._entries = []
