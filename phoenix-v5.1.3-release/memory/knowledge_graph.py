"""
不死鸟 Phoenix — 知识图谱（独立版）

与 unified_memory.SelfWiringKG 并存：
- KnowledgeGraph: 持久化JSON文件，支持 add_entity/stats/to_prompt
- SelfWiringKG: 内存态，自动连线

两个KG各有用途，不合并。
"""

import json
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("phoenix.knowledge_graph")


class KnowledgeGraph:
    """
    持久化知识图谱 — JSON文件存储
    
    支持：
    - add_entity(name, type, properties)
    - add_relation(source, target, type)
    - stats() → {entities: N, relations: N}
    - to_prompt() → 可注入system prompt的文本
    """
    
    def __init__(self, graph_file: str = None):
        self._file = Path(graph_file) if graph_file else None
        self._entities: Dict[str, dict] = {}
        self._relations: List[dict] = []
        self._load()
    
    def _load(self):
        if self._file and self._file.exists():
            try:
                data = json.loads(self._file.read_text())
                self._entities = data.get("entities", {})
                self._relations = data.get("relations", [])
            except Exception as e:
                logger.warning("Failed to load KG: %s", e)
    
    def _save(self):
        if self._file:
            try:
                self._file.parent.mkdir(parents=True, exist_ok=True)
                self._file.write_text(json.dumps({
                    "entities": self._entities,
                    "relations": self._relations,
                }, ensure_ascii=False, indent=2))
            except Exception as e:
                logger.warning("Failed to save KG: %s", e)
    
    def add_entity(self, name: str, entity_type: str = "concept", properties: dict = None):
        """添加实体"""
        if name not in self._entities:
            self._entities[name] = {
                "type": entity_type,
                "properties": properties or {},
                "created_at": time.time(),
            }
            self._save()
    
    def add_relation(self, source: str, target: str, relation_type: str = "related"):
        """添加关系"""
        self._relations.append({
            "source": source,
            "target": target,
            "type": relation_type,
            "created_at": time.time(),
        })
        self._save()
    
    def stats(self) -> dict:
        """返回统计信息"""
        return {
            "entities": len(self._entities),
            "relations": len(self._relations),
        }
    
    def to_prompt(self) -> str:
        """转换为可注入prompt的文本"""
        if not self._entities:
            return ""
        
        lines = ["知识图谱:"]
        for name, data in self._entities.items():
            lines.append(f"  - {name} ({data['type']})")
        
        if self._relations:
            lines.append("关系:")
            for rel in self._relations[-20:]:  # 最近20条
                lines.append(f"  {rel['source']} --{rel['type']}--> {rel['target']}")
        
        return "\n".join(lines)
