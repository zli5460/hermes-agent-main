#!/usr/bin/env python3
"""Phoenix installation doctor.

Verify -> Auto-Fix -> Restart -> Re-Verify 的前半段：
- 检查 Phoenix 文件、插件、皮肤、配置
- 自动修复可恢复问题
- 可选运行时自检

默认面向安装器使用；也可单独运行：
  python3 doctor.py --fix
  python3 doctor.py --verify
  python3 doctor.py --json
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_SKIN_TEXT = '''name: phoenix
description: "不死鸟 Phoenix — 浴火不灭，迭代永生"
branding:
  agent_name: "Hermes × Phoenix"
  welcome: "🔥 Hermes × Phoenix — 浴火不灭，迭代永生"
  goodbye: "🔥 不死鸟浴火，下次重生再见！"
  response_label: " 🔥 Phoenix "
'''


@dataclass
class DoctorIssue:
    kind: str
    detail: str
    repairable: bool = True


@dataclass
class DoctorFix:
    kind: str
    detail: str


@dataclass
class DoctorReport:
    healthy: bool
    issues: List[DoctorIssue] = field(default_factory=list)
    fixes: List[DoctorFix] = field(default_factory=list)
    recheck_issues: List[DoctorIssue] = field(default_factory=list)
    runtime_ok: Optional[bool] = None
    runtime_error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "healthy": self.healthy,
            "issues": [issue.__dict__ for issue in self.issues],
            "fixes": [fix.__dict__ for fix in self.fixes],
            "recheck_issues": [issue.__dict__ for issue in self.recheck_issues],
            "runtime_ok": self.runtime_ok,
            "runtime_error": self.runtime_error,
        }


class PhoenixDoctor:
    def __init__(
        self,
        hermes_home: Optional[Path] = None,
        phoenix_home: Optional[Path] = None,
        hermes_agent_dir: Optional[Path] = None,
        verify_runtime: bool = True,
    ):
        self.hermes_home = Path(hermes_home or Path.home() / ".hermes")
        self.phoenix_home = Path(phoenix_home or self.hermes_home / "phoenix")
        self.hermes_agent_dir = Path(hermes_agent_dir or self._detect_hermes_agent_dir())
        self.bundled_plugin_dir = self.hermes_agent_dir / "plugins" / "phoenix_full"
        self.user_plugin_dir = self.hermes_home / "plugins" / "phoenix_full"
        self.skin_dir = self.hermes_home / "skins"
        self.env_file = self.hermes_home / ".env"
        self.config_file = self.hermes_home / "config.yaml"
        self.verify_runtime = verify_runtime
        self.source_root = Path(__file__).resolve().parent

    def _detect_hermes_agent_dir(self) -> str:
        candidates = [
            os.environ.get("HERMES_AGENT_DIR", ""),
            str(self.hermes_home / "hermes-agent"),
            str(Path.home() / ".hermes" / "hermes-agent"),
            "/mnt/projects/hermes-agent",
            str(Path.home() / "projects" / "hermes-agent"),
            str(Path.home() / "Desktop" / "hermes-agent"),
        ]
        for candidate in candidates:
            if candidate and Path(candidate).exists():
                return candidate
        return str(self.hermes_home / "hermes-agent")

    def _read_text(self, path: Path) -> str:
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def _write_text(self, path: Path, text: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _load_yaml(self) -> Optional[Any]:
        try:
            import yaml  # type: ignore
        except Exception:
            return None
        if not self.config_file.exists() or not self.config_file.read_text(encoding="utf-8").strip():
            return {}
        data = yaml.safe_load(self.config_file.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}

    def _save_yaml(self, data: Dict[str, Any]):
        try:
            import yaml  # type: ignore
        except Exception:
            return False
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        self.config_file.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        return True

    def _load_phoenix_config(self) -> Dict[str, Any]:
        cfg = self.phoenix_home / "config.json"
        if not cfg.exists():
            return {}
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _parse_env_file(self) -> Dict[str, str]:
        """Parse ~/.hermes/.env into key → value (no shell expansion)."""
        if not self.env_file.is_file():
            return {}
        out: Dict[str, str] = {}
        for line in self.env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if "=" not in s:
                continue
            k, _, v = s.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k:
                out[k] = v
        return out

    def _collect_phoenix_key_env_names(self, data: Dict[str, Any]) -> set:
        """All api_key_env names that must be non-empty for 学员版验收（不落明文 Key）。"""
        names: set = set()
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

    def _check_env_credentials(self, issues: List[DoctorIssue]):
        """配置里声明的 api_key_env 必须在 .env 或进程环境中非空（学员缺 Key 时一眼定位）。"""
        data = self._load_phoenix_config()
        if not data:
            return
        required = self._collect_phoenix_key_env_names(data)
        if not required:
            return
        file_env = self._parse_env_file()
        for env_name in sorted(required):
            raw = os.environ.get(env_name) or file_env.get(env_name)
            if raw is None or not str(raw).strip():
                issues.append(
                    DoctorIssue(
                        "env_key_missing_or_empty",
                        f"需要 {env_name}：在环境变量或 {self.env_file} 中未设置或为空（高档/日常线路会失败）",
                        repairable=False,
                    )
                )

    def _save_phoenix_config(self, data: Dict[str, Any]) -> bool:
        cfg = self.phoenix_home / "config.json"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return True

    def _check_phoenix_open_config(self, issues: List[DoctorIssue]):
        """V8 权威配置检查：phoenix/config.json → phoenix_open.model_tiers/providers。"""
        data = self._load_phoenix_config()
        if not data:
            issues.append(DoctorIssue("invalid_phoenix_config", "config.json missing or invalid JSON", repairable=False))
            return
        open_cfg = data.get("phoenix_open")
        if not isinstance(open_cfg, dict):
            issues.append(DoctorIssue("missing_phoenix_open", "config.json: phoenix_open"))
            return
        tiers = open_cfg.get("model_tiers")
        providers = open_cfg.get("providers")
        if not isinstance(tiers, dict):
            issues.append(DoctorIssue("missing_model_tiers", "phoenix_open.model_tiers"))
            tiers = {}
        if not isinstance(providers, dict):
            issues.append(DoctorIssue("missing_providers", "phoenix_open.providers"))
            providers = {}

        required_tiers = ["daily", "medium", "deep", "god", "super_god"]
        expected_triggers = {"deep": "/深度", "god": "/大神", "super_god": "/真神"}
        for tier_name in required_tiers:
            tier = tiers.get(tier_name)
            if not isinstance(tier, dict):
                issues.append(DoctorIssue("missing_model_tier", tier_name))
                continue
            if tier.get("auto_execute") is True:
                issues.append(DoctorIssue("auto_execute_must_be_false", tier_name, repairable=False))
            if tier_name in expected_triggers and tier.get("trigger") != expected_triggers[tier_name]:
                issues.append(DoctorIssue("high_tier_trigger_missing", f"{tier_name} -> {expected_triggers[tier_name]}", repairable=False))
            if tier_name == "medium" and tier.get("enabled") is not False:
                issues.append(DoctorIssue("medium_should_be_reserved", "medium 默认应 enabled=false", repairable=False))
            if not tier.get("model"):
                issues.append(DoctorIssue("tier_missing_model", tier_name))
            if not tier.get("provider"):
                issues.append(DoctorIssue("tier_missing_provider", tier_name))
            if tier.get("api_mode") not in (None, "", "chat_completions"):
                issues.append(DoctorIssue("invalid_api_mode", f"{tier_name}: {tier.get('api_mode')}，OpenAI兼容必须用chat_completions", repairable=False))
            for slot in ("fallback", "emergency"):
                item = tier.get(slot)
                if not isinstance(item, dict) or not item.get("model") or not item.get("provider"):
                    issues.append(DoctorIssue(f"tier_missing_{slot}", tier_name))
            if tier_name in ("deep", "god", "super_god"):
                if tier.get("requires_approval") is not True:
                    issues.append(DoctorIssue("high_tier_without_approval", tier_name))
                if tier.get("manual_only") is not True:
                    issues.append(DoctorIssue("high_tier_not_manual_only", tier_name, repairable=False))

        for provider_name, provider_cfg in providers.items():
            if not isinstance(provider_cfg, dict):
                issues.append(DoctorIssue("invalid_provider_config", provider_name))
                continue
            if not provider_cfg.get("base_url"):
                issues.append(DoctorIssue("provider_missing_base_url", provider_name))
            if not provider_cfg.get("is_local") and not provider_cfg.get("api_key_env") and not provider_cfg.get("api_key"):
                issues.append(DoctorIssue("provider_missing_key_env", provider_name))

        # 调 ProviderResolver 做防串 Key 绑定审计；不打印真实 Key。
        try:
            provider_root = self.phoenix_home
            if str(provider_root) not in sys.path:
                sys.path.insert(0, str(provider_root))
            from core.provider_resolver import ProviderResolver  # type: ignore
            resolver_issues = ProviderResolver(data).validate_all()
            for item in resolver_issues:
                issues.append(DoctorIssue("provider_resolver", item, repairable=False))
        except Exception as exc:
            issues.append(DoctorIssue("provider_resolver_exception", str(exc), repairable=False))


    def _upsert_yaml(self, dotted_key: str, value: Any):
        data = self._load_yaml()
        if data is None:
            return False
        cur = data
        parts = dotted_key.split(".")
        for part in parts[:-1]:
            if not isinstance(cur.get(part), dict):
                cur[part] = {}
            cur = cur[part]
        cur[parts[-1]] = value
        return self._save_yaml(data)

    def _check_file_exists(self, rel: str, issues: List[DoctorIssue]):
        path = self.phoenix_home / rel
        if not path.exists():
            issues.append(DoctorIssue("missing_file", rel))

    def _check_feature_registry(self, issues: List[DoctorIssue]):
        registry = self.phoenix_home / "feature_registry.json"
        if not registry.exists():
            issues.append(DoctorIssue("missing_feature_registry", str(registry)))
            return
        try:
            data = json.loads(registry.read_text(encoding="utf-8"))
        except Exception:
            issues.append(DoctorIssue("invalid_feature_registry", str(registry)))
            return
        meta = data.get("_meta") if isinstance(data, dict) else None
        categories = data.get("categories") if isinstance(data, dict) else None
        if not isinstance(meta, dict) or not isinstance(categories, dict) or not categories:
            issues.append(DoctorIssue("empty_feature_registry", str(registry)))

    def _check_bundle_sync(self, issues: List[DoctorIssue]):
        src = self.phoenix_home / "plugins" / "phoenix_full"
        if not src.exists():
            issues.append(DoctorIssue("missing_source_plugin", "plugins/phoenix_full"))
            return
        src_init = src / "__init__.py"
        src_yaml = src / "plugin.yaml"

        targets = [(self.bundled_plugin_dir, "bundled"), (self.user_plugin_dir, "user")]
        for dst, label in targets:
            dst_init = dst / "__init__.py"
            dst_yaml = dst / "plugin.yaml"
            if not dst_init.exists() or not dst_yaml.exists():
                issues.append(DoctorIssue(f"{label}_plugin_missing", str(dst)))
                continue
            if self._read_text(src_init) != self._read_text(dst_init):
                issues.append(DoctorIssue(f"{label}_plugin_drift", "__init__.py"))
            if self._read_text(src_yaml) != self._read_text(dst_yaml):
                issues.append(DoctorIssue(f"{label}_plugin_drift", "plugin.yaml"))

        plugin_text = self._read_text(src_init)
        forbidden_markers = ['return {"model"', 'api_mode="openai"', "api_mode='openai'", "base_url=current_api_key"]
        for marker in forbidden_markers:
            if marker in plugin_text:
                issues.append(DoctorIssue("plugin_forbidden_pattern", marker, repairable=False))
        for cmd in ("/深度", "/大神", "/真神"):
            if cmd not in plugin_text:
                issues.append(DoctorIssue("manual_trigger_missing_in_plugin", cmd, repairable=False))

    def _check_skin(self, issues: List[DoctorIssue]):
        skin = self.skin_dir / "phoenix.yaml"
        if not skin.exists():
            issues.append(DoctorIssue("missing_skin", str(skin)))
            return
        text = self._read_text(skin)
        if "Phoenix" not in text or "phoenix" not in text.lower():
            issues.append(DoctorIssue("invalid_skin", str(skin)))
        import re
        if re.search(r"\b[Vv]\d+(?:\.\d+)+", text):
            issues.append(DoctorIssue("fixed_version_skin", str(skin)))

    def _check_runtime_data_shapes(self, issues: List[DoctorIssue]):
        """检查 Phoenix 运行时 JSON 文件形状，避免 doctor 二次运行被 []/{} 错形数据打爆。"""
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
        data_dir = self.phoenix_home / "data"
        for filename, default in defaults.items():
            path = data_dir / filename
            if not path.exists():
                issues.append(DoctorIssue("runtime_data_missing", filename))
                continue
            try:
                loaded = json.loads(path.read_text(encoding="utf-8") or "null")
            except Exception:
                issues.append(DoctorIssue("runtime_data_invalid_json", filename))
                continue
            if not isinstance(loaded, type(default)):
                issues.append(DoctorIssue("runtime_data_wrong_shape", f"{filename}: expected {type(default).__name__}, got {type(loaded).__name__}"))

    def _scan_hermes_processes(self) -> List[Dict[str, Any]]:
        try:
            proc = subprocess.run(["ps", "-eo", "pid=,etime=,command="], capture_output=True, text=True, timeout=5)
        except Exception:
            return []
        if proc.returncode != 0:
            return []
        rows: List[Dict[str, Any]] = []
        current_pid = os.getpid()
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(None, 2)
            if len(parts) < 3:
                continue
            try:
                pid = int(parts[0])
            except ValueError:
                continue
            if pid == current_pid:
                continue
            command = parts[2]
            if "hermes" not in command.lower():
                continue
            if "doctor.py" in command or "build_release" in command:
                continue
            rows.append({"pid": pid, "etime": parts[1], "command": command})
        return rows

    def _has_agent_thread_leak_log(self) -> bool:
        log_path = self.hermes_home / "logs" / "errors.log"
        if not log_path.exists():
            return False
        try:
            text = log_path.read_text(encoding="utf-8", errors="ignore")[-20000:]
        except Exception:
            return False
        return "Agent thread still alive after interrupt" in text

    def _check_stale_agent_processes(self, issues: List[DoctorIssue]):
        """检测中断后残留的交互 Hermes 进程。默认只提示；--fix 下安全终止当前 HERMES_HOME 相关进程。"""
        if not self._has_agent_thread_leak_log():
            return
        processes = self._scan_hermes_processes()
        if not processes:
            issues.append(DoctorIssue("agent_thread_leak_log", "errors.log contains Agent thread still alive after interrupt", repairable=False))
            return
        for proc in processes:
            cmd = proc["command"]
            # 只自动修复明显属于当前 profile 或显式 Hermes 启动的进程，避免误杀别的 profile。
            repairable = str(self.hermes_home) in cmd or "HERMES_HOME" in cmd or "/.local/bin/hermes" in cmd or "/hermes-agent/venv/" in cmd
            issues.append(DoctorIssue(
                "stale_hermes_process",
                f"pid={proc['pid']} etime={proc['etime']} command={cmd[:180]}",
                repairable=repairable,
            ))

    def _check_hermes_entrypoint(self, issues: List[DoctorIssue]):
        """P0：hermes 必须是 Hermes Agent 原生命令，不能被 Phoenix CLI/alias/shim 覆盖。"""
        cmd = shutil.which("hermes")
        if not cmd:
            issues.append(DoctorIssue(
                "missing_hermes_command",
                "未检测到 hermes 命令；Phoenix 是插件，不是 Hermes 本体，请先安装 Hermes Agent",
                repairable=False,
            ))
            return
        path = Path(cmd)
        try:
            resolved = path.resolve()
            phoenix_resolved = self.phoenix_home.resolve()
            if phoenix_resolved == resolved or phoenix_resolved in resolved.parents:
                issues.append(DoctorIssue(
                    "hermes_command_hijacked_by_phoenix",
                    f"hermes points inside Phoenix: {resolved}",
                    repairable=False,
                ))
                return
        except Exception:
            pass
        blob = ""
        try:
            if path.is_file():
                blob += path.read_text(encoding="utf-8", errors="ignore")[:12000]
        except Exception:
            pass
        try:
            proc = subprocess.run([cmd, "--help"], capture_output=True, text=True, timeout=8)
            blob += "\n" + (proc.stdout or "")[:12000] + "\n" + (proc.stderr or "")[:4000]
        except Exception as exc:
            blob += f"\nHERME_HELP_ERROR={exc}"
        markers = ["不死鸟 Phoenix", "python -m phoenix.cli", "Phoenix V8", "CLI入口"]
        if any(marker in blob for marker in markers):
            issues.append(DoctorIssue(
                "hermes_command_hijacked_by_phoenix",
                f"hermes={cmd}; 输出/脚本包含 Phoenix CLI 标记。输入 hermes 会进入 Phoenix CLI，学员进不了 Hermes Agent。",
                repairable=False,
            ))

    def _gateway_status(self) -> Optional[str]:
        try:
            proc = subprocess.run(["hermes", "gateway", "status"], capture_output=True, text=True, timeout=20)
        except Exception:
            return None
        text = (proc.stdout or "") + "\n" + (proc.stderr or "")
        text = text.strip()
        return text if text else None

    def _check_gateway(self, issues: List[DoctorIssue]):
        status = self._gateway_status()
        if status is None:
            return
        lowered = status.lower()
        if any(marker in lowered for marker in ["not running", "stopped", "failed", "inactive"]):
            issues.append(DoctorIssue("gateway_not_running", status))
            return
        # Hermes/macOS launchd status may include a historic LastExitStatus even when
        # the service is loaded and has a live PID. Treat live PID/running markers as OK.
        running_markers = ["gateway running", "service is loaded", "pid =", "pid="]
        if any(marker in lowered for marker in running_markers):
            return

    def _repair_gateway(self) -> List[DoctorFix]:
        fixes: List[DoctorFix] = []
        try:
            restart = subprocess.run(["hermes", "gateway", "restart"], capture_output=True, text=True, timeout=60)
            if restart.returncode == 0:
                fixes.append(DoctorFix("restart_gateway", "hermes gateway restart"))
                return fixes
        except Exception:
            pass
        try:
            start = subprocess.run(["hermes", "gateway", "start"], capture_output=True, text=True, timeout=60)
            if start.returncode == 0:
                fixes.append(DoctorFix("start_gateway", "hermes gateway start"))
                return fixes
        except Exception:
            pass
        fixes.append(DoctorFix("restart_gateway_failed", "hermes gateway restart/start"))
        return fixes

    def _check_config(self, issues: List[DoctorIssue]):
        data = self._load_yaml()
        if data is None:
            issues.append(DoctorIssue("yaml_dependency_missing", "PyYAML not available", repairable=False))
            return
        if not self.config_file.exists():
            issues.append(DoctorIssue("missing_config", str(self.config_file)))
        expected = {
            "display.skin": "phoenix",
            "memory.memory_enabled": True,
            "memory.user_profile_enabled": True,
            "checkpoints.enabled": True,
            "compression.enabled": True,
            "privacy.redact_pii": True,
        }
        for key, expected_value in expected.items():
            cur = data
            for part in key.split("."):
                if not isinstance(cur, dict) or part not in cur:
                    issues.append(DoctorIssue("missing_config_key", key))
                    break
                cur = cur[part]
            else:
                if cur != expected_value:
                    issues.append(DoctorIssue("config_mismatch", f"{key}={cur!r}"))
        plugins = (((data or {}).get("plugins") or {}).get("enabled"))
        if not isinstance(plugins, list) or "phoenix-full" not in plugins:
            issues.append(DoctorIssue("missing_plugin_enable", "plugins.enabled"))
        self._check_phoenix_open_config(issues)
        self._check_env_credentials(issues)

    def _get_nested(self, data: Dict[str, Any], dotted_key: str) -> Any:
        cur: Any = data
        for part in dotted_key.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return None
            cur = cur[part]
        return cur

    def _check_fallback_config(self, data: Dict[str, Any], issues: List[DoctorIssue]):
        """Deprecated in V8. 权威配置已迁移到 config.json: phoenix_open。"""
        return


    def _check_runtime(self, report: DoctorReport):
        if not self.verify_runtime:
            report.runtime_ok = None
            return
        try:
            pkg_parent = self.phoenix_home.parent
            if str(pkg_parent) not in sys.path:
                sys.path.insert(0, str(pkg_parent))
            from phoenix import Phoenix  # type: ignore
            phoenix = Phoenix()
            health = phoenix.health_check()
            maintenance = health.get("maintenance", {}) if isinstance(health, dict) else {}
            report.runtime_ok = bool(health)
            if not maintenance.get("healthy", True):
                report.recheck_issues.append(DoctorIssue("runtime_health", json.dumps(maintenance, ensure_ascii=False)))
        except Exception as exc:  # pragma: no cover - surfaced in report
            report.runtime_ok = False
            report.runtime_error = str(exc)
            report.recheck_issues.append(DoctorIssue("runtime_exception", str(exc), repairable=False))

    def verify(self) -> DoctorReport:
        issues: List[DoctorIssue] = []
        for rel in [
            "phoenix.py",
            "doctor.py",
            "config.json",
            "integration/hermes_bridge.py",
            "integration/cli_command.py",
            "self_heal/unified_maintenance.py",
            "plugins/phoenix_full/__init__.py",
            "plugins/phoenix_full/plugin.yaml",
        ]:
            self._check_file_exists(rel, issues)
        self._check_feature_registry(issues)
        self._check_bundle_sync(issues)
        ledger_dir = self.phoenix_home / "data"
        try:
            ledger_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            issues.append(DoctorIssue("ledger_dir_unwritable", str(exc), repairable=False))
        self._check_skin(issues)
        self._check_config(issues)
        self._check_runtime_data_shapes(issues)
        self._check_stale_agent_processes(issues)
        self._check_hermes_entrypoint(issues)
        self._check_gateway(issues)
        report = DoctorReport(healthy=not issues, issues=issues)
        self._check_runtime(report)
        if report.runtime_ok is False:
            report.healthy = False
        return report

    def _copy_plugin(self) -> Optional[DoctorFix]:
        src = self.phoenix_home / "plugins" / "phoenix_full"
        if not src.exists():
            return None
        copied = []
        for dst in (self.bundled_plugin_dir, self.user_plugin_dir):
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            copied.append(str(dst))
        return DoctorFix("sync_plugin", " | ".join(copied))

    def _repair_skin(self) -> Optional[DoctorFix]:
        skin = self.skin_dir / "phoenix.yaml"
        source_skin = self.phoenix_home / "_package_skins" / "phoenix.yaml"
        self.skin_dir.mkdir(parents=True, exist_ok=True)
        if source_skin.exists():
            shutil.copy2(source_skin, skin)
        else:
            self._write_text(skin, DEFAULT_SKIN_TEXT)
        return DoctorFix("install_skin", str(skin))

    def _repair_feature_registry(self) -> Optional[DoctorFix]:
        source = self.source_root / "feature_registry.json"
        target = self.phoenix_home / "feature_registry.json"
        if source.exists():
            shutil.copy2(source, target)
            return DoctorFix("install_feature_registry", str(target))
        return None

    def _repair_runtime_data_shapes(self) -> List[DoctorFix]:
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
        fixes: List[DoctorFix] = []
        data_dir = self.phoenix_home / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        for filename, default in defaults.items():
            path = data_dir / filename
            needs_write = False
            if not path.exists() or path.stat().st_size == 0:
                needs_write = True
            else:
                try:
                    loaded = json.loads(path.read_text(encoding="utf-8") or "null")
                    needs_write = not isinstance(loaded, type(default))
                except Exception:
                    needs_write = True
            if needs_write:
                path.write_text(json.dumps(default, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                fixes.append(DoctorFix("repair_runtime_data", filename))
        return fixes

    def _repair_stale_hermes_processes(self, issues: List[DoctorIssue]) -> List[DoctorFix]:
        fixes: List[DoctorFix] = []
        pids: List[int] = []
        for issue in issues:
            if issue.kind != "stale_hermes_process" or not issue.repairable:
                continue
            prefix = "pid="
            if not issue.detail.startswith(prefix):
                continue
            try:
                pids.append(int(issue.detail[len(prefix):].split()[0]))
            except Exception:
                continue
        for pid in sorted(set(pids)):
            try:
                os.kill(pid, signal.SIGTERM)
                fixes.append(DoctorFix("terminate_stale_hermes", f"pid={pid} signal=TERM"))
            except ProcessLookupError:
                fixes.append(DoctorFix("terminate_stale_hermes", f"pid={pid} already exited"))
            except PermissionError:
                fixes.append(DoctorFix("terminate_stale_hermes_failed", f"pid={pid} permission denied"))
            except Exception as exc:
                fixes.append(DoctorFix("terminate_stale_hermes_failed", f"pid={pid} {exc}"))
        if pids:
            time.sleep(0.2)
        return fixes

    def _repair_config(self) -> List[DoctorFix]:
        """修复 Hermes config.yaml 里的通用启用项；V8 模型权威源不在这里。"""
        fixes: List[DoctorFix] = []
        if not self.config_file.exists():
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            self.config_file.write_text("{}\n", encoding="utf-8")
            fixes.append(DoctorFix("create_config", str(self.config_file)))
        targets = [
            ("display.skin", "phoenix"),
            ("display.resume_display", "full"),
            ("display.tui_auto_resume_recent", True),
            ("display.streaming", True),
            ("compression.enabled", True),
            ("compression.threshold", 0.5),
            ("compression.target_ratio", 0.2),
            ("checkpoints.enabled", True),
            ("checkpoints.max_snapshots", 50),
            ("memory.memory_enabled", True),
            ("memory.user_profile_enabled", True),
            ("privacy.redact_pii", True),
        ]
        for key, value in targets:
            if self._upsert_yaml(key, value):
                fixes.append(DoctorFix("set_config", key))
        data = self._load_yaml() or {}
        plugins = (((data.get("plugins") or {}).get("enabled")) if isinstance(data, dict) else None)
        if not isinstance(plugins, list):
            self._upsert_yaml("plugins.enabled", ["phoenix-full", "disk-cleanup"])
            fixes.append(DoctorFix("set_config", "plugins.enabled"))
        elif "phoenix-full" not in plugins:
            plugins = list(plugins)
            plugins.append("phoenix-full")
            self._upsert_yaml("plugins.enabled", plugins)
            fixes.append(DoctorFix("set_config", "plugins.enabled"))
        return fixes


    def auto_fix(self, issues: List[DoctorIssue]) -> List[DoctorFix]:
        fixes: List[DoctorFix] = []
        issue_kinds = {issue.kind for issue in issues}
        if issue_kinds.intersection({"bundled_plugin_missing", "bundled_plugin_drift", "user_plugin_missing", "user_plugin_drift"}):
            fix = self._copy_plugin()
            if fix:
                fixes.append(fix)
        if issue_kinds.intersection({"missing_skin", "invalid_skin", "fixed_version_skin"}):
            fixes.append(self._repair_skin())
        if issue_kinds.intersection({"missing_feature_registry", "invalid_feature_registry", "empty_feature_registry"}):
            fix = self._repair_feature_registry()
            if fix:
                fixes.append(fix)
        if issue_kinds.intersection({"missing_config", "missing_config_key", "config_mismatch", "missing_plugin_enable"}):
            fixes.extend(self._repair_config())
        if issue_kinds.intersection({"runtime_data_missing", "runtime_data_invalid_json", "runtime_data_wrong_shape"}):
            fixes.extend(self._repair_runtime_data_shapes())
        if "stale_hermes_process" in issue_kinds:
            fixes.extend(self._repair_stale_hermes_processes(issues))
        if "gateway_not_running" in issue_kinds:
            fixes.extend(self._repair_gateway())
        return fixes

    def run(self, apply_fixes: bool = True) -> DoctorReport:
        report = self.verify()
        if apply_fixes and report.issues:
            report.fixes = self.auto_fix(report.issues)
            recheck = self.verify()
            report.recheck_issues = recheck.issues
            report.runtime_ok = recheck.runtime_ok
            report.runtime_error = recheck.runtime_error
            report.healthy = not recheck.issues and (recheck.runtime_ok is not False)
        return report


def _print_report(report: DoctorReport):
    print("🩺 Phoenix Doctor 报告")
    print(f"  健康: {report.healthy}")
    print(f"  问题: {len(report.issues)}")
    for issue in report.issues:
        flag = "可修复" if issue.repairable else "跳过"
        print(f"  - [{flag}] {issue.kind}: {issue.detail}")
    if report.fixes:
        print(f"  修复: {len(report.fixes)}")
        for fix in report.fixes:
            print(f"  - {fix.kind}: {fix.detail}")
    if report.recheck_issues:
        print(f"  复检问题: {len(report.recheck_issues)}")
        for issue in report.recheck_issues:
            print(f"  - {issue.kind}: {issue.detail}")
    if report.runtime_ok is not None:
        print(f"  运行时检查: {report.runtime_ok}")
    if report.runtime_error:
        print(f"  运行时错误: {report.runtime_error}")
    print("")
    print("SUMMARY", "PASS" if report.healthy else "FAIL")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Phoenix installation doctor")
    parser.add_argument("--fix", action="store_true", help="auto-fix repairable issues")
    parser.add_argument("--verify", action="store_true", help="verify only, no fixes")
    parser.add_argument("--json", action="store_true", help="print JSON report")
    parser.add_argument("--no-runtime", action="store_true", help="skip runtime import/health check")
    parser.add_argument("--home", type=str, default=None, help="override Hermes home")
    parser.add_argument("--phoenix-home", type=str, default=None, help="override Phoenix home")
    parser.add_argument("--hermes-agent-dir", type=str, default=None, help="override Hermes agent source dir")
    args = parser.parse_args(argv)

    apply_fixes = args.fix or not args.verify
    doctor = PhoenixDoctor(
        hermes_home=Path(args.home) if args.home else None,
        phoenix_home=Path(args.phoenix_home) if args.phoenix_home else None,
        hermes_agent_dir=Path(args.hermes_agent_dir) if args.hermes_agent_dir else None,
        verify_runtime=not args.no_runtime,
    )
    report = doctor.run(apply_fixes=apply_fixes)
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        _print_report(report)
    return 0 if report.healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
