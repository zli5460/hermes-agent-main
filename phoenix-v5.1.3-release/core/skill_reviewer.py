"""
Phoenix V5.1 — 技能审稿机制（Skill Reviewer）

功能：
1. 新技能创建时自动评分
2. 定期检查技能库，合并相近技能
3. 裁剪长期未使用的死技能
4. 防止临时做法被写成长期规则
"""

import json
import os
import time
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional

SKILLS_DIR = Path.home() / ".hermes" / "skills"
REVIEW_LOG = Path.home() / ".hermes" / "phoenix" / "data" / "skill_review.json"


@dataclass
class SkillScore:
    """技能评分"""
    name: str
    path: str
    score: float
    usage_count: int
    last_used: float
    created_at: float
    status: str


class SkillReviewer:
    """技能审稿器"""

    def __init__(self):
        self.skills_dir = SKILLS_DIR
        self.review_log = REVIEW_LOG
        self.review_log.parent.mkdir(parents=True, exist_ok=True)

    def score_skill(self, skill_path: str) -> SkillScore:
        """给技能评分"""
        path = Path(skill_path)
        name = path.stem
        score = 50

        if path.exists():
            content = path.read_text(encoding="utf-8", errors="ignore")
            if len(content) > 100:
                score += 10
            if "SKILL.md" in str(path):
                score += 10
            if any(kw in content.lower() for kw in ["trigger", "使用", "用法", "example"]):
                score += 10
            if len(content) > 500:
                score += 10
            if content.count("\n") > 10:
                score += 10

        usage = self._get_usage_count(name)
        score += min(usage * 2, 20)

        return SkillScore(
            name=name, path=str(path), score=min(score, 100),
            usage_count=usage, last_used=self._get_last_used(name),
            created_at=path.stat().st_mtime if path.exists() else 0,
            status="active"
        )

    def review_all(self) -> List[SkillScore]:
        """审稿所有技能"""
        scores = []
        for skill_file in self.skills_dir.rglob("*.md"):
            if skill_file.name == "README.md":
                continue
            scores.append(self.score_skill(str(skill_file)))
        scores.sort(key=lambda x: x.score, reverse=True)
        self._save_review(scores)
        return scores

    def find_duplicates(self, scores: List[SkillScore]) -> List[List[SkillScore]]:
        """查找重复技能"""
        duplicates = []
        checked = set()
        for i, s1 in enumerate(scores):
            if s1.name in checked:
                continue
            group = [s1]
            for s2 in scores[i+1:]:
                if s2.name in checked:
                    continue
                if self._are_similar(s1, s2):
                    group.append(s2)
                    checked.add(s2.name)
            if len(group) > 1:
                duplicates.append(group)
                checked.add(s1.name)
        return duplicates

    def prune_dead_skills(self, scores: List[SkillScore], threshold: int = 30) -> List[str]:
        """裁剪死技能"""
        pruned = []
        now = time.time()
        for score in scores:
            if score.score < threshold and (now - score.last_used) > 30 * 86400:
                pruned.append(score.name)
        return pruned

    def _are_similar(self, s1: SkillScore, s2: SkillScore) -> bool:
        """判断两个技能是否相似"""
        name1 = set(s1.name.lower().replace("-", "").replace("_", ""))
        name2 = set(s2.name.lower().replace("-", "").replace("_", ""))
        intersection = name1 & name2
        union = name1 | name2
        return len(intersection) / len(union) > 0.5 if union else False

    def _get_usage_count(self, skill_name: str) -> int:
        try:
            if self.review_log.exists():
                data = json.loads(self.review_log.read_text())
                return data.get("usage", {}).get(skill_name, 0)
        except Exception as exc:
            _ = exc
        return 0

    def _get_last_used(self, skill_name: str) -> float:
        try:
            if self.review_log.exists():
                data = json.loads(self.review_log.read_text())
                return data.get("last_used", {}).get(skill_name, 0)
        except Exception as exc:
            _ = exc
        return 0

    def _save_review(self, scores: List[SkillScore]):
        data = {
            "last_review": time.time(),
            "total_skills": len(scores),
            "avg_score": sum(s.score for s in scores) / len(scores) if scores else 0,
            "skills": [asdict(s) for s in scores[:20]]
        }
        self.review_log.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    def get_report(self) -> str:
        """获取审稿报告"""
        scores = self.review_all()
        duplicates = self.find_duplicates(scores)
        dead = self.prune_dead_skills(scores)

        lines = [
            "📊 Phoenix技能审稿报告",
            f"   总技能数: {len(scores)}",
            f"   平均分: {sum(s.score for s in scores) / len(scores):.1f}" if scores else "   平均分: 0",
            f"   重复技能: {len(duplicates)}组",
            f"   死技能: {len(dead)}个",
            ""
        ]

        if duplicates:
            lines.append("⚠️ 重复技能:")
            for group in duplicates:
                lines.append(f"   {', '.join(s.name for s in group)}")

        if dead:
            lines.append("🗑️ 建议裁剪:")
            for name in dead:
                lines.append(f"   {name}")

        return "\n".join(lines)
