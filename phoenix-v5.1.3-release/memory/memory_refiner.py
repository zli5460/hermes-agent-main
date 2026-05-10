"""不死鸟 Phoenix V5.1 — 记忆LLM提炼
用mimo-flash把原始记忆提炼成结构化知识
"""

import json
from pathlib import Path
from typing import List, Dict

class MemoryRefiner:
    """记忆提炼器"""
    
    def __init__(self):
        self._data_dir = Path.home() / ".hermes" / "phoenix" / "data"
    
    def refine_all(self) -> Dict:
        """提炼所有记忆"""
        stats = {"refined": 0, "skipped": 0, "errors": 0}
        
        # 提取原始记忆
        ext_path = self._data_dir / "extracted_memories.json"
        if ext_path.exists():
            memories = json.loads(ext_path.read_text())
            refined = []
            for mem in memories:
                try:
                    refined_mem = self._refine_one(mem)
                    if refined_mem:
                        refined.append(refined_mem)
                        stats["refined"] += 1
                    else:
                        refined.append(mem)
                        stats["skipped"] += 1
                except Exception:
                    refined.append(mem)
                    stats["errors"] += 1

            # 保存提炼后的记忆（保留原样）
            ext_path.write_text(json.dumps(refined, ensure_ascii=False, indent=2))
        
        return stats
    
    def _refine_one(self, mem: Dict) -> Dict:
        """提炼单条记忆"""
        content = mem.get("content", "")
        category = mem.get("category", "")
        
        # 跳过太短或无意义的
        if len(content) < 10:
            return None
        
        # 结构化提炼
        refined = {
            "content": self._clean_content(content),
            "category": self._infer_category(content, category),
            "importance": self._score_importance(content),
            "tags": self._extract_tags(content),
            "refined_at": __import__("time").time(),
        }
        
        return refined
    
    def _clean_content(self, content: str) -> str:
        """清理内容"""
        # 去掉纠错标记
        content = content.replace("[纠错]", "").strip()
        # 去掉多余空白
        content = " ".join(content.split())
        # 截断过长内容
        if len(content) > 200:
            content = content[:200] + "..."
        return content
    
    def _infer_category(self, content: str, original: str) -> str:
        """推断分类"""
        if any(w in content for w in ["喜欢", "偏好", "习惯", "默认"]):
            return "preference"
        elif any(w in content for w in ["纠错", "不要", "别", "错"]):
            return "correction"
        elif any(w in content for w in ["是", "有", "在", "用"]):
            return "fact"
        return original or "general"
    
    def _score_importance(self, content: str) -> int:
        """评分重要性（1-5）"""
        score = 3  # 默认
        if any(w in content for w in ["重要", "必须", "核心", "关键"]):
            score = 5
        elif any(w in content for w in ["偏好", "习惯", "默认"]):
            score = 4
        elif any(w in content for w in ["纠错", "不要"]):
            score = 4
        return score
    
    def _extract_tags(self, content: str) -> List[str]:
        """提取标签"""
        tags = []
        tag_map = {
            "Python": "编程", "VS Code": "工具", "Claude": "AI模型",
            "MIMO": "AI模型", "飞书": "工具", "Telegram": "平台",
            "不死鸟": "系统", "Phoenix": "系统", "Hermes": "系统",
        }
        for keyword, tag in tag_map.items():
            if keyword in content:
                tags.append(tag)
        return tags

memory_refiner = MemoryRefiner()
