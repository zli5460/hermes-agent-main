"""Phoenix Skills — 技能库（对接SkillCrystallizer）"""
import json
from pathlib import Path
from typing import Dict, List, Optional


class PhoenixSkills:
    """不死鸟技能库 — 从成功经验中结晶的可复用技能"""

    def __init__(self, data_dir: str = None):
        if data_dir is None:
            data_dir = str(Path.home() / ".hermes" / "phoenix" / "data")
        self._skills_file = Path(data_dir) / "phoenix_skills.json"
        self._skills = self._load()

    def _load(self) -> List[Dict]:
        try:
            if self._skills_file.exists():
                return json.loads(self._skills_file.read_text())
        except Exception as exc:
            _ = exc
        return []

    def _save(self):
        self._skills_file.parent.mkdir(parents=True, exist_ok=True)
        self._skills_file.write_text(json.dumps(self._skills, ensure_ascii=False, indent=2))

    def add_skill(self, name: str, description: str, trigger: str, steps: List[str]) -> Dict:
        """手动添加技能"""
        skill = {
            "name": name,
            "description": description,
            "trigger": trigger,
            "steps": steps,
            "uses": 0,
            "success_rate": 1.0,
        }
        self._skills.append(skill)
        self._save()
        return skill

    def recall(self, task_description: str) -> Optional[Dict]:
        """根据任务描述回忆相关技能"""
        task_lower = task_description.lower()
        for skill in self._skills:
            if any(kw in task_lower for kw in skill.get("trigger", "").lower().split(",")):
                skill["uses"] = skill.get("uses", 0) + 1
                self._save()
                return skill
        return None

    def get_all(self) -> List[Dict]:
        return self._skills

    def stats(self) -> Dict:
        return {
            "total_skills": len(self._skills),
            "total_uses": sum(s.get("uses", 0) for s in self._skills),
        }
