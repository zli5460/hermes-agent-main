"""
不死鸟 Phoenix V5.1.3 — 配置管理

所有不死鸟的配置集中管理，支持：
- 默认配置
- 用户配置覆盖
- 热更新
- 开源友好（不硬编码任何API Key）
"""

import os
import json
from pathlib import Path
from typing import Optional


# ========== 默认配置 ==========

DEFAULT_CONFIG = {
    "version": "5.1.3",
    "name": "不死鸟 Phoenix",

    # 记忆系统
    "memory": {
        "auto_extract": True,
        "extract_rules": True,
        "extract_llm": False,
        "session_memory_max": 50,
        "cron_sync_interval": 1800,
        "recover_on_startup": True,
    },

    # 路由系统
    "router": {
        "enabled": True,
        "strategy": "task_type",
        "models": {
            # 四供应商矩阵：xiaomi / anthropic / openai / google
            # 路由入口：只负责分类，要快
            "routing": {
                "primary": "xiaomi/mimo-v2-flash",
                "fallback": "openai/gpt-5.4-mini",
                "emergency": "google/gemini-2.5-flash",
                "provider": "nous-api",
            },
            # 日常对话
            "chat": {
                "primary": "xiaomi/mimo-v2.5",
                "fallback": "openai/gpt-5.4-mini",
                "emergency": "google/gemini-2.5-flash",
                "provider": "nous-api",
            },
            # 小代码：改配置、写脚本
            "code_small": {
                "primary": "xiaomi/mimo-v2.5",
                "fallback": "openai/gpt-5.4-mini",
                "emergency": "anthropic/claude-haiku-4.5",
                "provider": "nous-api",
            },
            # 中代码：写函数、写模块
            "code_medium": {
                "primary": "anthropic/claude-sonnet-4.6",
                "fallback": "openai/gpt-5.4",
                "emergency": "xiaomi/mimo-v2.5",
                "provider": "nous-api",
            },
            # 大代码：架构、重构、系统
            "code_large": {
                "primary": "anthropic/claude-opus-4.7",
                "fallback": "anthropic/claude-sonnet-4.6",
                "emergency": "openai/gpt-5.5",
                "provider": "nous-api",
            },
            # 轻推理：快速判断
            "reasoning_light": {
                "primary": "xiaomi/mimo-v2.5",
                "fallback": "openai/gpt-5.4-mini",
                "emergency": "google/gemini-2.5-flash",
                "provider": "nous-api",
            },
            # 深度推理：分析、决策
            "reasoning": {
                "primary": "anthropic/claude-opus-4.7",
                "fallback": "openai/gpt-5.5",
                "emergency": "google/gemini-2.5-pro",
                "provider": "nous-api",
            },
            # 子任务：委派给子agent
            "subtask": {
                "primary": "openai/gpt-5.4-mini",
                "fallback": "xiaomi/mimo-v2-flash",
                "emergency": "anthropic/claude-haiku-4.5",
                "provider": "nous-api",
            },
            # 视觉：图片、截图
            "vision": {
                "primary": "xiaomi/mimo-v2-omni",
                "fallback": "google/gemini-3-flash-preview",
                "emergency": "anthropic/claude-sonnet-4.6",
                "provider": "nous-api",
            },
        },
        "task_type_mapping": {
            "chat": "chat",
            "tool_call": "chat",
            "memory_op": "chat",
            "code": "code_medium",
            "code_small": "code_small",
            "code_medium": "code_medium",
            "code_large": "code_large",
            "reasoning": "reasoning",
            "reasoning_light": "reasoning_light",
            "delegation": "subtask",
            "self_heal": "reasoning",
            "evolution": "reasoning",
            "routing": "routing",
            "vision": "vision",
            "compression": "chat",
        },
    },

    # 执行系统
    "executor": {
        "micro_compact": {
            "enabled": True,
            "max_tool_result_lines": 5,
            "compress_threshold": 500,
        },
        "deep_compact": {
            "enabled": True,
            "context_threshold_tokens": 4000,
            "keep_last_n_messages": 3,
            "summary_max_tokens": 500,
        },
        "budget": {
            "monthly_limit_usd": 50.0,
            "daily_limit_usd": 5.0,
            "warning_threshold": 0.8,
        },
        "circuit_breaker": {
            "failure_threshold": 5,
            "success_threshold": 3,
            "cooldown_seconds": 60,
        },
    },

    # 安全系统
    "security": {
        "api_key_block": True,
        "daily_message_limit": 20,
        "master_uid": "",
    },

    # 自我净化 + 进化
    "self_heal": {
        "antibody_enabled": True,
        "auto_fallback": True,
        "evolution_enabled": True,
        "max_antibodies": 100,
    },

    # 技能系统（V2：按需加载，不预载全部）
    "skills": {
        "enabled": True,
        "directory": "~/.hermes/skills",
        "lazy_load": True,
    },

    # 垃圾回收
    "gc": {
        "event_history_max": 200,
        "task_ttl_seconds": 7 * 24 * 3600,
        "antibody_ttl_days": 30,
        "config_prune_empty": True,
    },

    # 插件系统（V2扩展）
    "plugins": {
        "enabled": False,
        "directory": "~/.hermes/phoenix/plugins",
    },
}


