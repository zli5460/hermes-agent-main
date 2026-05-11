"""
Phoenix V8 初心回归版插件
手动升档（/深度 /大神 /真神）+ 三层兜底 + CLI/Gateway确认弹窗 + 记忆 + 自愈

核心创新：
1. Monkey-patch AIAgent.run_conversation — 统一拦截所有平台的用户消息
2. Monkey-patch AIAgent.chat — CLI模式额外包装
3. 零改动Hermes核心，纯插件实现五档路由+确认弹窗

覆盖平台：CLI / TUI / Telegram / 飞书 / 微信
"""

import os
import sys
import time
import logging
import json
import threading
from pathlib import Path

logger = logging.getLogger("hermes.plugin.phoenix_full")

# Phoenix路径
HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
PHOENIX_DIR = HERMES_HOME / "phoenix"
if PHOENIX_DIR.exists() and str(PHOENIX_DIR) not in sys.path:
    sys.path.insert(0, str(PHOENIX_DIR))

# ============================================================
# 模块级状态
# ============================================================
_phoenix = None
_router = None
_assessor = None
_phoenix_lock = threading.Lock()
_SENTINEL = object()
_load_failed_at = 0
_phoenix = _SENTINEL

# 确认弹窗状态（按会话隔离，避免并发会话串线）
_pending_confirm_sessions = {}  # session_scope -> {"task": str, "tier": str, "model": str, "action": None/"confirm"/"downgrade"}
_last_session_scope = "global"

# 消息捕获（monkey-patch用）
_last_user_message = ""

# TokenLedger: 脱敏审计，不存API Key，只记录模型/档位/动作/预估成本。
_LEDGER_PATH = PHOENIX_DIR / "data" / "token_ledger.jsonl"
_BUDGET_DEFAULTS = {
    "max_steps": 24,
    "max_visual_calls": 6,
    "max_cost_usd": 5.0,
    "enforce_cost_limit": False,
}
_HIGH_RISK_TOOL_NAMES = {
    "terminal",
    "execute_code",
    "run_shell_command",
    "write_file",
    "patch_file",
    "remove_file",
    "delete_file",
    "git_commit",
    "git_push",
}


def _session_scope_from_agent(agent) -> str:
    sid = str(getattr(agent, "session_id", "") or "").strip()
    return f"session:{sid}" if sid else f"agent:{id(agent)}"


def _session_scope_from_event(event) -> str:
    try:
        src = getattr(event, "source", None)
        if src:
            platform = getattr(getattr(src, "platform", None), "value", "") or ""
            chat_id = str(getattr(src, "chat_id", "") or "")
            thread_id = str(getattr(src, "thread_id", "") or "")
            if platform and chat_id:
                return f"gateway:{platform}:{chat_id}:{thread_id}"
    except Exception:
        pass
    return "global"


def _get_pending_confirm(scope: str):
    return _pending_confirm_sessions.get(scope)


def _set_pending_confirm(scope: str, payload):
    if payload is None:
        _pending_confirm_sessions.pop(scope, None)
    else:
        _pending_confirm_sessions[scope] = payload


def _clear_all_pending_confirms():
    _pending_confirm_sessions.clear()

def _ledger_record(event, **fields):
    """写入 TokenLedger JSONL；失败不影响主流程。"""
    try:
        _LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "event": event}
        row.update(fields)
        # 永不落真实Key
        for k in list(row.keys()):
            if "key" in k.lower() and row[k] and not str(row[k]).startswith("env:"):
                row[k] = "[REDACTED]"
        with _LEDGER_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception as exc:
        logger.debug("[phoenix_full] ledger write failed: %s", exc)


def _load_budget_guard():
    """Create a per-run BudgetGuard from phoenix config (best effort)."""
    try:
        from security.budget_guard import BudgetGuard  # type: ignore
    except Exception as exc:
        logger.warning("[phoenix_full] BudgetGuard unavailable, skip guard: %s", exc)
        return None

    cfg = dict(_BUDGET_DEFAULTS)
    try:
        data = _load_phoenix_config()
        section = data.get("budget_guard", {})
        if isinstance(section, dict):
            cfg.update(
                {
                    "max_steps": int(section.get("max_steps", cfg["max_steps"])),
                    "max_visual_calls": int(section.get("max_visual_calls", cfg["max_visual_calls"])),
                    "max_cost_usd": float(section.get("max_cost_usd", cfg["max_cost_usd"])),
                    "enforce_cost_limit": bool(section.get("enforce_cost_limit", cfg["enforce_cost_limit"])),
                }
            )
    except Exception as exc:
        logger.debug("[phoenix_full] budget config load failed, use defaults: %s", exc)

    return BudgetGuard(
        max_steps=cfg["max_steps"],
        max_visual_calls=cfg["max_visual_calls"],
        max_cost_usd=cfg["max_cost_usd"],
        enforce_cost_limit=cfg["enforce_cost_limit"],
    )


