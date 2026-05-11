# Hermes Agent v0.13.1 (Phoenix V8 Guardrails)

**Release Date:** May 11, 2026  
**Scope:** Phoenix V8 `/真神` safety and observability hardening

---

## ✨ Highlights

- **`/真神` budget gate before execution** — expensive runs are checked before entering the heavy path. When budget is exceeded, execution is blocked with a clear downgrade/retry message instead of silently burning cost.
- **Full `/真神` execution ledger lifecycle** — adds start/end/error/downgrade/cancel/switch-failed events so operators can reconstruct what happened in one run.
- **Hard high-risk tool confirmation at runtime** — risky tools are now blocked in `pre_tool_call` during confirmed `/真神` runs unless `user_confirmed_high_risk=true` is explicitly present.
- **Session-scoped confirm state isolation** — pending confirm state is now keyed by session scope to avoid cross-session bleed in concurrent gateway traffic.
- **Profile-safe Phoenix action ledger path** — default ledger path now uses `get_hermes_home()` (profile-aware) instead of a hardcoded home directory path.

---

## 🛡️ Safety Changes

- New runtime gate for `/真神`:
  - checks estimated max cost before execution
  - records gate snapshots for traceability
  - returns user-friendly block reason when denied
- New high-risk tool enforcement:
  - applies only to confirmed `/真神` execution
  - blocks risky tool names unless explicit confirmation flag is passed
  - records `high_risk_tool_blocked` in ledger

---

## 🧪 Validation

- `tests/plugins/test_phoenix_full_guardrails.py` — **3 passed**
  - profile-aware `ActionLedger` path
  - session-scoped pending confirm isolation
  - high-risk `pre_tool_call` blocking in `/真神`
- `tests/test_tui_gateway_server.py` — **174 passed**

---

## 📁 Primary Files Changed

- `plugins/phoenix_full/__init__.py`
- `phoenix-v8-release/security/action_ledger.py`
- `tests/plugins/test_phoenix_full_guardrails.py`
- `tui_gateway/server.py`

