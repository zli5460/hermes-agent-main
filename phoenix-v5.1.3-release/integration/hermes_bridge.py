"""
不死鸟 Phoenix V5.1 — Hermes集成桥接（完整版）

一句话进去 → 全链路自动跑完 → 结果出来
"""

import sys
import time
import json
from pathlib import Path

# 确保 phoenix 包的父目录在 sys.path 中（供 `import phoenix.xxx` 使用）
PHOENIX_PKG_DIR = Path(__file__).resolve().parent.parent      # .../phoenix
PHOENIX_PARENT = PHOENIX_PKG_DIR.parent                       # phoenix 的父目录
for _p in (str(PHOENIX_PARENT), str(PHOENIX_PKG_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# 统一使用包路径导入，避免模块重复加载
from phoenix.phoenix import Phoenix
from phoenix.executor.pipeline import AutoPipeline


class HermesPhoenixBridge:
    """
    Hermes-Phoenix 完整桥接器

    核心方法：
    - chat(message) → 一句话进去，全链路自动跑完
    - get_health() → 系统健康检查
    - get_stats() → 完整统计
    """

    def __init__(self):
        self.phoenix = Phoenix()
        self.pipeline = AutoPipeline(self.phoenix)
        self._call_count = 0

    def chat(self, message: str, has_image: bool = False,
             model_callback=None):
        """
        核心接口：一句话进去，全链路自动跑完

        Args:
            message: 用户消息
            has_image: 是否包含图片
            model_callback: 模型调用回调（可选，不传则用模拟）

        Returns:
            PipelineResult
        """
        self._call_count += 1
        result = self.pipeline.run(message, has_image, model_callback)

        # 自动提取记忆（跟Gateway同逻辑）
        try:
            from phoenix.integration.memory_auto import phoenix_memory
            phoenix_memory.on_message(
                user_message=message,
                ai_response=result.response[:200] if hasattr(result, 'response') else "",
                model=result.model_used if hasattr(result, 'model_used') else "",
                task_type=result.task_type if hasattr(result, 'task_type') else "",
            )
        except Exception as exc:
            _ = exc  # 记忆提取失败不影响主流程

        # 每10次交互触发一次进化
        if self._call_count % 10 == 0:
            self.phoenix.evolve()

        return result

    def on_session_end(self):
        """会话结束"""
        events = self.phoenix.evolve()
        persistent = self.phoenix.session_memory.extract_persistent()
        return {
            "evolution_events": len(events),
            "persistent_memories": persistent,
        }

    def get_health(self) -> dict:
        """健康检查"""
        return self.phoenix.health_check()

    def get_stats(self) -> dict:
        """完整统计"""
        return {
            "health": self.phoenix.health_check(),
            "evolution": self.phoenix.evolution_report(),
            "pipeline_stats": {
                "total_calls": self._call_count,
            },
        }


def test():
    """完整自动化测试"""
    print("🦅 不死鸟 Phoenix V5.1 — 全链路自动化测试\n")

    bridge = HermesPhoenixBridge()

    test_cases = [
        "你好",
        "帮我写个Python爬虫，抓取知乎热榜",
        "分析一下为什么我的代码报错 ConnectionRefusedError",
        "记住：以后所有项目代码都放在 ~/Projects 目录下",
        "不对，应该是 ~/Developer 目录",
    ]

    for i, msg in enumerate(test_cases, 1):
        print(f"--- 测试{i}: {msg[:40]} ---")
        result = bridge.chat(msg)
        print(f"  模型: {result.model_used}")
        print(f"  类型: {result.task_type}")
        print(f"  成功: {result.success}")
        print(f"  耗时: {result.latency:.2f}s")
        print(f"  步骤:")
        for step in result.steps:
            print(f"    {step}")
        print()

    # 健康检查
    print("=== 系统健康 ===")
    health = bridge.get_health()
    print(f"  模式: {health['system']['mode']}")
    print(f"  抗体: {health['antibodies']['total']}个 (活跃{health['antibodies']['active']})")
    print(f"  记忆: {health['memory']['extraction']['total']}条提取")
    print(f"  会话: {health['memory']['session']['total']}条")

    print("\n✅ 全链路自动化测试完成！")


if __name__ == "__main__":
    test()
