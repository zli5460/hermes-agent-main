"""不死鸟 Phoenix V5.1 — 子agent智能路由（可扩展版）
从配置文件读取路由规则，用户可自定义添加任务类型和模型

用法:
    from phoenix.router.subagent_model_router import select_subagent_model
    result = select_subagent_model("code_medium", "审查这段代码")
"""

import json
from pathlib import Path
from typing import Dict

# 加载路由配置
CONFIG_PATH = Path.home() / ".hermes" / "phoenix" / "config" / "subagent_routing.json"

def _load_config() -> Dict:
    """加载路由配置"""
    try:
        if CONFIG_PATH.exists():
            return json.loads(CONFIG_PATH.read_text())
    except Exception as exc:
        _ = exc
    return {"task_routing": {}, "models": {}}

def select_subagent_model(task_type: str, task_description: str = "") -> Dict:
    """
    根据任务类型和描述选择最优子agent模型
    
    路由规则：
    1. 精确匹配任务类型
    2. 模糊匹配任务描述中的关键词
    3. 默认使用chat模型
    """
    config = _load_config()
    task_routing = config.get("task_routing", {})
    models = config.get("models", {})
    
    # 1. 精确匹配任务类型
    for task_key, route in task_routing.items():
        if task_key in task_type:
            return {
                "model": route["model"],
                "cost_tier": models.get(route["model"], {}).get("cost", "unknown"),
                "fallback": route.get("fallback", ""),
                "reason": route.get("reason", f"匹配任务类型: {task_key}"),
            }
    
    # 2. 模糊匹配任务描述
    if task_description:
        for task_key, route in task_routing.items():
            if task_key in task_description:
                return {
                    "model": route["model"],
                    "cost_tier": models.get(route["model"], {}).get("cost", "unknown"),
                    "fallback": route.get("fallback", ""),
                    "reason": route.get("reason", f"匹配描述: {task_key}"),
                }
    
    # 3. 默认
    return {
        "model": "xiaomi/mimo-v2.5",
        "cost_tier": "low",
        "fallback": "openai/gpt-5.4-mini",
        "reason": "默认chat模型",
    }

def get_model_for_task(task_type: str) -> str:
    """简单接口：返回模型名"""
    return select_subagent_model(task_type)["model"]

def add_task_routing(task_key: str, model: str, reason: str = ""):
    """动态添加任务路由（运行时扩展）"""
    config = _load_config()
    config.setdefault("task_routing", {})[task_key] = {
        "model": model,
        "reason": reason,
    }
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2))
