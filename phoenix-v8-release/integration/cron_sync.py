"""
不死鸟 Phoenix V8 — Cron定时任务配置

提供给hermes-agent的cron系统调用。
每隔30分钟自动同步记忆、触发进化、健康检查。
"""

import sys
import json
from pathlib import Path

PHOENIX_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PHOENIX_DIR))

from phoenix import Phoenix


def cron_sync():
    """
    定时同步（每30分钟调用一次）

    做的事：
    1. 会话记忆 → 长期记忆
    2. 提取记忆 → 长期记忆
    3. 触发进化检查
    4. 健康检查
    5. 输出状态摘要
    """
    phoenix = Phoenix()

    # 触发进化
    events = phoenix.evolve()

    # 获取健康状态
    health = phoenix.health_check()

    # 输出摘要
    summary = {
        "type": "phoenix_cron_sync",
        "evolution_events": len(events),
        "system_mode": health["system"]["mode"],
        "budget_used": health["system"]["budget_used"],
        "active_tasks": health["system"]["active_tasks"],
        "antibodies": health["antibodies"]["total"],
        "memory_count": health["memory"]["extraction"]["total"],
    }

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    cron_sync()
