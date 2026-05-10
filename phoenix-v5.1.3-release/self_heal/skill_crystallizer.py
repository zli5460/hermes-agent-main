"""不死鸟 Phoenix V5.1 — 自进化Skill结晶
来源: GenericAgent

每次解决新任务，自动结晶成Skill供下次复用。
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional

class SkillCrystallizer:
    """Skill结晶器 — 从任务执行中自动提取可复用Skill"""
    
    def __init__(self):
        self._data_dir = Path.home() / ".hermes" / "phoenix" / "data"
        self._crystals_file = self._data_dir / "skill_crystals.json"
        self._crystals = self._load()
    
    def crystallize(self, task: str, steps: List[str], result: str, success: bool) -> Optional[Dict]:
        """
        从任务执行中结晶Skill
        
        Args:
            task: 任务描述
            steps: 执行步骤
            result: 执行结果
            success: 是否成功
        
        Returns:
            结晶的Skill
        """
        if not success:
            return None
        
        # 提取模式
        pattern = self._extract_pattern(task, steps)
        
        # 检查是否已有相似Skill
        existing = self._find_similar(pattern)
        if existing:
            # 更新现有Skill的使用次数
            existing["uses"] = existing.get("uses", 0) + 1
            existing["last_used"] = time.time()
            self._save()
            return existing
        
        # 创建新Skill
        crystal = {
            "id": str(int(time.time() * 1000))[-8:],
            "pattern": pattern,
            "task": task,
            "steps": steps,
            "result_summary": result[:200],
            "uses": 1,
            "created": time.time(),
            "last_used": time.time(),
        }
        
        self._crystals.append(crystal)
        self._save()
        return crystal
    
    def recall(self, task: str) -> Optional[Dict]:
        """回忆相似任务的Skill"""
        pattern = self._extract_pattern(task, [])
        return self._find_similar(pattern)
    
    def _extract_pattern(self, task: str, steps: List[str]) -> str:
        """提取任务模式"""
        # 简单模式：取任务的前50个字符作为模式
        return task[:50].strip().lower()
    
    def _find_similar(self, pattern: str) -> Optional[Dict]:
        """查找相似Skill"""
        for crystal in self._crystals:
            if self._similarity(pattern, crystal["pattern"]) > 0.6:
                return crystal
        return None
    
    def _similarity(self, a: str, b: str) -> float:
        """简单相似度计算"""
        a_words = set(a.split())
        b_words = set(b.split())
        if not a_words or not b_words:
            return 0.0
        intersection = len(a_words & b_words)
        union = len(a_words | b_words)
        return intersection / union if union > 0 else 0.0
    
    def stats(self) -> Dict:
        """统计"""
        return {
            "total_crystals": len(self._crystals),
            "total_uses": sum(c.get("uses", 0) for c in self._crystals),
        }
    
    def _load(self):
        try:
            if self._crystals_file.exists():
                return json.loads(self._crystals_file.read_text())
        except Exception as exc:
            _ = exc
        return []
    
    def _save(self):
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._crystals_file.write_text(json.dumps(self._crystals, ensure_ascii=False, indent=2))

skill_crystallizer = SkillCrystallizer()
