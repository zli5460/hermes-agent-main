"""
Phoenix V5.1 — 渐进式技能加载器（Progressive Skill Loader）

功能：
1. 技能只在需要时加载（已有lazy_load）
2. 新增：缓存已加载技能，避免重复加载
3. 新增：技能优先级排序，常用技能自动提升
"""

import json
import time
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass

SKILLS_CACHE = Path.home() / ".hermes" / "phoenix" / "data" / "skills_cache.json"


@dataclass
class CachedSkill:
    """缓存的技能"""
    name: str
    path: str
    score: float
    last_used: float
    use_count: int


class ProgressiveSkillLoader:
    """渐进式技能加载器"""

    def __init__(self, skills_dir: str):
        self.skills_dir = Path(skills_dir)
        self.cache_file = SKILLS_CACHE
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self._cache = self._load_cache()

    def _load_cache(self) -> Dict[str, CachedSkill]:
        """加载技能缓存"""
        try:
            if self.cache_file.exists():
                data = json.loads(self.cache_file.read_text())
                return {k: CachedSkill(**v) for k, v in data.items()}
        except Exception as exc:
            _ = exc
        return {}

    def _save_cache(self):
        """保存技能缓存"""
        data = {k: {"name": v.name, "path": v.path, "score": v.score,
                     "last_used": v.last_used, "use_count": v.use_count}
                for k, v in self._cache.items()}
        self.cache_file.write_text(json.dumps(data, indent=2))

    def load_skill(self, skill_path: str) -> Optional[dict]:
        """加载技能（带缓存）"""
        path = Path(skill_path)

        # 检查缓存
        if str(path) in self._cache:
            cached = self._cache[str(path)]
            cached.last_used = time.time()
            cached.use_count += 1
            self._save_cache()
            return {"name": cached.name, "path": cached.path, "cached": True}

        # 缓存未命中，加载技能
        if not path.exists():
            return None

        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            skill = {"name": path.stem, "path": str(path), "content": content[:2000]}

            # 加入缓存
            self._cache[str(path)] = CachedSkill(
                name=path.stem, path=str(path),
                score=50, last_used=time.time(), use_count=1
            )
            self._save_cache()

            return skill
        except Exception:
            return None

    def get_popular_skills(self, limit: int = 10) -> List[CachedSkill]:
        """获取常用技能（按使用次数排序）"""
        skills = sorted(self._cache.values(), key=lambda x: x.use_count, reverse=True)
        return skills[:limit]

    def cleanup_cache(self, max_age_days: int = 30):
        """清理过期缓存"""
        now = time.time()
        to_remove = []
        for path, skill in self._cache.items():
            if (now - skill.last_used) > max_age_days * 86400:
                to_remove.append(path)

        for path in to_remove:
            del self._cache[path]

        self._save_cache()
        return len(to_remove)

    def get_stats(self) -> str:
        """获取缓存统计"""
        total = len(self._cache)
        if total == 0:
            return "📊 技能缓存: 空"

        avg_use = sum(s.use_count for s in self._cache.values()) / total
        popular = self.get_popular_skills(3)

        lines = [
            f"📊 技能缓存统计",
            f"   缓存技能数: {total}",
            f"   平均使用次数: {avg_use:.1f}",
            f"   最常用: {', '.join(s.name for s in popular)}"
        ]
        return "\n".join(lines)
