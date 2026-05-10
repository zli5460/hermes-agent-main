import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from phoenix import Phoenix
from executor.skill_loader import SkillLoader


class SkillSystemTest(unittest.TestCase):
    def test_skill_loader_hits_core_phoenix_skills(self):
        phoenix = Phoenix()
        loader = phoenix.skill_loader
        self.assertIn('phoenix-v2-architecture', loader.to_prompt('继续把整个V2跑完整了', 'reasoning'))
        self.assertIn('phoenix-v2-memory-loop', loader.to_prompt('记忆闭环怎么做', 'memory'))
        self.assertIn('phoenix-v2-state-event', loader.to_prompt('状态与事件流怎么管', 'state'))
        self.assertIn('phoenix-v2-self-heal', loader.to_prompt('错误处理和自愈', 'reasoning'))

    def test_skill_loader_can_load_skills_without_phoenix_keywords(self):
        loader = SkillLoader(str(Path.home() / '.hermes' / 'skills'))
        prompt = loader.to_prompt('我要做记忆闭环和自愈系统', 'reasoning')
        self.assertIn('phoenix-v2-memory-loop', prompt)
        self.assertIn('phoenix-v2-self-heal', prompt)


if __name__ == '__main__':
    unittest.main()
