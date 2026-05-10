"""
Phoenix 记忆自动化 — 独立模块

CLI和Gateway都能调，不依赖特定入口。
每条消息自动：提取记忆 + 更新知识图谱 + 写日记

用法：
    from phoenix.integration.memory_auto import phoenix_memory
    phoenix_memory.on_message("用户消息", "AI回复", model="mimo-v2.5")
"""

import os
import re
import json
import time
import logging
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger("phoenix.memory_auto")

HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
PHOENIX_DATA = HERMES_HOME / "phoenix" / "data"

# 文件路径
EXTRACTED_MEMORIES = PHOENIX_DATA / "extracted_memories.json"
LONG_TERM_MEMORY = PHOENIX_DATA / "long_term_memory.json"
DIARY_FILE = PHOENIX_DATA / "diary.json"
KG_FILE = PHOENIX_DATA / "knowledge_graph.json"
SESSION_MEMORY = PHOENIX_DATA / "session_memory.json"


def _read_json(path: Path):
    """安全读取JSON"""
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception as exc:
        _ = exc
    return [] if "memory" in path.name or "diary" in path.name or "extracted" in path.name else {}


def _write_json(path: Path, data):
    """原子写入"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.rename(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except Exception as exc:
            _ = exc


def _append_item(path: Path, item: dict, max_items: int = 500):
    """追加到数组并裁剪"""
    items = _read_json(path)
    if not isinstance(items, list):
        items = []
    items.append(item)
    if len(items) > max_items:
        items = items[-max_items:]
    _write_json(path, items)


class PhoenixMemory:
    """Phoenix记忆自动化核心"""

    def on_message(self, user_message: str, ai_response: str = "",
                   model: str = "", task_type: str = ""):
        """
        每条消息调用一次，自动完成所有记忆操作
        
        不抛异常，不影响主流程。
        """
        if not user_message or len(user_message) < 3:
            return

        try:
            self._extract_memories(user_message)
        except Exception as e:
            logger.debug("Memory extract failed: %s", e)

        try:
            self._update_kg(user_message, ai_response)
        except Exception as e:
            logger.debug("KG update failed: %s", e)

        try:
            self._write_diary(user_message, ai_response, model, task_type)
        except Exception as e:
            logger.debug("Diary write failed: %s", e)

    def _extract_memories(self, message: str):
        """从消息提取记忆 — 统一委托给 auto_extract.AutoExtractor"""
        try:
            from phoenix.memory.auto_extract import AutoExtractor
            if not hasattr(self, "_extractor"):
                self._extractor = AutoExtractor(memory_file=str(EXTRACTED_MEMORIES))
            memories = self._extractor.extract(message, role="user")
            if memories:
                logger.debug("Extracted %d memories via AutoExtractor", len(memories))
        except Exception as e:
            logger.debug("AutoExtractor failed, skip: %s", e)

    def _update_kg(self, message: str, response: str):
        """更新知识图谱"""
        kg = _read_json(KG_FILE)
        if not isinstance(kg, dict):
            kg = {"entities": [], "relations": []}

        # 提取实体关系
        patterns = [
            (r"我叫(.+?)[\s，。,.]", lambda m: ("我", "叫", m.group(1).strip())),
            (r"(.{2,10})是(.{2,20})[\s，。,.]", lambda m: (m.group(1).strip(), "is", m.group(2).strip())),
        ]

        new_relations = 0
        for pattern, extractor in patterns:
            for match in re.finditer(pattern, message):
                try:
                    s, p, o = extractor(match)
                    if len(s) < 20 and len(o) < 50:
                        rel = {"subject": s, "predicate": p, "object": o}
                        if rel not in kg["relations"]:
                            kg["relations"].append(rel)
                            new_relations += 1
                except Exception as exc:
                    _ = exc

        # 裁剪
        if len(kg["relations"]) > 300:
            kg["relations"] = kg["relations"][-300:]

        if new_relations > 0:
            _write_json(KG_FILE, kg)
            logger.debug("KG updated: %d new relations", new_relations)

    def _write_diary(self, message: str, response: str,
                     model: str, task_type: str):
        """写日记"""
        entry = {
            "timestamp": time.time(),
            "msg": message[:200],
            "resp": response[:100] if response else "",
            "model": model,
            "type": task_type,
        }
        _append_item(DIARY_FILE, entry, max_items=500)

    def get_context_for_prompt(self) -> str:
        """加载记忆用于prompt注入"""
        parts = []

        # 长期记忆
        ltm = _read_json(LONG_TERM_MEMORY)
        if isinstance(ltm, list) and ltm:
            sorted_mem = sorted(ltm, key=lambda m: m.get("importance", 0), reverse=True)[:10]
            lines = ["不死鸟记忆:"]
            for mem in sorted_mem:
                lines.append(f"- [{mem.get('category','')}] {mem.get('content','')}")
            parts.append("\n".join(lines))

        # 最近提取的记忆
        extracted = _read_json(EXTRACTED_MEMORIES)
        if isinstance(extracted, list):
            recent = [m for m in extracted[-5:] if not m.get("applied")]
            if recent:
                lines = ["最近发现:"]
                for mem in recent:
                    lines.append(f"- {mem.get('content','')}")
                parts.append("\n".join(lines))

        return "\n\n".join(parts)

    def get_stats(self) -> dict:
        """获取记忆统计"""
        extracted = _read_json(EXTRACTED_MEMORIES)
        diary = _read_json(DIARY_FILE)
        kg = _read_json(KG_FILE)
        ltm = _read_json(LONG_TERM_MEMORY)

        return {
            "extracted_memories": len(extracted) if isinstance(extracted, list) else 0,
            "diary_entries": len(diary) if isinstance(diary, list) else 0,
            "kg_relations": len(kg.get("relations", [])) if isinstance(kg, dict) else 0,
            "long_term_memories": len(ltm) if isinstance(ltm, list) else 0,
        }


# 全局单例
phoenix_memory = PhoenixMemory()
