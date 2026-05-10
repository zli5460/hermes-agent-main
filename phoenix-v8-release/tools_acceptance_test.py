#!/usr/bin/env python3
"""
Phoenix V8 full acceptance test.
本脚本只做离线/本地验证，不触发真实付费模型。
"""
import json
import os
import py_compile
import re
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path.home() / ".hermes" / "phoenix"
BUNDLED = Path.home() / ".hermes" / "hermes-agent" / "plugins" / "phoenix_full"
SKIN = Path.home() / ".hermes" / "skins" / "phoenix.yaml"

sys.path.insert(0, str(ROOT))

results = []

def ok(name, detail=""):
    results.append((True, name, detail))


def fail(name, detail=""):
    results.append((False, name, detail))


def check(name, cond, detail=""):
    ok(name, detail) if cond else fail(name, detail)

# 1. Core files
for rel in [
    "phoenix.py", "core/config.py", "core/state.py", "core/task.py",
    "router/engine.py", "router/router.py", "executor/pipeline.py",
    "memory/memory_system.py", "memory/structured_memory.py",
    "self_heal/antibody.py", "self_heal/error_processor.py",
    "security/approval.py", "integration/hooks.py",
    "plugins/phoenix_full/__init__.py", "plugins/phoenix_full/plugin.yaml",
    "install.sh", "install.ps1",
]:
    check(f"file_exists:{rel}", (ROOT / rel).exists(), str(ROOT / rel))

# 2. Compile all current source py except runtime/archives/data caches
compiled = 0
compile_errors = []
for p in ROOT.rglob("*.py"):
    s = str(p)
    if any(x in s for x in ["/__pycache__/", "/data/", "/_archive", "/_archived_islands/", "/release_v4/"]):
        continue
    try:
        py_compile.compile(str(p), doraise=True)
        compiled += 1
    except Exception as e:
        compile_errors.append(f"{p.relative_to(ROOT)}: {e}")
check("python_compile", not compile_errors, f"compiled={compiled}; errors={compile_errors[:5]}")

# 3. Memory system behavior
try:
    from memory.memory_system import MemorySystem
    from memory.structured_memory import StructuredMemory
    base = Path(tempfile.mkdtemp(prefix="phoenix_accept_mem_"))
    ms = MemorySystem(str(base / "memory"))
    for i in range(12):
        ms.add_to_short_term("user", f"msg{i}")
    r1 = ms.process_message("user", "记住：安装包不能泄露API Key")
    r2 = ms.process_message("user", "你刚才说错了，不要这样")
    facts = json.loads((base / "memory" / "facts.json").read_text())
    check("memory_three_layer", len(ms.short_term) == 10 and r1 == "permanent" and r2 == "correction", f"short={len(ms.short_term)}, r1={r1}, r2={r2}")
    check("memory_persist", bool(facts.get("facts")) and bool(facts.get("corrections")), f"facts={len(facts.get('facts', []))}, corrections={len(facts.get('corrections', []))}")
    sm = StructuredMemory(str(base / "structured"))
    sm.update_work_context("发布包验收")
    sm.add_fact("用户要求一键安装", "requirement", 0.95)
    prompt = sm.get_context_prompt()
    check("structured_memory", "用户要求一键安装" in prompt and "发布包验收" in prompt, prompt[:120])
except Exception as e:
    fail("memory_system_exception", repr(e))

# 4. Self-heal modules instantiate
try:
    from self_heal.antibody import AntibodyLibrary
    from self_heal.error_processor import ErrorProcessor
    from self_heal.failure_tracker import FailureTracker
    from self_heal.fault_playbook import FaultPlaybook
    tmp = Path(tempfile.mkdtemp(prefix="phoenix_accept_heal_"))
    ab = AntibodyLibrary(str(tmp / "antibodies.json"))
    ft = FailureTracker(threshold=3)
    fp = FaultPlaybook(root=str(tmp))
    check("self_heal_present", ab is not None and ft is not None and fp is not None, "antibody/failure/faultplaybook instantiated")
except Exception as e:
    fail("self_heal_exception", repr(e))

