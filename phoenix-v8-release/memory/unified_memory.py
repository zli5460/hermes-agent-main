"""
Phoenix V8 — 统一记忆模块
合并: session (会话记忆) + layered_memory (4层记忆) + self_wiring_kg (自连线知识图谱)

提供：
- SessionMemory: 会话级临时记忆
- LayeredMemory: L1-L4分层持久记忆
- SelfWiringKG: 自连线知识图谱（零LLM调用）
"""

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


# ============================================================
# Part 1: SessionMemory (会话记忆)
# ============================================================

@dataclass
class SessionEntry:
    """会话记忆条目"""
    key: str
    value: str
    category: str = "context"
    importance: int = 1
    created_at: float = 0.0
    last_accessed: float = 0.0
    access_count: int = 0

    def __post_init__(self):
        if not self.created_at:
            self.created_at = time.time()
        if not self.last_accessed:
            self.last_accessed = time.time()

    def access(self):
        self.last_accessed = time.time()
        self.access_count += 1

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "value": self.value,
            "category": self.category,
            "importance": self.importance,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "access_count": self.access_count,
        }


class SessionMemory:
    """会话记忆管理器"""

    def __init__(self, max_entries: int = 50):
        self._entries: dict[str, SessionEntry] = {}
        self._max_entries = max_entries

    def set(self, key: str, value: str, category: str = "context",
            importance: int = 1) -> SessionEntry:
        entry = SessionEntry(key=key, value=value, category=category, importance=importance)
        self._entries[key] = entry
        if len(self._entries) > self._max_entries:
            self._evict()
        return entry

    def get(self, key: str) -> Optional[str]:
        entry = self._entries.get(key)
        if entry:
            entry.access()
            return entry.value
        return None

    def get_all(self, category: str = None) -> list[SessionEntry]:
        entries = list(self._entries.values())
        if category:
            entries = [e for e in entries if e.category == category]
        return sorted(entries, key=lambda e: e.importance, reverse=True)

    def get_important(self, min_importance: int = 4) -> list[SessionEntry]:
        return [e for e in self._entries.values() if e.importance >= min_importance]

    def delete(self, key: str) -> bool:
        if key in self._entries:
            del self._entries[key]
            return True
        return False

    def clear(self):
        self._entries.clear()

    def extract_persistent(self) -> list[dict]:
        to_persist = []
        for entry in self._entries.values():
            should_persist = (
                entry.importance >= 4
                or entry.access_count >= 3
                or entry.category == "correction"
            )
            if should_persist:
                to_persist.append({
                    "content": f"{entry.key}: {entry.value}",
                    "category": entry.category,
                    "importance": entry.importance,
                })
        return to_persist

    def get_context_summary(self) -> str:
        if not self._entries:
            return ""
        lines = ["## 当前会话上下文"]
        for entry in sorted(self._entries.values(), key=lambda e: e.importance, reverse=True):
            importance_mark = "⭐" * entry.importance
            lines.append(f"- {entry.key}: {entry.value} [{importance_mark}]")
        return "\n".join(lines)

    def get_stats(self) -> dict:
        by_category = {}
        for e in self._entries.values():
            by_category[e.category] = by_category.get(e.category, 0) + 1
        return {
            "total": len(self._entries),
            "max": self._max_entries,
            "by_category": by_category,
            "persistent_candidates": len(self.extract_persistent()),
        }

    def _evict(self):
        """淘汰最不重要的记忆"""
        if len(self._entries) <= self._max_entries:
            return
        worst_key = min(self._entries.keys(),
                        key=lambda k: (self._entries[k].importance, self._entries[k].access_count))
        del self._entries[worst_key]


# ============================================================
# Part 2: LayeredMemory (4层记忆架构)
# ============================================================

class LayeredMemory:
    """4层记忆架构: L1索引 / L2事实 / L3记录 / L4历史"""

    def __init__(self):
        self._data_dir = Path.home() / ".hermes" / "phoenix" / "data"

    def get_l1_index(self) -> str:
        """L1: 全局索引（≤30行）"""
        index_lines = []
        l2 = self._load_l2()
        for category, items in l2.items():
            if items:
                index_lines.append(f"{category}: {', '.join(items[:3])}")
        index_lines.append("RULES: 不存密码/API Key; 不存易变状态; 验证后才记忆")
        return "\n".join(index_lines[:30])

    def get_l2_facts(self) -> Dict:
        """L2: 事实库"""
        return self._load_l2()

    def add_l2_fact(self, category: str, fact: str):
        """添加事实到L2"""
        l2 = self._load_l2()
        if category not in l2:
            l2[category] = []
        if fact not in l2[category]:
            l2[category].append(fact)
        self._save_l2(l2)

    def get_l3_records(self) -> List[Dict]:
        """L3: 记录库"""
        return self._load_l3()

    def add_l3_record(self, record: Dict):
        """添加记录到L3"""
        l3 = self._load_l3()
        l3.append(record)
        self._save_l3(l3)

    def get_context_for_prompt(self) -> str:
        """生成系统prompt用的上下文"""
        parts = []
        l1 = self.get_l1_index()
        if l1:
            parts.append(f"## 记忆索引\n{l1}")
        l2 = self.get_l2_facts()
        if l2:
            lines = ["## 关键事实"]
            for cat, items in l2.items():
                lines.append(f"- {cat}: {', '.join(items[:5])}")
            parts.append("\n".join(lines))
        return "\n\n".join(parts)

    def _load_l2(self) -> Dict:
        path = self._data_dir / "memory_l2.json"
        try:
            if path.exists():
                return json.loads(path.read_text())
        except Exception as exc:
            _ = exc
        return {}

    def _save_l2(self, data: Dict):
        self._data_dir.mkdir(parents=True, exist_ok=True)
        (self._data_dir / "memory_l2.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2)
        )

    def _load_l3(self) -> List[Dict]:
        path = self._data_dir / "memory_l3.json"
        try:
            if path.exists():
                return json.loads(path.read_text())
        except Exception as exc:
            _ = exc
        return []

    def _save_l3(self, data: List[Dict]):
        self._data_dir.mkdir(parents=True, exist_ok=True)
        (self._data_dir / "memory_l3.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2)
        )


