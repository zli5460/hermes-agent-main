#!/usr/bin/env python3
"""
Phoenix V5.1 Auto-Fusion Script
================================
Hermes升级后自动运行，扫描所有原生能力，对比Feature Registry，
自动激活/配置未融合的功能。

用法：
  python3 ~/.hermes/phoenix/auto_fusion.py           # 扫描+报告
  python3 ~/.hermes/phoenix/auto_fusion.py --apply    # 扫描+自动融合
  python3 ~/.hermes/phoenix/auto_fusion.py --report   # 仅输出报告
"""

import json
import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path

HERMES_HOME = Path.home() / ".hermes"
PHOENIX_DIR = HERMES_HOME / "phoenix"
REGISTRY_PATH = PHOENIX_DIR / "feature_registry.json"
CONFIG_PATH = HERMES_HOME / "config.yaml"
HERMES_AGENT = HERMES_HOME / "hermes-agent"


def detect_hermes_agent_dir():
    candidates = [
        Path(os.environ.get("HERMES_AGENT_DIR", "")) if os.environ.get("HERMES_AGENT_DIR") else None,
        HERMES_HOME / "hermes-agent",
        Path.home() / ".hermes" / "hermes-agent",
        Path("/mnt/projects/hermes-agent"),
        Path.home() / "projects" / "hermes-agent",
        Path.home() / "Desktop" / "hermes-agent",
    ]
    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate
    return HERMES_HOME / "hermes-agent"

# ============================================================
# 1. 扫描Hermes原生能力
# ============================================================

