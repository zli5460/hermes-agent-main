"""
Phoenix Gateway Hook — 路由覆盖

作为gateway hook加载，在每次消息处理时覆盖模型路由，
让Phoenix的智能路由替代Hermes的V1路由。

集成方式：通过gateway的hook系统自动加载。
将此文件放到 gateway/builtin_hooks/ 或通过 config 注册。
"""

import os
import sys
import time
import json
import logging
from pathlib import Path

logger = logging.getLogger("phoenix.hooks.routing_override")

# 确保phoenix在path中
HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
if str(HERMES_HOME) not in sys.path:
    sys.path.insert(0, str(HERMES_HOME))


def on_turn_route(message: str, current_model: str, context: dict = None) -> dict:
    """V8: 旧路由覆盖钩子已降级为只读观测。

    Phoenix V8 的模型切换唯一入口是 phoenix_full 插件里的
    run_conversation monkey-patch + AIAgent.switch_model() 真切换。
    这里绝不返回 override=True，避免再次出现只改 model 字符串的假切换。
    """
    return {
        "model": current_model,
        "override": False,
        "reason": "Phoenix V8: model switching is owned by phoenix_full.switch_model",
    }


def on_model_result(model: str, task_type: str, latency: float, success: bool, error: str = ""):
    """
    模型调用结果回调
    
    在gateway完成模型调用后触发，用于Phoenix的熔断器和进化系统。
    """
    try:
        from phoenix.integration.gateway_api import phoenix_gateway
        
        if phoenix_gateway.is_ready:
            phoenix_gateway.report_result(
                model=model,
                task_type=task_type,
                latency=latency,
                success=success,
                error=error,
            )
    except Exception as e:
        logger.debug("Phoenix result hook failed (non-critical): %s", e)


def on_message_process(message: str, source: dict = None) -> dict:
    """
    消息处理钩子
    
    在gateway处理每条消息时触发：
    1. 自动提取记忆 + 更新知识图谱 + 写日记
    2. 加载已有记忆注入到system prompt
    
    Returns:
        {
            "context_injection": str,  # 注入到system prompt的内容
            "memories": list,          # 提取的记忆
        }
    """
    try:
        from phoenix.integration.gateway_api import phoenix_gateway
        from phoenix.integration.memory_auto import phoenix_memory
        
        # 1. 自动提取记忆（每条消息都跑）
        try:
            phoenix_memory.on_message(
                user_message=message,
                model=source.get("model", "") if source else "",
                task_type=source.get("task_type", "") if source else "",
            )
        except Exception as e:
            logger.debug("Phoenix memory extract failed: %s", e)
        
        # 2. 加载已有记忆注入prompt
        context = ""
        if phoenix_gateway.is_ready:
            context = phoenix_gateway.load_memories()
        
        return {
            "context_injection": context,
            "memories": [],
        }
        
    except Exception as e:
        logger.debug("Phoenix message hook failed (non-critical): %s", e)
        return {"context_injection": "", "memories": []}


def on_startup():
    """
    Gateway启动钩子
    
    在gateway启动时触发，初始化Phoenix系统。
    """
    try:
        from phoenix.integration.gateway_api import phoenix_gateway
        
        if phoenix_gateway.is_ready:
            logger.info("Phoenix gateway hook: initialized and ready")
        else:
            logger.warning("Phoenix gateway hook: init failed - %s", phoenix_gateway.init_error)
            
    except Exception as e:
        logger.warning("Phoenix startup hook failed: %s", e)


def on_shutdown():
    """
    Gateway关闭钩子
    
    在gateway关闭时触发，保存Phoenix状态。
    """
    try:
        from phoenix.integration.gateway_api import phoenix_gateway
        
        if phoenix_gateway.is_ready:
            # 触发进化检查
            phoenix_gateway.evolve()
            logger.info("Phoenix gateway hook: shutdown complete")
            
    except Exception as e:
        logger.debug("Phoenix shutdown hook failed (non-critical): %s", e)
