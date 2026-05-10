import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from memory.unified_memory import SessionMemory


class SessionMemoryTest(unittest.TestCase):
    def test_last_user_message_is_not_overwritten_by_other_keys(self):
        sm = SessionMemory(max_entries=10)
        sm.set('last_user_message', '原始消息', category='context', importance=1)
        sm.set('foo', 'bar', category='fact', importance=2)
        self.assertEqual(sm.get('last_user_message'), '原始消息')
        self.assertEqual(sm.get('foo'), 'bar')


if __name__ == '__main__':
    unittest.main()
