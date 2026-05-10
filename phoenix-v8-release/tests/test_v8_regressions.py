#!/usr/bin/env python3
"""Phoenix V8 focused regression tests.

Covers student-reported bugs that must not come back:
- runtime JSON wrong shape ([] for dict files)
- stale Hermes agent thread/process detection
- Gateway self-heal restart path
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from doctor import PhoenixDoctor


def test_runtime_data_wrong_shape_auto_fix():
    with tempfile.TemporaryDirectory() as td:
        home = Path(td) / "home"
        phoenix = home / "phoenix"
        data = phoenix / "data"
        data.mkdir(parents=True)
        (data / "knowledge_graph.json").write_text("[]", encoding="utf-8")
        (data / "evolution.json").write_text("[]", encoding="utf-8")

        doctor = PhoenixDoctor(hermes_home=home, phoenix_home=phoenix, verify_runtime=False)
        report = doctor.run(apply_fixes=True)

        kg = json.loads((data / "knowledge_graph.json").read_text(encoding="utf-8"))
        ev = json.loads((data / "evolution.json").read_text(encoding="utf-8"))
        assert isinstance(kg, dict) and "entities" in kg and "relations" in kg
        assert isinstance(ev, dict) and "events" in ev and "model_performance" in ev
        assert any(f.kind == "repair_runtime_data" for f in report.fixes)


def test_stale_agent_thread_detection():
    with tempfile.TemporaryDirectory() as td:
        home = Path(td) / "home"
        (home / "logs").mkdir(parents=True)
        (home / "logs" / "errors.log").write_text(
            "Agent thread still alive after interrupt\n", encoding="utf-8"
        )
        doctor = PhoenixDoctor(hermes_home=home, phoenix_home=home / "phoenix", verify_runtime=False)
        doctor._scan_hermes_processes = lambda: [
            {
                "pid": 999999,
                "etime": "1-00:00:00",
                "command": f"{home}/hermes-agent/venv/bin/python3 {home}/.local/bin/hermes",
            }
        ]
        issues = []
        doctor._check_stale_agent_processes(issues)
        assert issues
        assert issues[0].kind == "stale_hermes_process"
        assert issues[0].repairable is True


def test_gateway_self_heal_restart_path():
    with tempfile.TemporaryDirectory() as td:
        home = Path(td) / "home"
        doctor = PhoenixDoctor(hermes_home=home, phoenix_home=home / "phoenix", verify_runtime=False)
        doctor._gateway_status = lambda: "Gateway not running"
        issues = []
        doctor._check_gateway(issues)
        assert issues and issues[0].kind == "gateway_not_running"

        called = []
        doctor._repair_gateway = lambda: called.append("restart") or []
        fixes = doctor.auto_fix(issues)
        assert called == ["restart"]
        assert fixes == []


def test_gateway_loaded_with_pid_is_ok():
    with tempfile.TemporaryDirectory() as td:
        home = Path(td) / "home"
        doctor = PhoenixDoctor(hermes_home=home, phoenix_home=home / "phoenix", verify_runtime=False)
        doctor._gateway_status = lambda: "Service definition matches\nGateway service is loaded\nPID = 12345\nLastExitStatus = 15"
        issues = []
        doctor._check_gateway(issues)
        assert issues == []


if __name__ == "__main__":
    test_runtime_data_wrong_shape_auto_fix()
    test_stale_agent_thread_detection()
    test_gateway_self_heal_restart_path()
    test_gateway_loaded_with_pid_is_ok()
    print("Phoenix V8 regression tests PASS")