def _run_with_tier_budget_guard(agent, tier: str, task_text: str, run_fn):
    """Gate expensive tier execution before entering the heavy run."""
    if tier != "super_god":
        return run_fn()

    guard = _load_budget_guard()
    if guard is None:
        return run_fn()

    try:
        _, _, _, _, cost_max = _estimate_cost(task_text or "", tier)
        guard.gate(visual=False, estimated_cost_usd=cost_max)
        _ledger_record(
            "budget_gate",
            tier=tier,
            ok=True,
            estimated_cost_max=round(cost_max, 6),
            snapshot=guard.snapshot(),
        )
    except Exception as exc:
        reason = str(exc)
        _ledger_record("budget_gate", tier=tier, ok=False, error=reason[:200])
        return {
            "final_response": (
                "❌ 真神模式预算闸门已触发，已阻止本次高成本执行。\n"
                f"原因：{reason}\n"
                "可回复「降级」改用默认模型继续，或调整 phoenix 的 budget_guard 配置后重试。"
            ),
            "messages": [],
        }

    result = run_fn()
    try:
        _ledger_record("budget_gate_post", tier=tier, snapshot=guard.snapshot())
    except Exception:
        pass
    return result


def _run_tier_execution_with_ledger(agent, tier: str, task_text: str, run_fn):
    """Record start/end/error lifecycle for expensive tier execution."""
    if tier != "super_god":
        return run_fn()

    started_at = time.time()
    _ledger_record(
        "tier_execution_start",
        tier=tier,
        task_preview=(task_text or "")[:200],
        model=getattr(agent, "model", ""),
        provider=getattr(agent, "provider", ""),
    )

    try:
        result = _run_with_tier_budget_guard(agent, tier, task_text, run_fn)
        latency_ms = int((time.time() - started_at) * 1000)
        status = "ok"
        if isinstance(result, dict):
            final_text = str(result.get("final_response", ""))
            if final_text.startswith("❌"):
                status = "blocked_or_error"
            _ledger_record(
                "tier_execution_end",
                tier=tier,
                status=status,
                latency_ms=latency_ms,
                final_response_preview=final_text[:240],
            )
        else:
            _ledger_record("tier_execution_end", tier=tier, status=status, latency_ms=latency_ms)
        return result
    except Exception as exc:
        _ledger_record(
            "tier_execution_end",
            tier=tier,
            status="exception",
            latency_ms=int((time.time() - started_at) * 1000),
            error=str(exc)[:240],
        )
        raise


# 确认弹窗配置
_TIER_CONFIG = {
    "deep": {
        "name": "🟠 深度模式（Sonnet 4.6）",
        "model": "anthropic/claude-sonnet-4.6",
        "provider": "anthropic",
        "output_tokens_range": (3000, 8000),
    },
    "god": {
        "name": "🔴 大神模式（Opus 4.7）",
        "model": "anthropic/claude-opus-4.7",
        "provider": "anthropic",
        "output_tokens_range": (5000, 12000),
    },
    "super_god": {
        "name": "👑 真神模式（Opus 4.7 + GPT-5.5）",
        "model": "anthropic/claude-opus-4.7",
        "provider": "anthropic",
        "secondary_model": "openai/gpt-5.5",
        "secondary_provider": "openai",
        "output_tokens_range": (8000, 18000),
    },
}

# ============================================================
# 真实Token估算 + 成本计算（选项B：简单估算，不装依赖）
# ============================================================

# 各模型真实单价（$ / 1M tokens），从Anthropic/OpenAI官网获取
_MODEL_PRICING = {
    "claude-sonnet-4.6":  {"input": 3.0,  "output": 15.0},
    "claude-opus-4.7":    {"input": 15.0, "output": 75.0},
    "gpt-5.5":            {"input": 2.0,  "output": 8.0},
    "mimo-v2.5":          {"input": 0.0,  "output": 0.0},
    "mimo-v2.5-pro":      {"input": 0.0,  "output": 0.0},
}


def _estimate_input_tokens(text):
    """简单估算输入token数。中文≈1.5tok/字，英文≈0.75tok/word。"""
    if not text:
        return 0
    chinese_chars = sum(1 for c in text if '一' <= c <= '鿿')
    non_chinese = len(text) - chinese_chars
    # 英文按空格分词，每个词约0.75 token
    english_tokens = int(non_chinese * 0.75) if non_chinese > 0 else 0
    chinese_tokens = int(chinese_chars * 1.5) if chinese_chars > 0 else 0
    # +30% 安全余量（system prompt + 会话上下文）
    return int((english_tokens + chinese_tokens) * 1.3) + 200


def _estimate_output_tokens(tier, task_text):
    """根据任务类型和输入长度估算输出token范围。"""
    cfg = _TIER_CONFIG.get(tier, {})
    out_min, out_max = cfg.get("output_tokens_range", (3000, 8000))
    # 任务越长，输出越多
    input_len = len(task_text)
    if input_len > 200:
        return out_max, int(out_max * 1.5)
    elif input_len > 50:
        return out_min, out_max
    else:
        return int(out_min * 0.6), out_min


def _estimate_cost(text, tier):
    """计算真实预估成本。返回 (input_tok, out_min, out_max, cost_min, cost_max)。"""
    cfg = _TIER_CONFIG.get(tier, {})
    model_name = cfg.get("model", "").split("/")[-1]  # "anthropic/claude-sonnet-4.6" → "claude-sonnet-4.6"
    pricing = _MODEL_PRICING.get(model_name, {"input": 0, "output": 0})

    input_tok = _estimate_input_tokens(text)
    out_min, out_max = _estimate_output_tokens(tier, text)

    cost_min = (input_tok * pricing["input"] + out_min * pricing["output"]) / 1_000_000
    cost_max = (input_tok * pricing["input"] + out_max * pricing["output"]) / 1_000_000

    return input_tok, out_min, out_max, cost_min, cost_max