class PhoenixConfig:
    """
    不死鸟配置管理器

    用法:
        config = PhoenixConfig()
        router_cfg = config.get("router")
        config.set("executor.budget.monthly_limit_usd", 100.0)
        config.save()
    """

    def __init__(self, config_path: Optional[str] = None):
        self._config_path = Path(config_path) if config_path else self._default_path()
        self._config = json.loads(json.dumps(DEFAULT_CONFIG))
        self._load()

    def _default_path(self) -> Path:
        """默认配置路径"""
        hermes_home = os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))
        return Path(hermes_home) / "phoenix" / "config.json"

    def get(self, key: str, default=None):
        """
        获取配置值，支持点号路径

        config.get("router.models.chat.primary")
        config.get("executor.budget.monthly_limit_usd")
        """
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def set(self, key: str, value):
        """
        设置配置值，支持点号路径

        config.set("router.models.chat.primary", "new-model")
        """
        keys = key.split(".")
        config = self._config
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value

    def get_all(self) -> dict:
        """获取全部配置"""
        return json.loads(json.dumps(self._config))

    def save(self):
        """保存配置到磁盘"""
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            self._config_path.write_text(
                json.dumps(self._config, indent=2, ensure_ascii=False)
            )
        except Exception as e:
            print(f"[Phoenix] 配置保存失败: {e}")

    def _load(self):
        """从磁盘加载用户配置（覆盖默认值）"""
        if not self._config_path.exists():
            return
        try:
            user_config = json.loads(self._config_path.read_text())
            self._deep_merge(self._config, user_config)
        except Exception as e:
            print(f"[Phoenix] 配置加载失败: {e}")

    def _deep_merge(self, base: dict, override: dict):
        """深度合并配置"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def get_model_for_task(self, task_type: str) -> dict:
        """
        根据任务类型获取模型配置。

        V5.1.3 统一配置源：优先读取 phoenix_open.model_tiers。
        router.task_modes / router.models 仅作为旧版本兼容回退。

        返回: {
            "primary": "model-name",
            "fallback": "fallback-model",
            "provider": "provider-name",
            "base_url": "https://...",
            "api_key_env": "ENV_NAME",
            "requires_approval": bool,
            "auto_execute": bool,
        }
        """
        # 1. V5.1.3 权威配置源：phoenix_open.model_tiers
        open_tiers = self.get("phoenix_open.model_tiers", {})
        task_to_tier = {
            "chat": "daily",
            "translation": "daily",
            "search": "daily",
            "vision": "daily",
            "vision_image": "daily",
            "vision_screenshot": "daily",
            "vision_video": "daily",
            "vision_document": "daily",
            "code_small": "medium",
            "code_medium": "medium",
            "content": "medium",
            "deep": "deep",
            "god": "god",
            "super_god": "super_god",
        }
        tier_key = task_to_tier.get(task_type, task_type if task_type in ("daily", "medium", "deep", "god", "super_god") else "daily")
        tier = open_tiers.get(tier_key, {}) if isinstance(open_tiers, dict) else {}
        if isinstance(tier, dict) and (tier.get("model") or tier.get("model_a")):
            fallback = tier.get("fallback")
            fallback_model = fallback.get("model") if isinstance(fallback, dict) else fallback
            result = {
                "primary": tier.get("model") or tier.get("model_a"),
                "fallback": fallback_model or self.get("phoenix_open.fallback.model"),
                "provider": tier.get("provider") or tier.get("provider_a") or "custom",
                "base_url": tier.get("base_url") or tier.get("base_url_a"),
                "api_key_env": tier.get("api_key_env") or tier.get("api_key_env_a"),
                "is_local": tier.get("is_local", False),
                "auto_execute": tier.get("auto_execute", False),
                "requires_approval": tier.get("requires_approval", tier_key in ("deep", "god", "super_god")),
                "tier": tier_key,
            }
            if tier_key == "super_god":
                result["secondary"] = tier.get("model_b")
                result["secondary_provider"] = tier.get("provider_b")
                result["secondary_base_url"] = tier.get("base_url_b")
                result["secondary_api_key_env"] = tier.get("api_key_env_b")
            return result

        # 2. 兼容旧配置：router.task_modes
        task_modes = self.get("router.task_modes", {})
        for mode_name, mode_cfg in task_modes.items():
            models = mode_cfg.get("models", {})
            if isinstance(models, dict):
                if task_type == mode_name and "primary" in models:
                    result = {
                        "primary": models["primary"],
                        "fallback": models.get("fallback"),
                        "provider": models.get("provider", "nous"),
                        "auto_execute": mode_cfg.get("auto_execute", False),
                        "requires_approval": mode_cfg.get("requires_approval", mode_name in ("deep", "god", "super_god")),
                        "tier": mode_name,
                    }
                    if "secondary" in models:
                        result["secondary"] = models["secondary"]
                    return result
                if task_type in models and isinstance(models[task_type], dict):
                    return models[task_type]

        # 3. 最终兼容旧路径：router.task_type_mapping + router.models
        model_category = self.get(f"router.task_type_mapping.{task_type}", "chat")
        return self.get(
            f"router.models.{model_category}",
            {
                "primary": "xiaomi/mimo-v2.5",
                "fallback": None,
                "provider": "nous",
            },
        )

    def validate(self) -> list[str]:
        """验证配置完整性"""
        errors = []

        if not self.get("router.models"):
            errors.append("路由模型配置为空")

        budget = self.get("executor.budget.monthly_limit_usd")
        if budget and budget <= 0:
            errors.append("月预算必须大于0")

        return errors
