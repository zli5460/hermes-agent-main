import importlib.util
from pathlib import Path


def _load_action_ledger_module():
    repo_root = Path(__file__).resolve().parents[2]
    mod_path = repo_root / "phoenix-v8-release" / "security" / "action_ledger.py"
    spec = importlib.util.spec_from_file_location("phoenix_v8_action_ledger", mod_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_action_ledger_uses_profile_home(monkeypatch, tmp_path):
    module = _load_action_ledger_module()
    hermes_home = tmp_path / "profile-home"
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    ledger = module.ActionLedger()

    assert ledger.path == hermes_home / "phoenix" / "data" / "action_ledger.jsonl"


def test_pending_confirm_isolated_by_session_scope():
    from plugins import phoenix_full as mod

    mod._clear_all_pending_confirms()
    mod._set_pending_confirm("session:a", {"tier": "super_god", "action": None, "task": "A"})
    mod._set_pending_confirm("session:b", {"tier": "deep", "action": None, "task": "B"})

    assert mod._get_pending_confirm("session:a")["task"] == "A"
    assert mod._get_pending_confirm("session:b")["task"] == "B"

    mod._on_session_reset(session_id="a")
    assert mod._get_pending_confirm("session:a") is None
    assert mod._get_pending_confirm("session:b")["task"] == "B"

    mod._clear_all_pending_confirms()


def test_pre_tool_call_blocks_high_risk_in_super_god_confirm():
    from plugins import phoenix_full as mod

    mod._clear_all_pending_confirms()
    mod._task_scope_map.clear()
    mod._set_pending_confirm("session:test", {"tier": "super_god", "action": "confirm", "task": "/真神 任务"})
    mod._bind_task_scope("task-1", "session:test")

    blocked = mod._on_pre_tool_call(tool_name="terminal", args={}, task_id="task-1")
    assert isinstance(blocked, dict)
    assert blocked.get("action") == "block"

    allowed = mod._on_pre_tool_call(
        tool_name="terminal",
        args={"user_confirmed_high_risk": True},
        task_id="task-1",
    )
    assert allowed is None

    mod._clear_all_pending_confirms()
    mod._task_scope_map.clear()