# ============================================================
# 懒加载
# ============================================================

def _get_phoenix():
    global _phoenix, _load_failed_at
    if _phoenix is not _SENTINEL:
        return _phoenix if _phoenix is not None else None
    if _load_failed_at and time.time() - _load_failed_at < 60:
        return None
    with _phoenix_lock:
        if _phoenix is not _SENTINEL:
            return _phoenix if _phoenix is not None else None
        if _load_failed_at and time.time() - _load_failed_at < 60:
            return None
        try:
            from phoenix import Phoenix
            _phoenix = Phoenix()
            logger.info("[phoenix_full] Phoenix V8 loaded")
            return _phoenix
        except Exception as e:
            logger.warning("[phoenix_full] load failed: %s", e)
            _load_failed_at = time.time()
            _phoenix = None
            return None


def _get_router():
    global _router
    if _router is None:
        try:
            from router.router import Router
            _router = Router()
        except Exception as exc:
            _ = exc
    return _router


# ============================================================
# ★ 核心：Monkey-patch 统一拦截（所有平台通用）
# ============================================================

def _make_confirm_box(tier, task_text):
    """生成确认框文本（使用真实Token估算）"""
    tc = _TIER_CONFIG[tier]
    task_preview = task_text[:30] + "..." if len(task_text) > 30 else task_text

    # 真实估算
    input_tok, out_min, out_max, cost_min, cost_max = _estimate_cost(task_text, tier)

    if cost_min == cost_max:
        cost_str = f"~${cost_min:.2f}"
    else:
        cost_str = f"~${cost_min:.2f} - ${cost_max:.2f}"

    _ledger_record(
        "confirm_box", tier=tier, model=tc.get("model"),
        input_tokens=input_tok, output_tokens_min=out_min, output_tokens_max=out_max,
        cost_min=round(cost_min, 6), cost_max=round(cost_max, 6), task_preview=task_preview
    )

    try:
        chain = _tier_binding_chain(tier)
        chain_text = " → ".join(f"{x.get('slot')}:{x.get('model')}" for x in chain) or tc['model']
    except Exception:
        chain_text = tc['model']

    return f"""
┌─────────────────────────────────────────┐
│  {tc['name']}
├─────────────────────────────────────────┤
│ 任务: {task_preview}
│ 主模型: {tc['model']}
│ 托底链: {chain_text}
│ 预估输入: ~{input_tok:,} tokens
│ 预估输出: ~{out_min:,} - {out_max:,} tokens
│ 预估成本: {cost_str}
├─────────────────────────────────────────┤
│ ⚠️ 高成本任务，请确认:
│ • 回复「确认」→ 执行
│ • 回复「降级」→ 用默认模型执行
│ • 回复「取消」→ 不执行
└─────────────────────────────────────────┘
"""


def _mimo_intent_analyze(text):
    """V8: 调MIMO做意图分析，判断任务是否需要深度AI处理。
    
    返回: "NORMAL" | "DEEP" | None
    成本: ~300 token，$0.001
    说明: 只负责意图判断，不做关键词兜底。
    """
    import requests
    
    # 读config拿MIMO API配置
    import yaml
    cfg_path = os.path.expanduser("~/.hermes/config.yaml")
    cfg = {}
    try:
        with open(cfg_path) as f:
            cfg = yaml.safe_load(f) or {}
    except Exception as exc:
        _ = exc
    
    delegation = cfg.get("delegation", {})
    api_key = delegation.get("api_key", "")
    base_url = delegation.get("base_url", "https://inference-api.nousresearch.com/v1")
    
    if not api_key:
        logger.warning("[phoenix_full] MIMO API key not found, skipping intent analysis")
        return None  # 无法分析，交给上层默认流程
    
    # 意图分析prompt（简洁版）— 减少歧义，缩短MIMO推理链，避免max_tokens截断
    prompt = f"""You are a routing classifier. Determine if the user request requires expensive deep analysis.

User request: {text[:500]}

Deep analysis (DEEP) is ONLY needed for:
- Design system/software architecture or detailed technical solutions
- Analyze a business model or strategy with multi-step reasoning
- Complex multi-step planning or research requiring synthesis

Everything else is NORMAL, including:
- Factual questions ("what is X", "explain Y", "X是什么", "深度学习是什么")
- Translation, chat, single questions
- Image description or analysis
- Short coding tasks or scripts

CRITICAL: "深度学习" means "deep learning" (a field of AI) — NOT a request for deep analysis.
Only trigger DEEP when user explicitly asks to DO analysis (e.g., "深度分析一下X", "帮我深入研究Y").

Reply with ONLY: [LEVEL:NORMAL] or [LEVEL:DEEP]"""
    
    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "xiaomi/mimo-v2.5",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1000,  # 推理模型需要足够token完成思考（500会截断→content=None）
                "temperature": 0.0,
            },
            timeout=15,  # 推理模型需要更长时间
        )
        resp.raise_for_status()
        msg = resp.json()["choices"][0]["message"]
        content = msg.get("content") or ""
        reasoning = msg.get("reasoning", "")
        
        # ★ 修复：推理模型优先用content（最终答案），reasoning只看最后一行
        # reasoning是思维链，包含"深度学习是..."等解释文本，会污染匹配
        if content.strip():
            check_text = content
        elif reasoning:
            # 从reasoning中提取最后一行（模型最终结论）
            lines = [l.strip() for l in reasoning.strip().splitlines() if l.strip()]
            check_text = lines[-1] if lines else ""
        else:
            check_text = ""
        
        if "[LEVEL:DEEP]" in check_text:
            logger.info("[phoenix_full] MIMO intent: DEEP (task: %s, check: %s)", text[:50], check_text[:80])
            return "DEEP"
        else:
            logger.info("[phoenix_full] MIMO intent: NORMAL (task: %s, check: %s)", text[:50], check_text[:80])
            return "NORMAL"
            
    except Exception as e:
        logger.warning("[phoenix_full] MIMO intent analyze failed: %s, skip auto escalation", e)
        return None  # 失败也不做关键词兜底


