"""不死鸟 Phoenix V8 — 子agent路由
从subagent_routing.json读取路由配置（含fallback），不再硬编码

用法:
    from phoenix.router.subagent_router import route_subagent
    result = route_subagent("帮我写个Python爬虫")
"""

import json
import sys
from pathlib import Path
from typing import Dict, Optional

# 添加phoenix到路径
sys.path.insert(0, str(Path.home() / ".hermes"))

CONFIG_PATH = Path.home() / ".hermes" / "phoenix" / "config" / "subagent_routing.json"


def _load_config() -> Dict:
    """加载路由配置"""
    try:
        if CONFIG_PATH.exists():
            return json.loads(CONFIG_PATH.read_text())
    except Exception as exc:
        _ = exc
    return {"task_routing": {}, "models": {}}


def route_subagent(task: str) -> Dict:
    """
    为子agent选择模型（含fallback）

    Args:
        task: 任务描述

    Returns:
        {
            "model": str,           # 主力模型
            "fallback": str,        # 备用模型
            "task_type": str,       # 匹配的任务类型
            "reason": str,          # 选择原因
        }
    """
    from phoenix.router.engine import TaskClassifier

    tc = TaskClassifier()
    task_type = tc.classify(task)

    config = _load_config()
    task_routing = config.get("task_routing", {})

    # 1. 精确匹配任务类型
    for task_key, route in task_routing.items():
        if task_key in task:
            return {
                "model": route["model"],
                "fallback": route.get("fallback", ""),
                "task_type": task_type,
                "reason": route.get("reason", f"匹配任务: {task_key}"),
            }

    # 2. 根据TaskClassifier结果匹配
    CATEGORY_TO_TASK = {
        "chat": "简单问答",
        "code_small": "爬虫",
        "code_medium": "代码编写",
        "code_large": "代码架构",
        "reasoning_light": "简单问答",
        "reasoning": "深度推理",
        "vision": "视觉",
    }

    mapped_task = CATEGORY_TO_TASK.get(task_type, "简单问答")
    if mapped_task in task_routing:
        route = task_routing[mapped_task]
        return {
            "model": route["model"],
            "fallback": route.get("fallback", ""),
            "task_type": task_type,
            "reason": route.get("reason", f"分类映射: {task_type} → {mapped_task}"),
        }

    # 3. 默认
    return {
        "model": "xiaomi/mimo-v2.5",
        "fallback": "openai/gpt-5.4-mini",
        "task_type": task_type,
        "reason": "默认chat模型",
    }


if __name__ == "__main__":
    # 测试
    tasks = [
        "帮我写个Python爬虫",
        "分析这个系统架构",
        "你好",
        "帮我处理这张图片",
        "写一段文案",
        "翻译这段话",
        "深度推理一下这个方案",
    ]

    print("=== 子agent路由测试（含fallback）===")
    for task in tasks:
        route = route_subagent(task)
        fb = route['fallback'] or '无'
        print(f"  {task:20} → {route['model']:35} 备用: {fb}")
