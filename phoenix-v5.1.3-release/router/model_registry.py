"""
Phoenix V5.1 模型能力注册表（ModelRegistry）
统一的模型元数据，所有路由和子agent决策的基础
"""

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class ModelInfo:
    """模型元数据"""
    model_id: str
    provider: str
    cost_tier: str  # free/low/medium/high
    latency_ms: int  # 预估延迟
    context_window: int  # 上下文窗口大小
    strengths: list  # 能力标签
    max_output_tokens: int = 4096


# 模型注册表（单一事实源）
MODEL_REGISTRY: Dict[str, ModelInfo] = {
    # Xiaomi
    "xiaomi/mimo-v2.5": ModelInfo(
        model_id="xiaomi/mimo-v2.5",
        provider="nous-api",
        cost_tier="low",
        latency_ms=500,
        context_window=32000,
        strengths=["chat", "simple_code", "chinese", "reasoning_light"],
    ),
    "xiaomi/mimo-v2-omni": ModelInfo(
        model_id="xiaomi/mimo-v2-omni",
        provider="nous-api",
        cost_tier="low",
        latency_ms=800,
        context_window=32000,
        strengths=["vision", "multimodal", "image_understanding"],
    ),
    
    # Anthropic
    "anthropic/claude-sonnet-4.6": ModelInfo(
        model_id="anthropic/claude-sonnet-4.6",
        provider="nous-api",
        cost_tier="medium",
        latency_ms=2000,
        context_window=200000,
        strengths=["code", "analysis", "writing", "reasoning"],
        max_output_tokens=8192,
    ),
    "anthropic/claude-opus-4.7": ModelInfo(
        model_id="anthropic/claude-opus-4.7",
        provider="nous-api",
        cost_tier="high",
        latency_ms=5000,
        context_window=200000,
        strengths=["deep_reasoning", "architecture", "complex_code", "research"],
        max_output_tokens=16384,
    ),
    
    # OpenAI (for image generation)
    "openai/gpt-image-2": ModelInfo(
        model_id="openai/gpt-image-2",
        provider="openai",
        cost_tier="medium",
        latency_ms=15000,
        context_window=0,
        strengths=["image_generation"],
    ),
}


def get_model_info(model_id: str) -> Optional[ModelInfo]:
    """获取模型信息"""
    return MODEL_REGISTRY.get(model_id)


def get_models_by_strength(strength: str) -> list:
    """按能力标签筛选模型"""
    return [
        m for m in MODEL_REGISTRY.values()
        if strength in m.strengths
    ]


def get_cheapest_model(strength: str = None) -> Optional[ModelInfo]:
    """获取最便宜的模型"""
    cost_order = {"free": 0, "low": 1, "medium": 2, "high": 3}
    models = get_models_by_strength(strength) if strength else list(MODEL_REGISTRY.values())
    return min(models, key=lambda m: cost_order.get(m.cost_tier, 99)) if models else None


def get_fastest_model(strength: str = None) -> Optional[ModelInfo]:
    """获取最快的模型"""
    models = get_models_by_strength(strength) if strength else list(MODEL_REGISTRY.values())
    return min(models, key=lambda m: m.latency_ms) if models else None