def _detect_high_tier(text):
    """V8初心回归版：只允许手动命令触发高成本模式。

    A方案铁律：普通文字/图片/链接/视频都先进默认模型处理，
    不做自动高成本升级，避免误触发和无声烧钱。

    触发方式：
    - /深度 xxx → deep
    - /大神 xxx → god
    - /真神 xxx → super_god
    """
    if not text:
        return None, None

    raw = text.strip()
    lowered = raw.lower()

    manual_triggers = [
        ("deep", ("/深度",)),
        ("god", ("/大神",)),
        ("super_god", ("/真神",)),
    ]

    for tier, prefixes in manual_triggers:
        if any(lowered.startswith(prefix.lower()) for prefix in prefixes):
            cfg = _TIER_CONFIG[tier]
            return tier, cfg

    return None, None


def _install_unified_intercept():
    """
    Monkey-patch AIAgent.run_conversation — 统一拦截所有平台。

    流程：
    1. 检查 _pending_confirm → 处理用户确认/降级/取消
    2. 检测高成本任务 → 存pending + 返回确认框（不调API）
    3. 非高成本 → 正常执行

    覆盖：CLI / TUI / Telegram / 飞书 / 微信
    （所有平台最终都调 run_conversation）
    """
    try:
        from run_agent import AIAgent

        if getattr(AIAgent, "_phoenix_unified_intercept", False):
            return

        _original_run_conversation = AIAgent.run_conversation

        def _wrapped_run_conversation(self, user_message, *args, **kwargs):
            global _last_user_message, _last_session_scope
            session_scope = _session_scope_from_agent(self)
            _last_session_scope = session_scope

            # 提取纯文本（过滤掉Hermes注入的图片描述，只保留用户真实输入）
            text = ""
            if isinstance(user_message, str):
                raw = user_message.strip()
                # Hermes把图片描述注入格式: "[The user attached an image. Here's what it contains:\n...\n]\n真实输入"
                # 只取最后一段（图片描述之后的真实用户文字）
                _IMG_MARKER = "[The user attached an image."
                if _IMG_MARKER in raw:
                    # 找到最后一个 ']' 之后的内容作为真实输入
                    bracket_end = raw.rfind("\n]\n")
                    if bracket_end != -1:
                        raw = raw[bracket_end + 3:].strip()
                    else:
                        # 没有找到结束标记，说明整条消息就是图片描述，无真实文字
                        raw = ""
                text = raw
                _last_user_message = text
            elif isinstance(user_message, list):
                # 如果消息包含 image_url 类型的 part，说明是图片消息，直接跳过路由
                has_image = any(
                    isinstance(p, dict) and p.get("type") in ("image_url", "image")
                    for p in user_message
                )
                if has_image:
                    return _original_run_conversation(self, user_message, *args, **kwargs)

                for part in user_message:
                    if isinstance(part, dict) and part.get("type") == "text":
                        raw_part = part.get("text", "").strip()
                        # 同样过滤掉Hermes注入的图片描述标记
                        _IMG_MARKER = "[The user attached an image."
                        if _IMG_MARKER in raw_part:
                            bracket_end = raw_part.rfind("\n]\n")
                            if bracket_end != -1:
                                raw_part = raw_part[bracket_end + 3:].strip()
                            else:
                                raw_part = ""
                        text = raw_part
                        _last_user_message = text
                        break

            if not text:
                return _original_run_conversation(self, user_message, *args, **kwargs)

            pending = _get_pending_confirm(session_scope)

            # ─── Step 1A: Gateway rewrite 已确认/降级的任务 ───
            if pending and pending.get("action") in ("confirm", "downgrade"):
                action = pending.get("action")
                original_task = pending.get("task", text)
                tier = pending.get("tier")
                target_model = pending.get("model")
                old_model = getattr(self, "model", "")
                old_provider = getattr(self, "provider", "")
                if action == "confirm" and target_model:
                    if not getattr(self, "_phoenix_default_model", None):
                        self._phoenix_default_model = old_model
                        self._phoenix_default_provider = old_provider
                    switched = _do_model_switch(self, target_model, tier)
                    if not switched:
                        _set_pending_confirm(session_scope, None)
                        return {"final_response": f"❌ 模型切换失败，已取消执行：{target_model}", "messages": []}
                result = _run_tier_execution_with_ledger(
                    self,
                    tier,
                    original_task,
                    lambda: _original_run_conversation(self, original_task, *args, **kwargs),
                )
                if action == "confirm":
                    try:
                        default_model = getattr(self, "_phoenix_default_model", old_model)
                        if getattr(self, "model", "") != default_model:
                            _do_model_switch(self, default_model, "daily")
                            logger.info("[phoenix_full] switched back to default: %s", default_model)
                    except Exception as exc:
                        _ = exc
                _set_pending_confirm(session_scope, None)
                return result

            # ─── Step 1: 检查是否有待确认的回复 ───
            if pending and pending.get("action") is None:
                if text in ["确认", "confirm", "确定", "ok", "OK"]:
                    original_task = pending["task"]
                    tier = pending["tier"]
                    target_model = pending["model"]
                    pending["action"] = "confirm"
                    _set_pending_confirm(session_scope, pending)
                    
                    # ★ 调用switch_model做完整切换（不只改model名，还重建client）
                    old_model = getattr(self, "model", "")
                    old_provider = getattr(self, "provider", "")
                    switched = _do_model_switch(self, target_model, tier)
                    
                    if switched:
                        logger.info("[phoenix_full] user confirmed %s, model switched: %s → %s",
                                    tier, old_model, getattr(self, "model", "?"))
                    else:
                        _ledger_record("tier_execution_switch_failed", tier=tier, model=target_model, reason="switch_model_failed")
                        _set_pending_confirm(session_scope, None)
                        logger.warning("[phoenix_full] switch_model failed, cancel expensive task")
                        return {"final_response": f"❌ 模型切换失败，已取消执行：{target_model}", "messages": []}
                    
                    result = _run_tier_execution_with_ledger(
                        self,
                        tier,
                        original_task,
                        lambda: _original_run_conversation(self, original_task, *args, **kwargs),
                    )
                    
                    # ★ 任务完成，切回默认模型
                    try:
                        default_model = getattr(self, "_phoenix_default_model", old_model)
                        default_provider = getattr(self, "_phoenix_default_provider", old_provider)
                        if getattr(self, "model", "") != default_model:
                            _do_model_switch(self, default_model, "daily")
                            logger.info("[phoenix_full] switched back to default: %s", default_model)
                    except Exception as exc:
                        _ = exc
                    
                    _set_pending_confirm(session_scope, None)
                    return result

                elif text in ["降级", "downgrade", "降低", "低配"]:
                    original_task = pending["task"]
                    _ledger_record("tier_execution_downgraded", tier=pending.get("tier"), task_preview=original_task[:200])
                    pending["action"] = "downgrade"
                    _set_pending_confirm(session_scope, pending)
                    logger.info("[phoenix_full] user downgraded, using default model")
                    result = _original_run_conversation(self, original_task, *args, **kwargs)
                    _set_pending_confirm(session_scope, None)
                    return result

                elif text in ["取消", "cancel", "算了", "不要"]:
                    _ledger_record("tier_execution_cancelled", tier=pending.get("tier"), task_preview=pending.get("task", "")[:200])
                    _set_pending_confirm(session_scope, None)
                    logger.info("[phoenix_full] user cancelled")
                    return {"final_response": "✓ 已取消", "messages": []}

            # ─── Step 2: 检测高成本任务 → 弹确认框 ───
            # 如果 _pending_confirm 已有 action，说明是 Gateway rewrite，
            # 不要覆盖，直接放行到原始 run_conversation
            if pending and pending.get("action") is not None:
                return _original_run_conversation(self, user_message, *args, **kwargs)

            tier, tier_cfg = _detect_high_tier(text)
            if tier:
                # 保存当前模型信息，任务完成后切回
                if not getattr(self, "_phoenix_default_model", None):
                    self._phoenix_default_model = getattr(self, "model", "")
                    self._phoenix_default_provider = getattr(self, "provider", "")
                
                target_model, target_provider = _resolve_tier_primary(tier, tier_cfg.get("model"))
                _set_pending_confirm(session_scope, {
                    "task": text,
                    "tier": tier,
                    "model": target_model,
                    "provider": target_provider,
                    "route_chain": _tier_binding_chain(tier),
                    "action": None,
                })
                confirm_box = _make_confirm_box(tier, text)
                logger.info("[phoenix_full] confirm dialog shown for %s: %s",
                            tier, text[:50])
                # 返回确认框作为响应，不调API
                return {"final_response": confirm_box, "messages": []}

            # ─── Step 3: 日常/中等任务不自动切换，直接走当前主模型 ───
            # Phoenix 5.1.1-hotfix: 用户反馈自动切换导致 Provider Runtime 掉 P。
            # 这里只保留 /深度 /大神 /真神 的手动确认链路；其它内容不触发模型切换。
            return _original_run_conversation(self, user_message, *args, **kwargs)

        AIAgent.run_conversation = _wrapped_run_conversation
        AIAgent._phoenix_unified_intercept = True
        logger.info("[phoenix_full] unified intercept installed (all platforms)")
    except Exception as e:
        logger.warning("[phoenix_full] unified intercept install failed: %s", e)


