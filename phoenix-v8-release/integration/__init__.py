"""Phoenix Gateway 集成层"""
from .gateway_api import phoenix_gateway, PhoenixGatewayAPI
from .routing_hook import (
    on_turn_route,
    on_model_result,
    on_message_process,
    on_startup,
    on_shutdown,
)

# Hermes hook 注册清单（gateway侧扫描用）
HERMES_HOOKS = {
    "turn_route": on_turn_route,
    "model_result": on_model_result,
    "message_process": on_message_process,
    "startup": on_startup,
    "shutdown": on_shutdown,
}

__all__ = [
    "phoenix_gateway", "PhoenixGatewayAPI", "HERMES_HOOKS",
    "on_turn_route", "on_model_result", "on_message_process",
    "on_startup", "on_shutdown",
]
