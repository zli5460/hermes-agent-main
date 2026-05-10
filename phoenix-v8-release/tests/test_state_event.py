import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.state import AppStateManager


class StateEventTest(unittest.TestCase):
    def test_dispatch_event_and_gc(self):
        mgr = AppStateManager()
        mgr.dispatch('update_budget', {'spent_month': 1.23})
        mgr.dispatch('update_context', {'size': 456})
        mgr.dispatch('emit_event', {'kind': 'test', 'source': 'unit', 'event_action': 'ping', 'payload': {'x': 1}})
        health = mgr.get_health_summary()
        self.assertEqual(health['context_size'], 456)
        self.assertIn('event_stream_size', health)
        self.assertGreaterEqual(health['budget_pct'].find('%'), 0)
        self.assertEqual(len(mgr.get_state().event_stream.tail(1)), 1)
        mgr.gc({'event_history_max': 1})
        self.assertLessEqual(len(mgr.get_state().event_stream), 1)


if __name__ == '__main__':
    unittest.main()