# ============================================================
# Part 3: SelfWiringKG (自连线知识图谱)
# ============================================================

class SelfWiringKG:
    """自连线知识图谱 — 每次写入自动提取实体+创建类型链接，零LLM调用"""

    ENTITY_PATTERNS = {
        "person": [
            r"([A-Z][a-z]+ [A-Z][a-z]+)",
            r"(用户|user)",
        ],
        "company": [
            r"(MCN|Nous|Anthropic|OpenAI|Google|Xiaomi|小米)",
        ],
        "tool": [
            r"(Python|VS Code|Claude|MIMO|GPT|Gemini|Edge TTS|Scrapling|Tavily)",
        ],
        "platform": [
            r"(Telegram|飞书|Discord|GitHub|微信|WeChat)",
        ],
        "system": [
            r"(Phoenix|不死鸟|Hermes|OpenClaw)",
        ],
    }

    RELATION_PATTERNS = {
        "uses": [r"使用.{0,5}(工具|平台|模型)"],
        "works_at": [r"(在|是).{0,10}(公司|团队)"],
        "prefers": [r"(喜欢|偏好|默认).{0,10}(工具|模型|语言)"],
        "built": [r"(创建|搭建|开发|构建).{0,10}(系统|工具|平台)"],
        "integrates": [r"集成.{0,10}(平台|工具|系统)"],
    }

    def __init__(self):
        self._data_dir = Path.home() / ".hermes" / "phoenix" / "data"
        self._kg_file = self._data_dir / "self_wiring_kg.json"
        self._kg = self._load()

    def wire(self, text: str) -> Dict:
        """从文本中自动连线知识图谱"""
        entities = self._extract_entities(text)
        relations = self._extract_relations(text, entities)
        for entity in entities:
            self._add_entity(entity)
        for relation in relations:
            self._add_relation(relation)
        self._save()
        return {
            "entities_added": len(entities),
            "relations_added": len(relations),
            "total_entities": len(self._kg.get("entities", [])),
            "total_relations": len(self._kg.get("relations", [])),
        }

    def _extract_entities(self, text: str) -> List[Dict]:
        entities = []
        seen = set()
        for etype, patterns in self.ENTITY_PATTERNS.items():
            for pattern in patterns:
                matches = re.findall(pattern, text)
                for match in matches:
                    if match not in seen:
                        seen.add(match)
                        entities.append({
                            "name": match,
                            "type": etype,
                            "first_seen": time.time(),
                        })
        return entities

    def _extract_relations(self, text: str, entities: List[Dict]) -> List[Dict]:
        relations = []
        entity_names = [e["name"] for e in entities]
        for rtype, patterns in self.RELATION_PATTERNS.items():
            for pattern in patterns:
                matches = re.finditer(pattern, text)
                for match in matches:
                    context = text[max(0, match.start() - 20):match.end() + 20]
                    for name1 in entity_names:
                        for name2 in entity_names:
                            if name1 != name2 and name1 in context and name2 in context:
                                relations.append({
                                    "from": name1,
                                    "to": name2,
                                    "type": rtype,
                                    "context": context[:100],
                                    "created": time.time(),
                                })
        return relations

    def _add_entity(self, entity: Dict):
        if "entities" not in self._kg:
            self._kg["entities"] = []
        for existing in self._kg["entities"]:
            if existing["name"] == entity["name"]:
                existing["last_seen"] = time.time()
                existing["mention_count"] = existing.get("mention_count", 0) + 1
                return
        entity["mention_count"] = 1
        self._kg["entities"].append(entity)

    def _add_relation(self, relation: Dict):
        if "relations" not in self._kg:
            self._kg["relations"] = []
        for existing in self._kg["relations"]:
            if (existing["from"] == relation["from"] and
                    existing["to"] == relation["to"] and
                    existing["type"] == relation["type"]):
                existing["count"] = existing.get("count", 0) + 1
                return
        relation["count"] = 1
        self._kg["relations"].append(relation)

    def query(self, entity_name: str) -> Dict:
        """查询实体及其关系"""
        entity = None
        for e in self._kg.get("entities", []):
            if e["name"] == entity_name:
                entity = e
                break
        if not entity:
            return {"found": False}
        relations = []
        for r in self._kg.get("relations", []):
            if r["from"] == entity_name or r["to"] == entity_name:
                relations.append(r)
        return {"found": True, "entity": entity, "relations": relations}

    def stats(self) -> Dict:
        return {
            "entities": len(self._kg.get("entities", [])),
            "relations": len(self._kg.get("relations", [])),
        }

    def _load(self):
        try:
            if self._kg_file.exists():
                return json.loads(self._kg_file.read_text())
        except Exception as exc:
            _ = exc
        return {"entities": [], "relations": []}

    def _save(self):
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._kg_file.write_text(json.dumps(self._kg, ensure_ascii=False, indent=2))


# ============================================================
# 模块级单例
# ============================================================
session_memory = SessionMemory()
layered_memory = LayeredMemory()
self_wiring_kg = SelfWiringKG()