def scan_hermes_features():
    """扫描当前Hermes安装的所有原生能力"""
    global HERMES_AGENT
    HERMES_AGENT = detect_hermes_agent_dir()
    features = {
        "toolsets": set(),
        "plugins": set(),
        "config_keys": set(),
        "slash_commands": set(),
    }

    # 扫描工具集
    try:
        sys.path.insert(0, str(HERMES_AGENT))
        from venv_fix import activate_venv
    except ImportError:
        pass

    venv_python = HERMES_AGENT / "venv" / "bin" / "python3"
    if not venv_python.exists():
        venv_python = Path(sys.executable)

    # 用子进程扫描，避免导入冲突
    scan_code = '''
import sys, json, os
sys.path.insert(0, "{hermes_agent}")

# 扫描工具集
toolsets = {{}}
try:
    from toolsets import TOOLSETS
    for name, info in TOOLSETS.items():
        tools = info.get("tools", [])
        toolsets[name] = len(tools)
except Exception as e:
    toolsets["_error"] = str(e)

# 扫描插件
from pathlib import Path
plugins = {{}}
plugins_dir = "{hermes_agent}/plugins"
if os.path.isdir(plugins_dir):
    for d in sorted(os.listdir(plugins_dir)):
        pdir = Path(plugins_dir) / d
        if os.path.isdir(pdir) and not d.startswith("_"):
            yaml_path = pdir / "plugin.yaml"
            if os.path.exists(yaml_path):
                plugins[d] = True

# 扫描配置键
config_keys = {{}}
try:
    from hermes_cli.config import DEFAULT_CONFIG
    def flatten(d, prefix=""):
        for k, v in d.items():
            key = f"{{prefix}}.{{k}}" if prefix else k
            if isinstance(v, dict):
                flatten(v, key)
            else:
                config_keys[key] = str(v)[:50]
    flatten(DEFAULT_CONFIG)
except Exception as e:
    config_keys["_error"] = str(e)

print(json.dumps({{
    "toolsets": toolsets,
    "plugins": plugins,
    "config_keys": config_keys,
}}))
'''.format(hermes_agent=str(HERMES_AGENT))

    try:
        result = subprocess.run(
            [str(venv_python), "-c", scan_code],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
        stderr = (result.stderr or "").strip()
        if stderr:
            print(f"⚠️  Hermes扫描子进程失败: {stderr[:300]}")
    except Exception as e:
        print(f"⚠️  扫描失败: {e}")

    return None


# ============================================================
# 2. 对比Registry
# ============================================================

def load_registry():
    """加载Phoenix Feature Registry"""
    if REGISTRY_PATH.exists():
        with open(REGISTRY_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("categories"):
            return data
    return None


def compare_features(scan_result, registry):
    """对比扫描结果和注册表，找出未融合的功能"""
    if not scan_result or not registry:
        return None

    unfused = []
    fused = []
    unknown = []

    categories = registry.get("categories", {})

    for cat_name, cat_data in categories.items():
        for feat_name, feat_info in cat_data.get("features", {}).items():
            status = feat_info.get("status", "unknown")
            if status == "integrated":
                fused.append(f"{cat_name}.{feat_name}")
            elif status == "skipped":
                pass  # 明确跳过的不报告
            else:
                # 检查这个功能在Hermes中是否存在
                exists = False
                if cat_name in ("core_tools", "display"):
                    exists = feat_name in scan_result.get("toolsets", {})
                elif cat_name == "plugins":
                    exists = feat_name.replace("_", "-") in scan_result.get("plugins", {}) or \
                             feat_name.replace("_", "_") in scan_result.get("plugins", {})
                elif cat_name in ("subsystems", "slash_commands"):
                    # 子系统和命令通过配置键判断
                    for key in scan_result.get("config_keys", {}):
                        if feat_name.split("_")[0] in key:
                            exists = True
                            break

                if exists:
                    unfused.append({
                        "category": cat_name,
                        "feature": feat_name,
                        "priority": feat_info.get("priority", "P2"),
                        "notes": feat_info.get("notes", ""),
                    })
                else:
                    unknown.append(f"{cat_name}.{feat_name}")

    return {
        "fused": fused,
        "unfused": unfused,
        "unknown": unknown,
        "total_fused": len(fused),
        "total_unfused": len(unfused),
    }


# ============================================================
# 3. 自动融合
# ============================================================

# P0配置项：自动融合时写入config.yaml
P0_CONFIGS = {
    "compression.enabled": "true",
    "compression.threshold": "0.5",
    "compression.target_ratio": "0.2",
    "compression.protect_last_n": "20",
    "checkpoints.enabled": "true",
    "checkpoints.max_snapshots": "50",
    "checkpoints.retention_days": "7",
    "tool_loop_guardrails.warnings_enabled": "true",
    "tool_loop_guardrails.hard_stop_enabled": "true",
    "tool_loop_guardrails.warn_after.exact_failure": "2",
    "tool_loop_guardrails.warn_after.same_tool_failure": "3",
    "tool_loop_guardrails.hard_stop_after.exact_failure": "5",
    "tool_loop_guardrails.hard_stop_after.same_tool_failure": "8",
    "display.runtime_footer.enabled": "true",
    "display.runtime_footer.fields": "['model', 'context_pct', 'cwd']",
    "sessions.auto_prune": "true",
    "sessions.retention_days": "90",
    "curator.enabled": "true",
    "curator.interval_hours": "168",
    "disk_cleanup": "planned_v5.1",
    "kanban.dispatch_in_gateway": "true",
}

def apply_fusion():
    """自动融合P0配置（安全模式：只报告不执行）"""
    print("⚠️  --apply模式已改为安全模式：只报告不执行")
    print("   如需实际执行，请手动运行 hermes config set")
    return []
    print("\n🔥 开始自动融合...")

    applied = []
    for key, value in P0_CONFIGS.items():
        if value.startswith("TODO"):
            print(f"  ⏳ {key} — {value}")
            continue

        try:
            result = subprocess.run(
                ["hermes", "config", "set", key, value],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                applied.append(key)
                print(f"  ✅ {key} = {value}")
            else:
                print(f"  ⚠️  {key} — {result.stderr.strip()}")
        except Exception as e:
            print(f"  ❌ {key} — {e}")

    return applied


def update_registry(scan_result, applied_keys):
    """更新Registry状态"""
    registry = load_registry()
    if not registry:
        return

    registry["_meta"]["last_scan"] = datetime.now().strftime("%Y-%m-%d")
    registry["_meta"]["hermes_version"] = get_hermes_version()

    # 将已融合的P0配置标记为integrated
    for key in applied_keys:
        parts = key.split(".")
        cat = "subsystems" if parts[0] in (
            "compression", "checkpoints", "tool_loop_guardrails",
            "sessions", "curator", "fallback", "prompt_caching"
        ) else "display" if parts[0] == "display" else "slash_commands"

        feat = parts[0] if parts[0] not in registry.get("categories", {}).get(cat, {}).get("features", {}) else parts[0]
        if cat in registry.get("categories", {}) and feat in registry["categories"][cat].get("features", {}):
            registry["categories"][cat]["features"][feat]["status"] = "integrated"

    with open(REGISTRY_PATH, "w") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)

    print(f"\n📝 Registry已更新 (hermes {registry['_meta']['hermes_version']})")


def get_hermes_version():
    try:
        result = subprocess.run(
            ["hermes", "version"], capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.split("\n"):
            if "v" in line:
                return line.strip().split("(")[0].replace("Hermes Agent", "").strip()
    except Exception as exc:
        _ = exc
    return "unknown"


# ============================================================
# 4. 报告生成
# ============================================================

def print_report(scan_result, comparison):
    """输出完整报告"""
    version = get_hermes_version()
    registry = load_registry()
    last_scan = registry["_meta"]["last_scan"] if registry else "never"
    last_version = registry["_meta"]["hermes_version"] if registry else "unknown"

    print("=" * 60)
    print(f"🔥 Phoenix V5.1 Auto-Fusion Report")
    print(f"{'=' * 60}")
    print(f"  Hermes版本:     {version}")
    print(f"  上次扫描:       {last_scan}")
    print(f"  上次Hermes版本: {last_version}")
    print(f"{'=' * 60}")

    if version != last_version and last_version != "unknown":
        print(f"\n⚡ Hermes已从 {last_version} 升级到 {version}")
        print(f"   检测到新版本，需要融合新功能")

    if scan_result:
        print(f"\n📊 扫描结果:")
        print(f"  工具集:   {len(scan_result.get('toolsets', {}))} 个")
        print(f"  插件:     {len(scan_result.get('plugins', {}))} 个")
        print(f"  配置键:   {len(scan_result.get('config_keys', {}))} 个")

    if comparison:
        print(f"\n🔥 融合状态:")
        print(f"  ✅ 已融合:  {comparison['total_fused']} 个")
        print(f"  ⏳ 待融合:  {comparison['total_unfused']} 个")
        print(f"  ❓ 未知:    {len(comparison['unknown'])} 个")

        if comparison["unfused"]:
            print(f"\n⏳ 待融合列表 (按优先级):")
            for p in ["P0", "P1", "P2"]:
                items = [i for i in comparison["unfused"] if i["priority"] == p]
                if items:
                    print(f"\n  [{p}]")
                    for item in items:
                        print(f"    • {item['category']}.{item['feature']}")
                        print(f"      {item['notes']}")

    fusion_pct = (comparison["total_fused"] / max(comparison["total_fused"] + comparison["total_unfused"], 1)) * 100
    print(f"\n{'=' * 60}")
    print(f"  融合度: {fusion_pct:.0f}% ({comparison['total_fused']}/{comparison['total_fused'] + comparison['total_unfused']})")
    print(f"{'=' * 60}\n")


# ============================================================
# Main
# ============================================================

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--scan"

    print("🔥 Phoenix V5.1 Auto-Fusion Engine")
    print("   扫描Hermes原生能力...\n")

    scan_result = scan_hermes_features()
    registry = load_registry()

    if not scan_result:
        print("❌ 扫描失败，无法连接Hermes")
        sys.exit(1)

    if not registry:
        print(f"⚠️  未找到有效 feature_registry.json: {REGISTRY_PATH}")
        print("   这通常表示安装器没有把注册表带进来，先修复安装再看融合报告。")
        comparison = {"fused": [], "unfused": [], "unknown": [], "total_fused": 0, "total_unfused": 0}
    else:
        comparison = compare_features(scan_result, registry)

    if mode == "--apply":
        print_report(scan_result, comparison)
        applied = apply_fusion()
        update_registry(scan_result, applied)
        print(f"\n✅ 融合完成，应用了 {len(applied)} 项配置")

    elif mode == "--report":
        print_report(scan_result, comparison)

    else:  # --scan
        print_report(scan_result, comparison)
        print("💡 使用 --apply 自动融合P0配置")
        print("💡 使用 --report 仅输出报告")


if __name__ == "__main__":
    main()