def _install_chat_patch():
    """
    额外包装 AIAgent.chat — CLI专用入口。
    虽然 chat() 内部调 run_conversation() 已被拦截，
    但 chat() 本身也需要捕获消息用于确认链路。
    """
    try:
        from run_agent import AIAgent

        if getattr(AIAgent, "_phoenix_chat_patch", False):
            return

        _original_chat = AIAgent.chat

        def _wrapped_chat(self, message, *args, **kwargs):
            global _last_user_message
            if isinstance(message, str) and message.strip():
                _last_user_message = message.strip()
            try:
                return _original_chat(self, message, *args, **kwargs)
            finally:
                _last_user_message = ""

        AIAgent.chat = _wrapped_chat
        AIAgent._phoenix_chat_patch = True
        logger.info("[phoenix_full] chat patch installed")
    except Exception as e:
        logger.warning("[phoenix_full] chat patch install failed: %s", e)


# ============================================================
# 注册
# ============================================================

def register(manager):
    """注册插件hooks"""
    _install_unified_intercept()
    _install_chat_patch()

    def _queue_phoenix_line(trigger: str):
        """经典 CLI：/深度 被 Hermes 当 slash 吃掉时，把整行注入对话队列。"""

        def _handler(raw_args: str) -> str:
            tail = (raw_args or "").strip()
            msg = f"{trigger} {tail}".strip() if tail else trigger
            if manager.inject_message(msg):
                return "（不死鸟）已加入对话队列，下一轮按该指令路由。"
            return (
                "（当前无 CLI 注入通道，常见于仅 Gateway/TUI）"
                "在 TUI 里输入「/深度 …」会作为对话发送；或直接向助手发同一行文字。"
            )

        return _handler

    manager.register_command(
        "深度",
        _queue_phoenix_line("/深度"),
        description="不死鸟：深度模式（等同发送「/深度 …」给对话）",
        args_hint="任务",
    )
    manager.register_command(
        "大神",
        _queue_phoenix_line("/大神"),
        description="不死鸟：大神模式",
        args_hint="任务",
    )
    manager.register_command(
        "真神",
        _queue_phoenix_line("/真神"),
        description="不死鸟：真神模式",
        args_hint="任务",
    )

    manager.register_hook("pre_gateway_dispatch", _on_pre_gateway_dispatch)
    manager.register_hook("pre_tool_call", _on_pre_tool_call)
    manager.register_hook("pre_api_request", _on_pre_api_request)
    manager.register_hook("post_api_request", _on_post_api_request)
    manager.register_hook("on_session_start", _on_session_start)
    manager.register_hook("on_session_finalize", _on_session_finalize)
    manager.register_hook("on_session_reset", _on_session_reset)
    logger.info("[phoenix_full] hooks registered (V8: manual upgrade + auto fallback)")


