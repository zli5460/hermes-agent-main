"""
Phoenix Gateway API — Unified Singleton Interface for Hermes Gateway

Provides a clean, single-import API that the gateway can call directly
instead of doing sys.path.insert + fresh import every request.

Usage (from gateway):
    from phoenix.integration.gateway_api import phoenix_gateway
    
    # Route + get full runtime config in one call
    result = phoenix_gateway.route_and_get_runtime(message, has_image=False)
    # result = {
    #   "model": "xiaomi/mimo-v2.5",
    #   "runtime": {"api_key": ..., "base_url": ..., "provider": "nous-api", ...},
    #   "task_type": "chat",
    #   "backup_model": "xiaomi/mimo-v2.5",
    #   "fallback_model": "xiaomi/mimo-v2.5",
    #   "route_chain": ["xiaomi/mimo-v2.5", ...],
    # }
    
    # Report result for feedback loop
    phoenix_gateway.report_result(
        model="xiaomi/mimo-v2.5",
        task_type="chat",
        latency=1.23,
        success=True,
        error=None,
    )
    
    # Load memories for system prompt injection
    memories = phoenix_gateway.load_memories()

Author: Hermes Agent (auto-generated)
"""

from __future__ import annotations

import os
import sys
import time
import json
import logging
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger("phoenix.gateway_api")

# ---------------------------------------------------------------------------
# Config resolution helpers
# ---------------------------------------------------------------------------

_NOUS_DEFAULT_BASE_URL = "https://inference-api.nousresearch.com/v1"


def _resolve_nous_api_key() -> str:
    """
    Resolve Nous API key with priority:
      1. NOUS_API_KEY environment variable
      2. ~/.hermes/config.yaml  →  model.api_key
      3. empty string (caller must handle)
    """
    # 1. Env var
    key = os.environ.get("NOUS_API_KEY", "").strip()
    if key:
        return key

    # 2. config.yaml
    try:
        import yaml  # type: ignore
        cfg_path = Path.home() / ".hermes" / "config.yaml"
        if cfg_path.exists():
            cfg = yaml.safe_load(cfg_path.read_text()) or {}
            key = (cfg.get("model") or {}).get("api_key", "")
            if key:
                return str(key).strip()
    except ImportError:
        # yaml not installed — try manual parse for api_key line
        try:
            cfg_path = Path.home() / ".hermes" / "config.yaml"
            if cfg_path.exists():
                for line in cfg_path.read_text().splitlines():
                    stripped = line.strip()
                    if stripped.startswith("api_key:"):
                        val = stripped.split(":", 1)[1].strip().strip("'\"")
                        if val and val != "''":
                            return val
        except Exception as exc:
            _ = exc
    except Exception as exc:
        _ = exc

    return ""


def _resolve_nous_base_url(phoenix_config=None) -> str:
    """
    Resolve base URL with priority:
      1. Phoenix config router.models.*.base_url (if present)
      2. Default: https://inference-api.nousresearch.com/v1
    """
    if phoenix_config:
        custom = phoenix_config.get("router.nous_base_url")
        if custom:
            return str(custom)
    return _NOUS_DEFAULT_BASE_URL


# ---------------------------------------------------------------------------
# Singleton Gateway API
# ---------------------------------------------------------------------------

