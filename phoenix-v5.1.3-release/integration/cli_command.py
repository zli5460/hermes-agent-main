"""
🦅 不死鸟 Phoenix — CLI 集成

用法:
  /phoenix status    — 查看不死鸟状态
  /phoenix route 消息 — 用不死鸟路由处理消息
  /phoenix test      — 跑全链路测试
  /phoenix on        — 开启不死鸟Hook
  /phoenix off       — 关闭不死鸟Hook
"""
import sys
from pathlib import Path

PHOENIX_DIR = Path.home() / ".hermes" / "phoenix"
sys.path.insert(0, str(PHOENIX_DIR))


def handle_phoenix_command(args: str) -> str:
    """处理 /phoenix 命令"""
    parts = args.strip().split(None, 1)
    subcmd = parts[0].lower() if parts else "status"
    rest = parts[1] if len(parts) > 1 else ""

    if subcmd == "status":
        return _status()
    elif subcmd == "route":
        return _route(rest)
    elif subcmd == "test":
        return _test()
    elif subcmd == "on":
        return _toggle(True)
    elif subcmd == "off":
        return _toggle(False)
    else:
        return (
            "🦅 不死鸟 Phoenix 命令:\n"
            "  /phoenix status — 查看状态\n"
            "  /phoenix route 消息 — 路由测试\n"
            "  /phoenix test — 全链路测试\n"
            "  /phoenix on — 开启\n"
            "  /phoenix off — 关闭"
        )


def _status() -> str:
    """查看不死鸟状态"""
    try:
        from phoenix import Phoenix
        p = Phoenix()
        health = p.health_check()

        models = p.config.get("router.models", {})
        lines = ["🦅 **不死鸟 Phoenix V1 状态**\n"]

        # 路由层
        r = models.get("routing", {})
        lines.append("**路由层（大脑）:**")
        lines.append(f"  ① {r.get('primary', '?').split('/')[-1]}")
        lines.append(f"  ② {r.get('fallback', '?').split('/')[-1]}")
        lines.append(f"  ③ {r.get('emergency', '?').split('/')[-1]}")

        # 执行层
        lines.append("\n**执行层（工人）:**")
        for task in ["chat", "code", "reasoning", "subtask"]:
            m = models.get(task, {})
            chain = f"  {task}: {m.get('primary', '?').split('/')[-1]}"
            if m.get("fallback"):
                chain += f" → {m['fallback'].split('/')[-1]}"
            if m.get("emergency"):
                chain += f" → {m['emergency'].split('/')[-1]}"
            lines.append(chain)

        # 系统状态
        lines.append(f"\n**系统:**")
        lines.append(f"  模式: {health.get('system', {}).get('mode', 'normal')}")
        lines.append(f"  抗体: {health.get('antibodies', {}).get('active', 0)}个活跃")
        lines.append(f"  记忆: {health.get('memory', {}).get('extraction', {}).get('total', 0)}条")

        return "\n".join(lines)
    except Exception as e:
        return f"❌ 不死鸟状态异常: {e}"


def _route(message: str) -> str:
    """用不死鸟路由处理消息"""
    if not message:
        return "用法: /phoenix route 你的消息"

    try:
        from phoenix import Phoenix
        p = Phoenix()
        decision = p.route(message)

        return (
            f"🦅 **不死鸟路由决策**\n"
            f"消息: {message[:50]}\n"
            f"任务类型: {decision.task_type}\n"
            f"选中模型: {decision.model.split('/')[-1]}\n"
            f"成本等级: {decision.estimated_cost_tier}\n"
            f"原因: {decision.reason}"
        )
    except Exception as e:
        return f"❌ 路由失败: {e}"


def _test() -> str:
    """跑全链路测试"""
    try:
        from integration.hermes_bridge import test
        test()
        return "✅ 全链路测试完成，查看终端输出"
    except Exception as e:
        return f"❌ 测试失败: {e}"


def _toggle(enable: bool) -> str:
    """开关不死鸟Hook"""
    try:
        from integration.hooks import get_hook
        hook = get_hook()
        if enable:
            hook.enable()
            return "🦅 不死鸟已开启"
        else:
            hook.disable()
            return "🔴 不死鸟已关闭"
    except Exception as e:
        return f"❌ 操作失败: {e}"