# ============================================================
# pre_gateway_dispatch: Gateway平台的确认弹窗（TUI/Telegram/飞书/微信）
# ============================================================

def _on_pre_gateway_dispatch(**kwargs):
    """
    Gateway分发前：确认弹窗（TUI/Telegram/飞书/微信）

    仅处理确认回复（用户输入"确认/降级/取消"时rewrite为原始任务）。
    新高成本任务的确认框由 run_conversation 的 monkey-patch 统一处理。
    """
    global _last_session_scope

    event = kwargs.get("event")
    if not event or not hasattr(event, "text"):
        return None

    session_scope = _session_scope_from_event(event)
    _last_session_scope = session_scope
    pending = _get_pending_confirm(session_scope)
    text = event.text.strip()

    # 有待确认 → 处理用户回复
    if pending and pending.get("action") is None:
        if text in ["确认", "confirm", "确定", "ok", "OK"]:
            original_task = pending["task"]
            pending["action"] = "confirm"
            _set_pending_confirm(session_scope, pending)
            logger.info("[phoenix_full] gateway confirmed: %s", original_task[:50])
            return {"action": "rewrite", "text": original_task}

        elif text in ["降级", "downgrade", "降低", "低配"]:
            original_task = pending["task"]
            pending["action"] = "downgrade"
            _set_pending_confirm(session_scope, pending)
            logger.info("[phoenix_full] gateway downgraded")
            return {"action": "rewrite", "text": original_task}

        elif text in ["取消", "cancel", "算了", "不要"]:
            _set_pending_confirm(session_scope, None)
            logger.info("[phoenix_full] gateway cancelled")
            return {"action": "rewrite", "text": "✓ 已取消"}

    return None  # 不干预，交给 run_conversation 的 monkey-patch 处理





# ============================================================
# Provider解析：正确的模型切换（调switch_model而非只改model名）
# ============================================================

def _is_high_risk_tool_name(tool_name: str) -> bool:
    name = (tool_name or "").strip().lower()
    if not name:
        return False
    if name in _HIGH_RISK_TOOL_NAMES:
        return True
    risky_prefixes = ("git_", "terminal_", "file_patch", "file_write", "delete_", "remove_")
    return any(name.startswith(prefix) for prefix in risky_prefixes)