class _PhoenixGatewayAPI:
    """
    Thread-safe singleton interface that wraps the Phoenix system for
    gateway consumption.  Only one Phoenix instance is ever created.
    """

    def __init__(self):
        self._phoenix = None
        self._initialized = False
        self._init_error: Optional[str] = None
        self._api_key: str = ""
        self._base_url: str = _NOUS_DEFAULT_BASE_URL
        self._init_lock = threading.Lock()

    # ---- lazy init --------------------------------------------------------

    def _ensure_initialized(self) -> bool:
        """Lazily create the Phoenix instance on first use."""
        if self._initialized:
            return True
        if not self._init_lock.acquire(blocking=False):
            return False  # avoid re-entrant import deadlock
        try:
            hermes_dir = str(Path.home() / ".hermes")
            if hermes_dir not in sys.path:
                sys.path.insert(0, hermes_dir)

            from phoenix.phoenix import Phoenix  # noqa: E402
            self._phoenix = Phoenix()
            self._initialized = True

            # Resolve credentials once
            self._api_key = _resolve_nous_api_key()
            self._base_url = _resolve_nous_base_url(self._phoenix.config)

            logger.info(
                "PhoenixGateway singleton initialized (base_url=%s, has_key=%s)",
                self._base_url,
                bool(self._api_key),
            )
            return True
        except Exception as exc:
            self._init_error = str(exc)
            logger.error("PhoenixGateway init failed: %s", exc)
            return False
        finally:
            self._init_lock.release()

    # ---- public API -------------------------------------------------------

    def route_and_get_runtime(
        self,
        message: str,
        has_image: bool = False,
        force_model: Optional[str] = None,
    ) -> Optional[dict]:
        """
        Route a message through Phoenix and return everything the gateway
        needs in a single call.

        Returns dict:
            model           – selected model name
            runtime         – {api_key, base_url, provider, api_mode, command, args, credential_pool}
            task_type       – classified task type
            backup_model    – secondary fallback model (from config "fallback" field)
            fallback_model  – emergency model (from config "emergency" field)
            route_chain     – ordered list [primary, fallback, emergency]
            reason          – routing decision reason
            is_fallback     – whether this is a degraded/fallback choice
        Or None on failure.
        """
        if not self._ensure_initialized():
            return None

        try:
            # Auto-detect image tags in message (matching gateway conventions)
            if not has_image:
                _IMAGE_TAGS = [
                    "[User sent an image",
                    "[The user sent an image",
                    "sent an image~",
                    "[User sent a video",
                    "[The user sent a video",
                    "[User sent audio",
                ]
                has_image = any(tag in message for tag in _IMAGE_TAGS)

            decision = self._phoenix.route(message, has_image=has_image, force_model=force_model)

            if not decision.model:
                return None

            runtime = {
                "api_key": self._api_key,
                "base_url": self._base_url,
                "provider": "nous-api",
                "api_mode": None,
                "command": None,
                "args": [],
                "credential_pool": None,
            }

            return {
                "model": decision.model,
                "runtime": runtime,
                "task_type": decision.task_type,
                "backup_model": getattr(decision, "backup_model", None),
                "fallback_model": getattr(decision, "fallback_model", None),
                "route_chain": getattr(decision, "route_chain", None),
                "reason": getattr(decision, "reason", ""),
                "is_fallback": getattr(decision, "is_fallback", False),
            }
        except Exception as exc:
            logger.warning("Phoenix route_and_get_runtime failed: %s", exc)
            return None

    def report_result(
        self,
        model: str,
        task_type: str,
        latency: float,
        success: bool,
        error: Optional[str] = None,
        cost: float = 0.0,
        status_code: Optional[int] = None,
    ) -> None:
        """
        Feed back a model-call result to Phoenix for circuit breaker,
        evolution, and memory updates.
        """
        if not self._ensure_initialized():
            return

        try:
            self._phoenix.report_model_result(
                model=model,
                task_type=task_type,
                latency=latency,
                cost=cost,
                success=success,
                error_message=error or "",
                error_status_code=status_code,
            )
        except Exception as exc:
            logger.debug("Phoenix report_result failed (non-critical): %s", exc)

    def load_memories(self) -> str:
        """
        Load Phoenix memories (long-term, extracted, session, knowledge graph)
        formatted for injection into the system prompt.

        Returns empty string on failure (never breaks the gateway).
        """
        if not self._ensure_initialized():
            return ""

        # --- Part A: use Phoenix's own context assembly (session, KG, diary, skills) ---
        phoenix_context = ""
        try:
            phoenix_context = self._phoenix.get_context_for_prompt()
        except Exception as exc:
            logger.debug("Phoenix get_context_for_prompt failed: %s", exc)

        # --- Part B: raw JSON files for long-term + extracted memories ---
        raw_parts: list[str] = []
        try:
            data_dir = Path.home() / ".hermes" / "phoenix" / "data"

            # 1. Long-term memory
            ltm_path = data_dir / "long_term_memory.json"
            if ltm_path.exists():
                memories = json.loads(ltm_path.read_text())
                if memories:
                    memories.sort(key=lambda m: m.get("importance", 0), reverse=True)
                    lines = ["## 不死鸟记忆（你之前知道的事情）"]
                    for mem in memories[:15]:
                        cat = mem.get("category", "")
                        content = mem.get("content", "")
                        importance = mem.get("importance", 1)
                        mark = "⭐" * min(importance, 3)
                        lines.append(f"- [{cat}] {content} {mark}")
                    raw_parts.append("\n".join(lines))

            # 2. Recent extracted memories (not yet applied)
            ext_path = data_dir / "extracted_memories.json"
            if ext_path.exists():
                extracted = json.loads(ext_path.read_text())
                recent = [m for m in extracted if not m.get("applied", False)]
                if recent:
                    lines = ["## 最近发现的新信息"]
                    for mem in recent[-5:]:
                        lines.append(f"- {mem.get('content', '')}")
                    raw_parts.append("\n".join(lines))
        except Exception as exc:
            logger.debug("Phoenix memory file loading failed: %s", exc)

        # Merge both parts, dedup empty
        all_parts = [p for p in [phoenix_context] + raw_parts if p]
        return "\n\n".join(all_parts)

    # ---- convenience ------------------------------------------------------

    @property
    def is_ready(self) -> bool:
        """Check if the singleton is initialized and healthy."""
        return self._initialized and self._phoenix is not None

    @property
    def init_error(self) -> Optional[str]:
        """Return the last init error, if any."""
        return self._init_error

    def health_check(self) -> dict:
        """Delegate to Phoenix health check."""
        if not self._ensure_initialized():
            return {"status": "unavailable", "error": self._init_error}
        try:
            return self._phoenix.health_check()
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def evolve(self):
        """Trigger Phoenix evolution (circuit breaker, memory consolidation, etc.)."""
        if not self._ensure_initialized():
            return
        try:
            self._phoenix.evolve()
        except Exception as exc:
            logger.debug("Phoenix evolve failed (non-critical): %s", exc)

    def reset(self) -> None:
        """Force re-initialization (useful for testing or config reload)."""
        self._phoenix = None
        self._initialized = False
        self._init_error = None
        self._api_key = ""
        self._base_url = _NOUS_DEFAULT_BASE_URL


# ---------------------------------------------------------------------------
# Module-level singleton — import this, not the class
# ---------------------------------------------------------------------------
phoenix_gateway = _PhoenixGatewayAPI()

# Convenience alias for explicit usage
PhoenixGatewayAPI = _PhoenixGatewayAPI
