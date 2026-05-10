"""
不死鸟 Phoenix V5.1 — Hermes消息钩子

轻量级集成，不改hermes-agent核心代码。
在消息处理的各个节点调用对应hook方法。

集成方式（三选一）：

方式1：在hermes-agent的run_agent.py中import调用
方式2：通过CLI slash命令调用 /phoenix
方式3：作为独立进程，通过文件IPC通信
"""

import sys
import json
import time
from pathlib import Path

PHOENIX_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PHOENIX_DIR))

from phoenix import Phoenix


class PhoenixHook:
    """
    不死鸟消息钩子

    设计原则：
    - 读操作不影响hermes正常运行
    - 写操作都是异步/非阻塞的
    - 出错不影响hermes主流程
    - 可以随时关闭/开启
    """

    def __init__(self):
        self.enabled = True
        self._phoenix = None

    @property
    def phoenix(self):
        """延迟加载，只在第一次调用时初始化"""
        if self._phoenix is None:
            self._phoenix = Phoenix()
        return self._phoenix

    def on_user_message(self, message: str) -> dict:
        """
        用户发消息时调用

        返回要注入到系统prompt的额外上下文
        安全：出错返回空dict，不影响正常流程
        """
        if not self.enabled:
            return {}

        try:
            result = {}

            # 自动提取记忆
            memories = self.phoenix.extract_memory(message)
            if memories:
                result["phoenix_memories"] = [m.content[:100] for m in memories[:3]]

            # 路由建议
            decision = self.phoenix.route(message)
            result["phoenix_suggested_model"] = decision.model
            result["phoenix_task_type"] = decision.task_type

            # 会话上下文
            ctx = self.phoenix.get_context_for_prompt()
            if ctx:
                result["phoenix_context"] = ctx

            return result
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[PhoenixHook] on_user_message 异常: {e}", file=__import__('sys').stderr)
            return {}

    def on_tool_result(self, tool_name: str, result: str) -> str:
        """
        工具返回结果时调用

        返回压缩后的结果
        安全：出错返回原始结果
        """
        if not self.enabled:
            return result

        try:
            return self.phoenix.compress_tool_result(result, tool_name)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[PhoenixHook] on_tool_result 异常: {e}", file=__import__('sys').stderr)
            return result

    def on_model_response(self, model: str, task_type: str,
                          latency: float, cost: float, success: bool,
                          error_message: str = ""):
        """
        模型调用完成时调用

        安全：出错静默
        """
        if not self.enabled:
            return

        try:
            self.phoenix.report_model_result(
                model,
                task_type,
                latency,
                cost,
                success,
                error_message=error_message,
                error_status_code=404 if "404" in error_message else None,
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[PhoenixHook] on_model_response 异常: {e}", file=__import__('sys').stderr)
            return

    def on_error(self, error_message: str) -> dict:
        """
        发生错误时调用

        返回处理建议
        安全：出错返回空dict
        """
        if not self.enabled:
            return {}

        try:
            return self.phoenix.check_and_handle_error(error_message)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[PhoenixHook] on_error 异常: {e}", file=__import__('sys').stderr)
            return {}

    def on_session_end(self):
        """
        会话结束时调用

        触发进化 + 提取持久化记忆 + 写日记
        安全：出错静默
        """
        if not self.enabled:
            return

        try:
            self.phoenix.evolve()
            persistent = self.phoenix.session_memory.extract_persistent()
            summary = f"本次会话结束，持久化候选 {len(persistent)} 条，已完成进化检查。"
            self.phoenix.diary.append_session_summary(summary=summary, title="会话结束")
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[PhoenixHook] on_session_end 异常: {e}", file=__import__('sys').stderr)

    def get_status(self) -> str:
        """获取不死鸟状态（供/phoenix命令使用）"""
        if not self.enabled:
            return "🔴 不死鸟已关闭"

        try:
            health = self.phoenix.health_check()
            lines = [
                "🦅 不死鸟状态",
                f"  模式: {health['system']['mode']}",
                f"  预算: {health['system']['budget_used']}",
                f"  抗体: {health['antibodies']['active']}/{health['antibodies']['total']}",
                f"  记忆: {health['memory']['extraction']['total']}条",
            ]
            return "\n".join(lines)
        except Exception as e:
            return f"❌ 不死鸟状态异常: {e}"

    def enable(self):
        """开启不死鸟"""
        self.enabled = True

    def disable(self):
        """关闭不死鸟"""
        self.enabled = False


# 全局单例（模块级）
_hook = PhoenixHook()


def get_hook() -> PhoenixHook:
    """获取不死鸟钩子单例

    ⚠️ 已废弃：新集成请直接使用 phoenix.integration.routing_hook 的函数式接口：
        from phoenix.integration.routing_hook import (
            on_message_process, on_turn_route, on_model_result,
            on_startup, on_shutdown,
        )
    本类接口仅为向后兼容保留。
    """
    import warnings
    warnings.warn(
        "PhoenixHook class is deprecated; use phoenix.integration.routing_hook functions",
        DeprecationWarning, stacklevel=2,
    )
    return _hook