# 5. Plugin routing A-scheme: only three slash commands
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location("phoenix_full_accept", ROOT / "plugins/phoenix_full/__init__.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    samples = {
        "深度学习是什么？": None,
        "帮我分析这张图": None,
        "架构设计要注意什么": None,
        "/深度 帮我分析商业模式": "deep",
        "/大神 设计系统架构": "god",
        "/真神 做全盘战略": "super_god",
    }
    raw = {k: mod._detect_high_tier(k) for k in samples}
    got = {k: (v[0] if isinstance(v, tuple) else v) for k, v in raw.items()}
    check("routing_a_scheme", got == samples, json.dumps(got, ensure_ascii=False))
    c = (ROOT / "plugins/phoenix_full/__init__.py").read_text()
    check("plugin_cost_estimator", "_estimate_cost" in c and "_MODEL_PRICING" in c, "real estimate funcs present")
except Exception as e:
    fail("routing_plugin_exception", repr(e))

# 6. Bundled sync/plugin yaml hooks
try:
    src_init = (ROOT / "plugins/phoenix_full/__init__.py").read_text()
    b_init = (BUNDLED / "__init__.py").read_text()
    check("bundled_init_synced", src_init == b_init, "source vs bundled __init__.py")
    src_yaml = (ROOT / "plugins/phoenix_full/plugin.yaml").read_text()
    b_yaml = (BUNDLED / "plugin.yaml").read_text()
    check("bundled_yaml_has_gateway_hook", "pre_gateway_dispatch" in b_yaml, "bundled plugin.yaml hooks")
except Exception as e:
    fail("bundled_sync_exception", repr(e))

# 7. Skin: no fixed version
try:
    s = SKIN.read_text()
    version_pats = [r"V\d+(?:\.\d+)+", r"v\d+(?:\.\d+)+"]
    has_version = any(re.search(p, s) for p in version_pats)
    check("skin_no_fixed_version", not has_version and "Phoenix" in s, s)
except Exception as e:
    fail("skin_exception", repr(e))

# 8. Installer baseline safety/automation signals
try:
    sh = (ROOT / "install.sh").read_text()
    ps = (ROOT / "install.ps1").read_text()
    check("installer_has_interaction", ("read -r -p" in sh or "read -p" in sh) and ("read -r -s -p" in sh or "read -sp" in sh) and "Read-Host" in ps, "interactive prompts found")
    check("installer_sets_skin_memory", "display.skin phoenix" in sh and "memory.memory_enabled true" in sh, "skin+memory config")
    check("installer_no_embedded_secret_pattern", not re.search(r"sk-[A-Za-z0-9]{20,}|AIza[\w-]{20,}|xai-[\w-]{20,}", sh + ps), "no obvious embedded API keys")
    check("installer_gateway_restart", ("hermes gateway restart" in sh or "hermes gateway start" in sh or "hermes restart" in sh), "gateway restart command present")
except Exception as e:
    fail("installer_exception", repr(e))

# 9. Secret/personal/runtime scan in source critical package candidates
try:
    issues = []
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        s = str(p)
        if any(x in s for x in ["/__pycache__/", "/data/", "/.git/", "/_archived_islands/"]):
            continue
        if p.suffix.lower() not in [".py", ".yaml", ".yml", ".json", ".md", ".sh", ".ps1", ""]:
            continue
        try:
            txt = p.read_text(errors="ignore")
        except Exception:
            continue
        if re.search(r"sk-[A-Za-z0-9]{25,}|AIza[\w-]{25,}", txt):
            issues.append(f"secret:{p.relative_to(ROOT)}")
        personal_markers = ["12321572" + "@" + "qq.com"]
        if any(x in txt for x in personal_markers):
            issues.append(f"personal:{p.relative_to(ROOT)}")
    check("source_secret_scan", not issues, str(issues[:20]))
except Exception as e:
    fail("source_scan_exception", repr(e))

passed = sum(1 for r in results if r[0])
total = len(results)
for success, name, detail in results:
    print(("✅" if success else "❌"), name, "::", detail)
print(f"\nSUMMARY {passed}/{total} passed")
if passed != total:
    sys.exit(1)
