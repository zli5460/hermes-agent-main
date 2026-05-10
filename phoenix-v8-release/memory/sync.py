"""
不死鸟 Phoenix V8 — 记忆同步 + 恢复

同步：Cron定时将会话记忆/提取记忆同步到长期存储
恢复：启动时自动恢复上次状态
"""

import json
import time
from pathlib import Path
from typing import Optional


class MemorySync:
    """
    记忆同步器

    负责：
    1. 会话记忆 → 长期记忆文件
    2. 提取的记忆 → 长期记忆文件
    3. 清理过期/低价值记忆
    """

    def __init__(self, memory_file: str = None):
        self._memory_file = Path(memory_file) if memory_file else self._default_path()
        self._memories: list[dict] = []
        self._load()

    def _default_path(self) -> Path:
        hermes_home = Path.home() / ".hermes"
        return hermes_home / "phoenix" / "data" / "long_term_memory.json"

    def sync_from_session(self, session_memories: list[dict]):
        """
        从会话记忆同步到长期记忆

        Args:
            session_memories: [{"content": "...", "category": "...", "importance": N}]
        """
        for mem in session_memories:
            content = mem.get("content", "")
            if not content:
                continue

            # 去重
            if self._is_duplicate(content):
                continue

            self._memories.append({
                "content": content,
                "category": mem.get("category", "context"),
                "importance": mem.get("importance", 1),
                "source": "session",
                "created_at": time.time(),
                "last_accessed": time.time(),
                "access_count": 0,
            })

        self._prune()
        self._save()

    def sync_from_extracted(self, extracted_memories: list):
        """
        从自动提取的记忆同步到长期记忆
        """
        for mem in extracted_memories:
            content = mem.content if hasattr(mem, "content") else str(mem)
            category = mem.category if hasattr(mem, "category") else "extracted"
            confidence = mem.confidence if hasattr(mem, "confidence") else 0.5

            if self._is_duplicate(content):
                continue

            self._memories.append({
                "content": content,
                "category": category,
                "importance": int(confidence * 5),
                "source": "auto_extract",
                "created_at": time.time(),
                "last_accessed": time.time(),
                "access_count": 0,
            })

        self._prune()
        self._save()

    def get_all(self, category: str = None) -> list[dict]:
        """获取所有长期记忆"""
        if category:
            return [m for m in self._memories if m["category"] == category]
        return self._memories

    def get_for_prompt(self, max_items: int = 10) -> str:
        """获取格式化记忆，用于注入系统prompt"""
        if not self._memories:
            return ""

        # 按重要性排序
        sorted_mems = sorted(self._memories, key=lambda m: m.get("importance", 0), reverse=True)

        lines = ["## 长期记忆"]
        for mem in sorted_mems[:max_items]:
            importance = "⭐" * mem.get("importance", 1)
            lines.append(f"- [{mem['category']}] {mem['content']} {importance}")

        return "\n".join(lines)

    def search(self, keyword: str) -> list[dict]:
        """搜索记忆"""
        keyword_lower = keyword.lower()
        return [
            m for m in self._memories
            if keyword_lower in m["content"].lower()
        ]

    def delete(self, content_prefix: str) -> int:
        """删除匹配的记忆"""
        before = len(self._memories)
        self._memories = [
            m for m in self._memories
            if not m["content"].startswith(content_prefix)
        ]
        deleted = before - len(self._memories)
        if deleted:
            self._save()
        return deleted

    def get_stats(self) -> dict:
        """获取统计"""
        by_category = {}
        for m in self._memories:
            cat = m.get("category", "unknown")
            by_category[cat] = by_category.get(cat, 0) + 1
        return {
            "total": len(self._memories),
            "max": 200,
            "by_category": by_category,
        }

    def _is_duplicate(self, content: str) -> bool:
        """检查是否重复"""
        content_lower = content.lower()[:50]
        for m in self._memories:
            if m["content"].lower()[:50] == content_lower:
                return True
        return False

    def _prune(self, max_items: int = 200):
        """修剪：超出上限时删除最不重要的"""
        if len(self._memories) <= max_items:
            return
        # 按重要性排序，保留前N个
        self._memories.sort(key=lambda m: m.get("importance", 0), reverse=True)
        self._memories = self._memories[:max_items]

    def _save(self):
        """持久化"""
        try:
            self._memory_file.parent.mkdir(parents=True, exist_ok=True)
            self._memory_file.write_text(
                json.dumps(self._memories, indent=2, ensure_ascii=False)
            )
        except Exception:
            return

    def _load(self):
        """加载"""
        if not self._memory_file.exists():
            return
        try:
            self._memories = json.loads(self._memory_file.read_text())
        except Exception:
            self._memories = []


class PhoenixRecover:
    """
    不死鸟恢复器

    启动时自动恢复：
    1. 加载长期记忆
    2. 恢复系统状态
    3. 加载抗体库
    4. 加载进化数据
    """

    def __init__(self, data_dir: str = None):
        self._data_dir = Path(data_dir) if data_dir else Path.home() / ".hermes" / "phoenix" / "data"

    def recover(self) -> dict:
        """
        执行恢复

        Returns: {"recovered": list, "failed": list}
        """
        recovered = []
        failed = []

        files_to_check = [
            ("state.json", "系统状态"),
            ("long_term_memory.json", "长期记忆"),
            ("extracted_memories.json", "提取记忆"),
            ("antibodies.json", "抗体库"),
            ("evolution.json", "进化数据"),
        ]

        for filename, description in files_to_check:
            filepath = self._data_dir / filename
            if filepath.exists():
                try:
                    data = json.loads(filepath.read_text())
                    if isinstance(data, list):
                        items = len(data)
                    elif isinstance(data, dict):
                        items = len(data)
                    else:
                        items = 1
                    recovered.append(f"{description}: {items}条")
                except Exception as e:
                    failed.append(f"{description}: {e}")
            else:
                failed.append(f"{description}: 文件不存在")

        return {
            "recovered": recovered,
            "failed": failed,
            "data_dir": str(self._data_dir),
        }

    def get_recovery_summary(self) -> str:
        """获取恢复摘要（人类可读）"""
        result = self.recover()
        lines = ["🔄 不死鸟恢复报告"]
        if result["recovered"]:
            lines.append("已恢复:")
            for r in result["recovered"]:
                lines.append(f"  ✅ {r}")
        if result["failed"]:
            lines.append("未恢复:")
            for f in result["failed"]:
                lines.append(f"  ⚠️ {f}")
        return "\n".join(lines)