def _on_pre_tool_call(**kwargs):
    """Hard gate: during /真神 confirm-run, risky tools require explicit confirmation."""
    pc = _get_pending_confirm(_last_session_scope) or {}
    if pc.get("tier") != "super_god" or pc.get("action") != "confirm":
        return None

    tool_name = kwargs.get("tool_name", "")
    if not _is_high_risk_tool_name(tool_name):
        return None

    args = kwargs.get("args") or {}
    confirmed = isinstance(args, dict) and bool(args.get("user_confirmed_high_risk"))
    if confirmed:
        return None

    block_msg = (
        "Phoenix 真神模式已拦截高风险工具调用："
        f"`{tool_name}` 需要显式参数 `user_confirmed_high_risk=true`。"
    )
    _ledger_record(
        "high_risk_tool_blocked",
        tier="super_god",
        tool=tool_name,
        reason="missing_user_confirmed_high_risk",
    )
    return {"action": "block", "message": block_msg}


def _classify_route(user_message):
    """V8: 自动升档已关闭。保留函数只为旧调用兼容，固定返回 daily。"""
    return {"tier": "daily", "task_type": "chat", "model": "", "provider": "", "reason": "manual_only_hotfix"}



def _load_phoenix_config():
    cfg_path = PHOENIX_DIR / "config.json"
    if not cfg_path.exists():
        raise ValueError(f"Phoenix config 不存在: {cfg_path}")
    with open(cfg_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _tier_binding_chain(tier):
    """返回当前档位的 primary/fallback/emergency 链。只返回脱敏结构，不含真实Key。"""
    data = _load_phoenix_config()
    tiers = data.get("phoenix_open", {}).get("model_tiers", {})
    t = tiers.get(tier) or {}
    chain = []
    if t.get("model"):
        chain.append({"slot": "primary", "model": t.get("model"), "provider": t.get("provider")})
    # super_god 额外记录 secondary 预留，不默认并行执行
    if tier == "super_god" and t.get("model_b"):
        chain.append({"slot": "secondary_reserved", "model": t.get("model_b"), "provider": t.get("provider_b")})
    for slot in ("fallback", "emergency"):
        v = t.get(slot) or {}
        if isinstance(v, dict) and v.get("model"):
            chain.append({"slot": slot, "model": v.get("model"), "provider": v.get("provider") or t.get("provider")})
    return chain


def _resolve_tier_primary(tier, fallback_model=None):
    """从 phoenix_open.model_tiers 读取档位主模型，配置缺失时回退到 _TIER_CONFIG。"""
    try:
        chain = _tier_binding_chain(tier)
        for item in chain:
            if item.get("slot") == "primary" and item.get("model"):
                return item.get("model"), item.get("provider")
    except Exception as exc:
        logger.debug("[phoenix_full] tier config load failed: %s", exc)
    cfg = _TIER_CONFIG.get(tier, {})
    return fallback_model or cfg.get("model"), cfg.get("provider")

def _resolve_provider_for_model(model_name, provider_name=None):
    """V8: 用 Phoenix ProviderResolver 解析完整 provider/base_url/api_key。

    返回字段：provider/base_url/api_key/api_key_env/is_local/source。
    不再用“当前provider”兜底，避免 Key 串位。
    """
    import json
    import os

    cfg_path = PHOENIX_DIR / "config.json"
    if not cfg_path.exists():
        raise ValueError(f"Phoenix config 不存在: {cfg_path}")
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    from core.provider_resolver import ProviderResolver
    resolver = ProviderResolver(cfg)
    binding = resolver.resolve_binding(model_name, provider_name)

    api_key = ""
    if binding.api_key_env:
        api_key = os.environ.get(binding.api_key_env, "")
    elif binding.api_key:
        api_key = binding.api_key

    return {
        "provider": binding.provider,
        "base_url": binding.base_url,
        "api_key": api_key,
        "api_key_env": binding.api_key_env,
        "is_local": binding.is_local,
        "source": binding.source,
    }

def _do_model_switch(agent, target_model, tier):
    """调用 AIAgent.switch_model() 做完整切换。V8：primary失败后按本档 fallback/emergency 依次尝试。"""
    tried = []
    try:
        chain = _tier_binding_chain(tier) if tier else []
    except Exception:
        chain = []
    candidates = []
    if target_model:
        candidates.append({"slot": "primary", "model": target_model, "provider": None})
    for item in chain:
        if item.get("slot") == "secondary_reserved":
            continue
        if item.get("model") and item.get("model") not in [c.get("model") for c in candidates]:
            candidates.append(item)
    if not candidates:
        candidates = [{"slot": "primary", "model": target_model, "provider": None}]

    for item in candidates:
        model = item.get("model")
        provider_hint = item.get("provider")
        if not model:
            continue
        try:
            tier_cfg = _TIER_CONFIG.get(tier, {}) if tier else {}
            if not provider_hint:
                provider_hint = tier_cfg.get("provider")
            if not provider_hint and tier in ("deep", "god", "super_god"):
                if model.startswith("anthropic/"):
                    provider_hint = "anthropic"
                elif model.startswith("openai/"):
                    provider_hint = "openai"
                elif model.startswith("xiaomi/") or "mimo" in model:
                    provider_hint = "xiaomi"

            binding = _resolve_provider_for_model(model, provider_hint)
            agent.switch_model(
                model,
                binding.get("provider", ""),
                binding.get("api_key", ""),
                binding.get("base_url", ""),
                "chat_completions",
            )
            logger.info(
                "[phoenix_full] switch_model OK: slot=%s model=%s provider=%s base_url=%s key=%s source=%s",
                item.get("slot"), model, binding.get("provider"), binding.get("base_url"),
                f"env:{binding.get('api_key_env')}" if binding.get("api_key_env") else "[REDACTED]",
                binding.get("source"),
            )
            _ledger_record(
                "switch_model", tier=tier, slot=item.get("slot"), model=model, provider=binding.get("provider"),
                base_url=binding.get("base_url"), api_key_env=f"env:{binding.get('api_key_env')}" if binding.get("api_key_env") else "",
                source=binding.get("source"), ok=True
            )
            if item.get("slot") in ("fallback", "emergency"):
                _ledger_record("fallback_used", tier=tier, slot=item.get("slot"), model=model, provider=binding.get("provider"))
            return True
        except Exception as e:
            tried.append(f"{item.get('slot')}:{model}:{e}")
            logger.warning("[phoenix_full] switch candidate failed: slot=%s model=%s err=%s", item.get("slot"), model, e)
            _ledger_record("switch_model", tier=tier, slot=item.get("slot"), model=model, ok=False, error=str(e)[:160])

    # 兼容回退：Hermes原生解析器。只作为最后兜底，不作为主路径。
    try:
        from hermes_cli.model_switch import switch_model as resolve_switch
        result = resolve_switch(
            raw_input=target_model,
            current_provider=getattr(agent, "provider", ""),
            current_model=getattr(agent, "model", ""),
            current_base_url=getattr(agent, "base_url", ""),
            current_api_key=getattr(agent, "api_key", ""),
        )
        if result.success:
            agent.switch_model(
                result.new_model,
                result.target_provider,
                result.api_key or "",
                result.base_url or "",
                result.api_mode or "chat_completions",
            )
            logger.info("[phoenix_full] hermes fallback switch_model OK: %s", result.new_model)
            return True
        logger.warning("[phoenix_full] hermes fallback resolve failed: %s", result.error_message)
        return False
    except Exception as e:
        logger.warning("[phoenix_full] switch_model failed after candidates=%s err=%s", tried, e)
        return False

# ============================================================
# pre_api_request: 五档手动路由（所有平台通用）
# ============================================================

def _on_pre_api_request(**kwargs):
    """
    API调用前：五档手动路由

    通过 _last_user_message（monkey-patch捕获）获取用户消息，
    使用 RouterEngine 做分类和模型选择。
    """
    pending = _get_pending_confirm(_last_session_scope)

    # 优先处理pending确认（Gateway rewrite后的模型切换）
    if pending:
        action = pending.get("action")
        if action == "confirm":
            model = pending["model"]
            tier = pending["tier"]
            logger.warning(
                "[phoenix_full] BLOCKED fake hook switch for %s (%s): switch_model must happen in run_conversation",
                model, tier
            )
            return None
        elif action == "downgrade":
            _set_pending_confirm(_last_session_scope, None)
            logger.info("[phoenix_full] using default model (downgraded)")
            return None

    # Phoenix V8: 关闭 RouterEngine 自动路由。
    # 根因：Hermes 0.13 的 transport registry 只注册 chat_completions/codex_responses/anthropic_messages/bedrock_converse；
    # 旧插件把 OpenAI 兼容模型切到错误 legacy transport 名称时，_get_transport() 返回 None，随后触发
    # 'NoneType' object has no attribute 'build_kwargs'。
    # 所以此 hook 绝不返回模型覆盖，也不做中等/关键词自动切换。
    return None


# ============================================================
# post_api_request / Session hooks
# ============================================================

def _on_post_api_request(**kwargs):
    """API调用后：记录模型表现"""
    try:
        phoenix = _get_phoenix()
        if not phoenix:
            return None
        model = kwargs.get("model", "")
        success = kwargs.get("success", True)
        latency = kwargs.get("latency", 0)
        cost = kwargs.get("cost", 0)
        if model and hasattr(phoenix, 'report_model_result'):
            phoenix.report_model_result(model=model, task_type="gateway",
                                        latency=latency, cost=cost, success=success)
        if model:
            _ledger_record("api_result", model=model, success=success, latency=latency, cost=cost)
    except Exception as exc:
        _ = exc
    return None


def _on_session_start(**kwargs):
    try:
        phoenix = _get_phoenix()
        if phoenix and hasattr(phoenix, 'memory_system'):
            recovery = phoenix.memory_system.recover_from_crash()
            if recovery.get("recovered"):
                logger.info("[phoenix_full] memory recovered")
    except Exception as exc:
        _ = exc
    return None


def _on_session_finalize(**kwargs):
    try:
        phoenix = _get_phoenix()
        if phoenix and hasattr(phoenix, 'shutdown'):
            phoenix.shutdown()
    except Exception as exc:
        _ = exc
    return None


def _on_session_reset(**kwargs):
    global _last_user_message, _last_session_scope
    session_id = str(kwargs.get("session_id") or "").strip()
    if session_id:
        _set_pending_confirm(f"session:{session_id}", None)
    else:
        _clear_all_pending_confirms()
    _last_session_scope = "global"
    _last_user_message = ""

    try:
        phoenix = _get_phoenix()
        if phoenix and hasattr(phoenix, 'memory_system'):
            phoenix.memory_system.clear_short_term()
    except Exception as exc:
        _ = exc
    return None
