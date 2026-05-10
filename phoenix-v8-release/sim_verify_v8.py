#!/usr/bin/env python3
"""Phoenix V8 交付前静态验收：包完整性、敏感信息粗扫、install 引用、隔离 doctor。

不替代三家 OS 真机安装冒烟。用法：

  python3 sim_verify_v8.py              # 全量 + 打 zip + CHECKSUMS.txt
  python3 sim_verify_v8.py --no-zip     # 仅验证（CI 默认）
  python3 sim_verify_v8.py --output-dir /path/to/out

环境变量 PHOENIX_SIM_FAKE_HERMES=0 可改用系统 PATH 里的真实 hermes（可能因本机未装 Hermes 失败）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple

# 与 doctor.PhoenixDoctor._collect_phoenix_key_env_names 保持语义一致（验收用占位 .env）
def _collect_required_env_names(data: Dict) -> Set[str]:
    names: Set[str] = set()
    open_cfg = data.get("phoenix_open") if isinstance(data, dict) else None
    if not isinstance(open_cfg, dict):
        return names
    provs = open_cfg.get("providers") or {}
    if isinstance(provs, dict):
        for pc in provs.values():
            if not isinstance(pc, dict) or pc.get("is_local"):
                continue
            if pc.get("api_key") and str(pc.get("api_key")).strip():
                continue
            envn = pc.get("api_key_env")
            if isinstance(envn, str) and envn.strip():
                names.add(envn.strip())
    tiers = open_cfg.get("model_tiers") or {}
    if isinstance(tiers, dict):
        for t in tiers.values():
            if not isinstance(t, dict):
                continue
            for key in ("api_key_env", "api_key_env_a", "api_key_env_b"):
                envn = t.get(key)
                if isinstance(envn, str) and envn.strip():
                    names.add(envn.strip())
            for slot in ("fallback", "emergency"):
                sub = t.get(slot)
                if isinstance(sub, dict):
                    envn = sub.get("api_key_env")
                    if isinstance(envn, str) and envn.strip():
                        names.add(envn.strip())
    return names


REQUIRED_TOP_LEVEL = (
    "install.sh",
    "install.ps1",
    "doctor.py",
    "config.json",
    "feature_registry.json",
    "VERSION.md",
    "CHANGELOG.md",
    "plugins/phoenix_full/__init__.py",
    "plugins/phoenix_full/plugin.yaml",
    "不死鸟_Phoenix_V8_使用说明书.md",
    "不死鸟_Phoenix_V8_技术细则与路径原理.md",
)

INSTALL_MARKERS = (
    "不死鸟_Phoenix_V8_使用说明书.md",
    "Phoenix V8 compatibility",
    "CHANGELOG.md",
)

SECRET_PATTERNS_PY_JSON = (
    re.compile(r"sk-proj-[a-zA-Z0-9_-]{10,}"),
    re.compile(r"sk-ant-api[a-zA-Z0-9_-]{10,}"),
    re.compile(r"AIzaSy[a-zA-Z0-9_-]{20,}"),
    re.compile(r"xox[boprs]-[a-zA-Z0-9-]{10,}"),
)

SCAN_SUFFIXES = {".py", ".json", ".yaml", ".yml", ".sh", ".ps1"}
SKIP_NAMES = {".git", "__pycache__", ".pytest_cache", ".venv", ".venv-phx", "node_modules"}


def _fail(msg: str) -> None:
    print(f"❌ sim_verify_v8: {msg}", file=sys.stderr)


def _ok(msg: str) -> None:
    print(f"✅ {msg}")


def check_package_layout(root: Path) -> List[str]:
    errors: List[str] = []
    for rel in REQUIRED_TOP_LEVEL:
        if not (root / rel).is_file():
            errors.append(f"missing required file: {rel}")
    return errors


def scan_secrets(root: Path) -> List[str]:
    hits: List[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_NAMES]
        for fn in filenames:
            path = Path(dirpath) / fn
            if path.suffix.lower() not in SCAN_SUFFIXES:
                continue
            if path.name == "sim_verify_v8.py":
                continue
            try:
                if path.stat().st_size > 2_000_000:
                    continue
            except OSError:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for line_no, line in enumerate(text.splitlines(), 1):
                if "sim_verify_dummy" in line or "PLACEHOLDER" in line:
                    continue
                for pat in SECRET_PATTERNS_PY_JSON:
                    if pat.search(line):
                        hits.append(f"{path.relative_to(root)}:{line_no}: possible secret pattern")
                        break
    return hits


def check_install_scripts(root: Path) -> List[str]:
    errors: List[str] = []
    install_sh = root / "install.sh"
    if install_sh.is_file():
        text = install_sh.read_text(encoding="utf-8", errors="ignore")
        for m in INSTALL_MARKERS:
            if m not in text:
                errors.append(f"install.sh missing marker: {m!r}")
    install_ps1 = root / "install.ps1"
    if install_ps1.is_file():
        textp = install_ps1.read_text(encoding="utf-8", errors="ignore")
        if "Phoenix V8 compatibility" not in textp:
            errors.append("install.ps1 missing Phoenix V8 compatibility marker")
    return errors


def check_plugin_manual_triggers(root: Path) -> List[str]:
    init_py = root / "plugins" / "phoenix_full" / "__init__.py"
    if not init_py.is_file():
        return ["plugin __init__.py missing"]
    text = init_py.read_text(encoding="utf-8", errors="ignore")
    errs: List[str] = []
    for cmd in ("/深度", "/大神", "/真神"):
        if cmd not in text:
            errs.append(f"plugin missing manual trigger {cmd!r}")
    return errs


def _write_minimal_hermes_config(path: Path) -> None:
    import yaml  # type: ignore

    data = {
        "display": {"skin": "phoenix"},
        "memory": {"memory_enabled": True, "user_profile_enabled": True},
        "checkpoints": {"enabled": True},
        "compression": {"enabled": True},
        "privacy": {"redact_pii": True},
        "plugins": {"enabled": ["phoenix-full", "disk-cleanup"]},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _write_runtime_data_json(data_dir: Path) -> None:
    defaults = {
        "long_term_memory.json": [],
        "extracted_memories.json": [],
        "antibodies.json": [],
        "diary.json": [],
        "knowledge_graph.json": {"entities": [], "relations": []},
        "evolution.json": {
            "events": [],
            "model_performance": {},
            "compress_quality": [],
            "latency_history": [],
        },
        "state.json": {},
    }
    data_dir.mkdir(parents=True, exist_ok=True)
    for name, obj in defaults.items():
        p = data_dir / name
        if not p.exists():
            p.write_text(json.dumps(obj, ensure_ascii=False) + "\n", encoding="utf-8")


def _copy_plugin(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def run_isolated_doctor(pkg_root: Path) -> Tuple[int, str]:
    import yaml  # type: ignore

    cfg_data = json.loads((pkg_root / "config.json").read_text(encoding="utf-8"))
    env_names = _collect_required_env_names(cfg_data)

    with tempfile.TemporaryDirectory(prefix="phx_sim_verify_") as td:
        td_path = Path(td)
        hermes_home = td_path / "hermes"
        phoenix_home = hermes_home / "phoenix"
        fake_agent = td_path / "hermes-agent"

        shutil.copytree(
            pkg_root,
            phoenix_home,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
            dirs_exist_ok=False,
        )

        plug_src = phoenix_home / "plugins" / "phoenix_full"
        _copy_plugin(plug_src, fake_agent / "plugins" / "phoenix_full")
        _copy_plugin(plug_src, hermes_home / "plugins" / "phoenix_full")

        skin_src = phoenix_home / "_package_skins" / "phoenix.yaml"
        if not skin_src.is_file():
            skin_src = phoenix_home / "phoenix.yaml"
        skin_dst = hermes_home / "skins" / "phoenix.yaml"
        skin_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(skin_src, skin_dst)

        _write_minimal_hermes_config(hermes_home / "config.yaml")
        _write_runtime_data_json(phoenix_home / "data")

        lines = [f"{k}=sim_verify_dummy_not_a_real_key" for k in sorted(env_names)]
        (hermes_home / ".env").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

        fake_bin = td_path / "bin"
        fake_bin.mkdir()
        hermes_stub = fake_bin / "hermes"
        hermes_stub.write_text(
            """#!/bin/sh
