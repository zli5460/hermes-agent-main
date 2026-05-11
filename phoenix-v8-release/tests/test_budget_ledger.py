import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from security.action_ledger import ActionLedger
from security.budget_guard import BudgetGuard, BudgetGuardExceeded


class BudgetAndLedgerTest(unittest.TestCase):
    def test_budget_guard_blocks_excess_steps(self):
        guard = BudgetGuard(max_steps=2, max_visual_calls=1, max_cost_usd=1.0)
        guard.gate()
        guard.gate()
        with self.assertRaises(BudgetGuardExceeded):
            guard.gate()

    def test_budget_guard_blocks_excess_cost(self):
        guard = BudgetGuard(max_steps=10, max_visual_calls=3, max_cost_usd=0.3, enforce_cost_limit=True)
        guard.gate(estimated_cost_usd=0.2)
        guard.add_cost(0.2)
        with self.assertRaises(BudgetGuardExceeded):
            guard.gate(estimated_cost_usd=0.2)

    def test_budget_guard_does_not_block_cost_when_disabled(self):
        guard = BudgetGuard(max_steps=10, max_visual_calls=3, max_cost_usd=0.1, enforce_cost_limit=False)
        guard.gate(estimated_cost_usd=1.0)
        guard.add_cost(1.0)
        snap = guard.snapshot()
        self.assertFalse(snap["enforce_cost_limit"])

    def test_action_ledger_redacts_sensitive_metadata(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            ledger_path = Path(tmp_dir) / "action_ledger.jsonl"
            ledger = ActionLedger(ledger_path)
            ledger.append(
                "pipeline.model_call",
                "success",
                metadata={
                    "api_key": "abc123",
                    "token": "xyz",
                    "safe": "ok",
                },
            )
            row = json.loads(ledger_path.read_text(encoding="utf-8").strip())
            self.assertEqual(row["metadata"]["api_key"], "[REDACTED]")
            self.assertEqual(row["metadata"]["token"], "[REDACTED]")
            self.assertEqual(row["metadata"]["safe"], "ok")


if __name__ == "__main__":
    unittest.main()
