"""Phoenix V8 action ledger.

Append-only JSONL audit log for model/tool execution records.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from hermes_constants import get_hermes_home


SENSITIVE_KEYS = ("api_key", "key", "token", "secret", "password", "authorization")


def _is_sensitive_key(key: str) -> bool:
    lower = key.lower()
    return any(part in lower for part in SENSITIVE_KEYS)


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for k, v in value.items():
            if _is_sensitive_key(k):
                out[k] = "[REDACTED]"
            else:
                out[k] = _sanitize_value(v)
        return out
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, str) and len(value) > 1200:
        return value[:1200] + " ...[truncated]"
    return value


class ActionLedger:
    """Append-only JSONL ledger with light redaction."""

    def __init__(self, path: Optional[Path] = None):
        self._path = path or (get_hermes_home() / "phoenix" / "data" / "action_ledger.jsonl")
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def append(
        self,
        action: str,
        status: str,
        *,
        task_type: str = "",
        model: str = "",
        provider: str = "",
        cost_usd: float = 0.0,
        latency_s: float = 0.0,
        error: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        record = {
            "ts": int(time.time()),
            "action": action,
            "status": status,
            "task_type": task_type,
            "model": model,
            "provider": provider,
            "cost_usd": round(float(cost_usd), 6),
            "latency_s": round(float(latency_s), 4),
            "error": (error or "")[:500],
            "metadata": _sanitize_value(metadata or {}),
        }
        with self._path.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(record, ensure_ascii=False) + "\n")