if [ "$1" = "--help" ] || [ -z "$1" ]; then
  echo "Hermes Agent CLI (sim_verify stub)"
  exit 0
fi
if [ "$1" = "gateway" ]; then
  echo "gateway running (sim_verify stub)"
  exit 0
fi
exit 0
""",
            encoding="utf-8",
        )
        hermes_stub.chmod(0o755)

        env = os.environ.copy()
        env["PATH"] = str(fake_bin) + os.pathsep + env.get("PATH", "")
        if os.environ.get("PHOENIX_SIM_FAKE_HERMES", "1") == "0":
            env.pop("PATH", None)
            env["PATH"] = os.environ.get("PATH", "")

        proc = subprocess.run(
            [
                sys.executable,
                str(phoenix_home / "doctor.py"),
                "--verify",
                "--no-runtime",
                "--home",
                str(hermes_home),
                "--phoenix-home",
                str(phoenix_home),
                "--hermes-agent-dir",
                str(fake_agent),
            ],
            cwd=str(phoenix_home),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        out = (proc.stdout or "") + "\n" + (proc.stderr or "")
        return proc.returncode, out


def write_zip_and_checksums(pkg_root: Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / "phoenix-v8-release.zip"
    if zip_path.exists():
        zip_path.unlink()
    base = pkg_root.parent
    name = pkg_root.name
    shutil.make_archive(str(out_dir / "phoenix-v8-release"), "zip", root_dir=str(base), base_dir=name)
    assert zip_path.is_file()
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    (out_dir / "CHECKSUMS.txt").write_text(
        f"SHA256(phoenix-v8-release.zip)= {digest}\n", encoding="utf-8"
    )
    return zip_path


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phoenix V8 sim verify + optional release zip")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.home() / ".hermes" / "work" / "phoenix_v8_package_build",
        help="zip + CHECKSUMS output directory",
    )
    parser.add_argument("--no-zip", action="store_true", help="skip zip/checksums (verify only)")
    parser.add_argument("--package-root", type=Path, default=None, help="override package root")
    args = parser.parse_args(argv)

    pkg_root = (args.package_root or Path(__file__).resolve().parent).resolve()
    if not (pkg_root / "config.json").is_file():
        _fail(f"not a Phoenix package root: {pkg_root}")
        return 2

    errors: List[str] = []

    errors.extend(check_package_layout(pkg_root))
    errors.extend(check_install_scripts(pkg_root))
    errors.extend(check_plugin_manual_triggers(pkg_root))

    secret_hits = scan_secrets(pkg_root)
    if secret_hits:
        errors.extend(secret_hits[:50])
        if len(secret_hits) > 50:
            errors.append(f"... and {len(secret_hits) - 50} more secret scan hits")

    try:
        import yaml  # noqa: F401
    except ImportError:
        errors.append("PyYAML required for isolated doctor; pip install pyyaml")

    if errors:
        for e in errors:
            _fail(e)
        return 1

    _ok("package layout + install markers + plugin triggers + secret scan (py/json/yaml/sh)")

    try:
        code, doc_out = run_isolated_doctor(pkg_root)
    except Exception as exc:
        _fail(f"isolated doctor failed: {exc}")
        return 1

    if code != 0:
        _fail("doctor --verify (isolated) failed")
        print(doc_out, file=sys.stderr)
        return 1
    _ok("doctor --verify (isolated, --no-runtime) PASS")
    if "SUMMARY PASS" not in doc_out and "PASS" not in doc_out:
        print(doc_out)

    if not args.no_zip:
        try:
            zp = write_zip_and_checksums(pkg_root, args.output_dir)
            _ok(f"wrote {zp} and {args.output_dir / 'CHECKSUMS.txt'}")
        except Exception as exc:
            _fail(f"zip/checksums: {exc}")
            return 1
    else:
        _ok("--no-zip: skipped phoenix-v8-release.zip")

    print("sim_verify_v8: ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
