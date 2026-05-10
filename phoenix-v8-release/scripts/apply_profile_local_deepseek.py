#!/usr/bin/env python3
"""Merge phoenix_open for profile local-deepseek: Ollama (OpenAI-compatible) + DeepSeek high tiers.

Called from install.sh after package config.json is copied to PHOENIX_HOME.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict


def parse_env_file(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and not k.startswith("#"):
            out[k] = v
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config-json", type=Path, required=True)
    ap.add_argument("--env-file", type=Path, required=True)
    ap.add_argument("--ollama-url", default="http://127.0.0.1:11434/v1")
    ap.add_argument("--ollama-model", default="qwen3.6:35b-a3b-q4_K_M")
    ap.add_argument("--deepseek-model", default="deepseek-chat")
    ap.add_argument("--deepseek-url", default="")
    args = ap.parse_args()

    envm = parse_env_file(args.env_file)
    deep_url = (args.deepseek_url or envm.get("DEEPSEEK_BASE_URL") or "").strip()
    if not deep_url:
        deep_url = "https://api.deepseek.com/v1"

    local_p, deep_p = "local", "deepseek"
    om = args.ollama_model
    dm = args.deepseek_model
    ou = args.ollama_url.rstrip("/")

    cfg_path = args.config_json
    data: Dict[str, Any] = {}
    if cfg_path.exists() and cfg_path.read_text(encoding="utf-8").strip():
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        data = {}

    open_cfg = data.setdefault("phoenix_open", {})
    open_cfg["providers"] = {
        local_p: {"base_url": ou, "is_local": True, "models": [om]},
        deep_p: {
            "base_url": deep_url,
            "api_key_env": "DEEPSEEK_API_KEY",
            "models": [dm],
            "is_local": False,
        },
    }
    fb = {
        "model": om,
        "provider": local_p,
        "base_url": ou,
        "api_key_env": "OLLAMA_API_KEY",
    }
    em_fb = dict(fb)
    open_cfg["model_tiers"] = {
        "daily": {
            "model": om,
            "provider": local_p,
            "base_url": ou,
            "api_key_env": "OLLAMA_API_KEY",
            "requires_approval": False,
            "auto_execute": False,
            "manual_only": True,
            "fallback": dict(fb),
            "emergency": dict(em_fb),
        },
        "medium": {
            "model": om,
            "provider": local_p,
            "base_url": ou,
            "api_key_env": "OLLAMA_API_KEY",
            "enabled": False,
            "requires_approval": True,
            "auto_execute": False,
            "manual_only": True,
            "fallback": {
                "model": om,
                "provider": local_p,
                "base_url": ou,
                "api_key_env": "OLLAMA_API_KEY",
            },
            "emergency": dict(em_fb),
        },
        "deep": {
            "model": dm,
            "provider": deep_p,
            "base_url": deep_url,
            "api_key_env": "DEEPSEEK_API_KEY",
            "requires_approval": True,
            "auto_execute": False,
            "manual_only": True,
            "trigger": "/深度",
            "fallback": dict(fb),
            "emergency": dict(em_fb),
        },
        "god": {
            "model": dm,
            "provider": deep_p,
            "base_url": deep_url,
            "api_key_env": "DEEPSEEK_API_KEY",
            "requires_approval": True,
            "auto_execute": False,
            "manual_only": True,
            "trigger": "/大神",
            "fallback": {
                "model": dm,
                "provider": deep_p,
                "base_url": deep_url,
                "api_key_env": "DEEPSEEK_API_KEY",
            },
            "emergency": dict(em_fb),
        },
        "super_god": {
            "model": dm,
            "provider": deep_p,
            "base_url": deep_url,
            "api_key_env": "DEEPSEEK_API_KEY",
            "model_a": dm,
            "provider_a": deep_p,
            "base_url_a": deep_url,
            "api_key_env_a": "DEEPSEEK_API_KEY",
            "model_b": dm,
            "provider_b": deep_p,
            "base_url_b": deep_url,
            "api_key_env_b": "DEEPSEEK_API_KEY",
            "requires_approval": True,
            "auto_execute": False,
            "manual_only": True,
            "trigger": "/真神",
            "secondary_reserved": {"model": dm, "provider": deep_p},
            "fallback": {
                "model": dm,
                "provider": deep_p,
                "base_url": deep_url,
                "api_key_env": "DEEPSEEK_API_KEY",
            },
            "emergency": dict(em_fb),
        },
    }
    open_cfg["fallback"] = dict(fb)
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
