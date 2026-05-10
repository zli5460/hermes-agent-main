import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from phoenix import Phoenix
from core.config import PhoenixConfig
from router.engine import RouterEngine


class PhoenixV2SmokeTest(unittest.TestCase):
    def test_router_matrix_matches_locked_design(self):
        """验证四供应商路由矩阵：xiaomi/anthropic/openai/google"""
        config = PhoenixConfig()
        # routing: 分类器，要快
        self.assertEqual(config.get("router.models.routing.primary"), "xiaomi/mimo-v2-flash")
        self.assertEqual(config.get("router.models.routing.fallback"), "xiaomi/mimo-v2.5")
        self.assertEqual(config.get("router.models.routing.emergency"), "xiaomi/mimo-v2.5")
        # chat: 日常对话
        self.assertEqual(config.get("router.models.chat.primary"), "xiaomi/mimo-v2.5")
        self.assertEqual(config.get("router.models.chat.fallback"), "xiaomi/mimo-v2.5")
        # code_small: 小代码
        self.assertEqual(config.get("router.models.code_small.primary"), "xiaomi/mimo-v2.5-pro")
        # code_medium: 中代码
        self.assertEqual(config.get("router.models.code_medium.primary"), "xiaomi/mimo-v2.5")
        # code_large: 大代码
        self.assertEqual(config.get("router.models.code_large.primary"), "anthropic/claude-sonnet-4.6")
        # reasoning_light: 轻推理
        self.assertEqual(config.get("router.models.reasoning_light.primary"), "xiaomi/mimo-v2.5")
        # reasoning: 深度推理
        self.assertEqual(config.get("router.models.reasoning.primary"), "anthropic/claude-opus-4.7")
        # subtask: 子任务
        self.assertEqual(config.get("router.models.subtask.primary"), "xiaomi/mimo-v2.5")
        # vision: 视觉
        self.assertEqual(config.get("router.models.vision.primary"), "xiaomi/mimo-v2-omni")
        # task_type_mapping
        self.assertEqual(config.get("router.task_type_mapping.code"), "code_medium")
        self.assertEqual(config.get("router.task_type_mapping.code_small"), "code_small")
        self.assertEqual(config.get("router.task_type_mapping.code_medium"), "code_medium")
        self.assertEqual(config.get("router.task_type_mapping.code_large"), "code_large")
        self.assertEqual(config.get("router.task_type_mapping.reasoning_light"), "reasoning_light")
        self.assertEqual(config.get("router.task_type_mapping.delegation"), "subtask")
        self.assertEqual(config.get("router.task_type_mapping.vision"), "vision")

    def test_404_response_bans_bad_target(self):
        phoenix = Phoenix()
        result = phoenix.check_and_handle_error(
            "[API错误 404]",
            context={"model": "bad/model", "provider": "nous", "task_type": "chat"},
        )
        self.assertTrue(result["handled"])
        self.assertEqual(result["action"], "ban_bad_target_then_fallback")
        self.assertEqual(phoenix.state.get_state().circuit_breakers["bad/model"].state, "open")

    def test_report_model_result_trips_404_target(self):
        phoenix = Phoenix()
        phoenix.report_model_result(
            model="bad/model",
            task_type="chat",
            latency=0.0,
            cost=0.0,
            success=False,
            error_message="404 Not Found",
        )
        self.assertEqual(phoenix.state.get_state().circuit_breakers["bad/model"].state, "open")

    def test_router_routes_core_intents(self):
        router = RouterEngine(PhoenixConfig())
        self.assertEqual(router.route("你好").task_type, "chat")
        self.assertEqual(router.route("帮我重构整个python爬虫系统").task_type, "code_large")
        self.assertEqual(router.route("看这张图").task_type, "vision")
        self.assertEqual(router.route("", has_image=True).task_type, "vision")

    def test_phoenix_initializes_and_skill_loader_picks_phoenix_skills(self):
        phoenix = Phoenix()
        prompt = phoenix.skill_loader.to_prompt("继续把整个V2跑完整了", "reasoning")
        self.assertIn("phoenix-v2-architecture", prompt)
        self.assertIn("phoenix-v2", prompt)  # 至少命中一个phoenix技能

    def test_no_deepseek_or_qwen_in_production_sources(self):
        """确保生产代码中没有deepseek或qwen残留"""
        py_files = [p for p in ROOT.rglob("*.py") if "tests" not in p.parts]
        hits = []
        for path in py_files:
            text = path.read_text(encoding="utf-8", errors="ignore")
            text_lower = text.lower()
            if "deepseek" in text_lower:
                hits.append(f"{path}:deepseek")
            if "qwen" in text_lower and "qwen" not in path.name:
                hits.append(f"{path}:qwen")
        self.assertEqual(hits, [], f" banned model remnants found: {hits}")

    def test_four_suppliers_only(self):
        """验证所有路由模型都属于四供应商"""
        config = PhoenixConfig()
        allowed_prefixes = ("xiaomi/", "anthropic/", "openai/", "google/")
        models = config.get("router.models", {})
        for category, model_cfg in models.items():
            for key in ("primary", "fallback", "emergency"):
                model = model_cfg.get(key, "")
                if model:
                    self.assertTrue(
                        model.startswith(allowed_prefixes),
                        f"路由矩阵中有非法模型: {category}.{key}={model}",
                    )


if __name__ == "__main__":
    unittest.main()
