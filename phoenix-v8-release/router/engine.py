"""
不死鸟 Phoenix V8 — 路由引擎

按任务类型智能选模型：
- 什么活配什么模型
- 不是“贵的备选、便宜的主力”
- 而是“合适的才是最好的”

路由决策流程：
1. 分析用户消息 → 识别任务类型
2. 查路由表 → 找对应模型
3. 检查熔断器 → 模型是否可用
4. 检查预算 → 能不能花这个钱
5. 返回最终选择
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class RouteDecision:
    """路由决策结果"""

    model: str                          # 选择的模型
    provider: str                       # 提供商
    task_type: str                      # 任务类型
    model_category: str                 # 模型类别
    reason: str                         # 决策原因
    is_fallback: bool = False           # 是否为降级选择
    estimated_cost_tier: str = "free"   # 成本等级: free/low/medium/high
    backup_model: Optional[str] = None  # 备选模型 (fallback model from config)
    fallback_model: Optional[str] = None # 应急模型 (emergency model from config)
    route_chain: Optional[list] = None   # 路由链: [primary, fallback, emergency]
    secondary_model: Optional[str] = None # 第二模型 (真神模式: Opus + GPT-5.5 双引擎)
    base_url: Optional[str] = None         # V8: ProviderResolver解析出的端点
    api_key_env: Optional[str] = None      # V8: 环境变量名（不保存真实Key）
    provider_binding: Optional[dict] = None # V8: 脱敏Provider绑定审计信息


class TaskClassifier:
    """
    任务类型分类器

    基于关键词+模式匹配，零成本，不调LLM。
    """

    # V5: deep/god/super_god 改为手动触发（/深度 /大神 /真神）
    # 不再通过关键词自动触发，避免"分析"、"设计"等常见词误触发确认框

    CODE_PATTERNS = [
        r"```",  # 代码块
        r"(?:写|写一个|帮我写|生成|创建|实现).{0,15}(?:代码|脚本|函数|程序|类|接口|API|爬虫|工具|插件|服务|算法|模块|组件|库|框架|系统)",
        r"(?:写|帮我写|生成|创建).{0,15}(?:python|javascript|typescript|rust|go|java|sql|hello.?world)",
        r"(?:fix|debug|修复|调试|找bug|报错|error|报了个错)",
        r"(?:重构|优化代码|代码审查|审查.{0,5}代码|review|code review)",
        r"(?:def |class |import |function |const |let |var )",
        r"(?:^|\s)(?:python|javascript|typescript|rust|go|java|sql)(?:\.[a-zA-Z_]|(?:\s+[a-zA-Z_./]))",
        r"(?:终端|terminal|shell|bash|命令行|pip install|npm install)",
    ]

    REASONING_PATTERNS = [
        r"(?:分析|思考|推理|为什么|原因|原理|根本|深层|本质)",
        r"(?:对比|比较|优劣|利弊|哪个好|选哪个)",
        r"(?:方案|策略|架构|设计|规划|计划)",
        r"(?:帮我决策|做决定|选择困难)",
        r"(?:总结|归纳|梳理|整理思路)",
        r"(?:写一篇|写文章|论文|报告|研究)",
    ]

    VISION_PATTERNS = [
        r"(?:看.{0,5}(?:图|照片|截图|图片|image|screenshot))",
        r"(?:这张图|图片里|截图里|这是什么)",
        r"(?:识别|OCR|读取图片|分析图片)",
    ]

    SIMPLE_PATTERNS = [
        r"^(?:你好|hi|hello|嗨|在吗|在不在).{0,5}$",
        r"^(?:好的|行|ok|OK|可以|没问题|收到|谢谢|感谢).{0,5}$",
        r"^(?:今天.{0,10}(?:天气|日期|星期))",
        r"^(?:现在.{0,5}(?:几点|时间))",
        r"^(?:我叫|记住|帮我记|别忘了|记一下).{0,20}$",
        r"^\s*\d+\s*[+\-*/]\s*\d+\s*(?:等于几|=\s*\?|是多少)?\s*[?？]?\s*$",
        r"^(?:帮我)?搜(?:一下|索)?.{0,30}$",
    ]

    SMALL_CODE_PATTERNS = [
        r"(?:hello\s*world|helloworld|你好世界)",
        r"(?:单个|小|简单|轻量|demo|示例|例子|片段|snippet)",
        r"(?:改一行|改个|补个|修个|加个|配置|变量|常量|一行|两行)",
        r"(?:入门|新手|初学|最简单|最基础).{0,10}(?:代码|例子|脚本)",
    ]

    LARGE_CODE_PATTERNS = [
        r"(?:重构|重写|整套|整个|系统|平台|多模块|跨服务|状态管理|迁移|全量)",
        r"(?:设计|搭建|构建|规划).{0,10}(?:架构|系统|平台|微服务|分布式|中台|后端|框架)",
        r"(?:微服务|分布式|高并发|高可用|集群).{0,10}(?:架构|设计|方案|系统)",
    ]
    LIGHT_REASONING_PATTERNS = [
        r"(?:简要|快速|轻度|大概|大致|简单判断|一句话)",
        r"(?:怎么选|哪个更好|值不值|合不合理)",
        r"^\s*\d+\s*[+\-*/]",
    ]

    def classify(self, message: str, has_image: bool = False) -> str:
        """V4: 分类任务类型（支持vision子类型）"""
        if has_image:
            return self._classify_vision_subtype(message)

        message_lower = message.lower().strip()

        for pattern in self.SIMPLE_PATTERNS:
            if re.search(pattern, message_lower, re.IGNORECASE):
                # 算术类归为reasoning_light
                if re.match(r"^\s*\d+\s*[+\-*/]", message_lower):
                    return "reasoning_light"
                return "chat"

        # V5: 去掉关键词触发的deep/god/super_god
        # 改为：只有显式手动命令触发
        if message_lower.startswith("/深度"):
            return "deep"
        if message_lower.startswith("/大神"):
            return "god"
        if message_lower.startswith("/真神"):
            return "super_god"

        # 优先检查LARGE_CODE - 架构设计类直接锁定code_large
        if any(re.search(p, message, re.IGNORECASE) for p in self.LARGE_CODE_PATTERNS):
            return "code_large"

        code_hit = any(re.search(pattern, message, re.IGNORECASE) for pattern in self.CODE_PATTERNS)
        if code_hit:
            if any(re.search(pattern, message, re.IGNORECASE) for pattern in self.SMALL_CODE_PATTERNS):
                return "code_small"
            return "code_medium"

        reasoning_hit = any(re.search(pattern, message, re.IGNORECASE) for pattern in self.REASONING_PATTERNS)
        if reasoning_hit:
            if any(re.search(pattern, message, re.IGNORECASE) for pattern in self.LIGHT_REASONING_PATTERNS):
                return "reasoning_light"
            return "reasoning"

        for pattern in self.VISION_PATTERNS:
            if re.search(pattern, message, re.IGNORECASE):
                return "vision"

        return "chat"

    def _classify_vision_subtype(self, message):
        """V4: vision子类型"""
        msg = message or ""
        if re.search(r"(?:截图|screenshot|截屏)", msg, re.I): return "vision_screenshot"
        if re.search(r"(?:视频|video|mp4|mov)", msg, re.I): return "vision_video"
        if re.search(r"(?:PDF|pdf|文档|document)", msg, re.I): return "vision_document"
        if re.search(r"(?:照片|photo|图片|image|jpg|png)", msg, re.I): return "vision_image"
        return "vision"


class RouterEngine:
    """
    路由引擎主类

    用法:
        router = RouterEngine(config)
        decision = router.route("帮我写个Python爬虫")
        # → RouteDecision(model="xiaomi/mimo-v2.5", task_type="code_small", ...)

        decision = router.route("今天天气怎么样")
        # → RouteDecision(model="xiaomi/mimo-v2.5", task_type="chat", ...)
    """

    def __init__(self, config, state_manager=None, circuit_manager=None, evolution_engine=None):
        """
        Args:
            config: PhoenixConfig 实例
            state_manager: AppStateManager 实例（可选，保留向后兼容）
            circuit_manager: CircuitBreakerManager 实例（可选，统一熔断器检查）
            evolution_engine: EvolutionEngine 实例（可选，基于历史数据优化路由）
        """
        self._config = config
        self._state_mgr = state_manager
        self._circuit_mgr = circuit_manager
        self._evolution = evolution_engine
        self._classifier = TaskClassifier()
        self._llm_classifier = None
        try:
            from router.llm_classifier import LLMClassifier
            self._llm_classifier = LLMClassifier()
        except Exception as e:
            logger.debug("[phoenix.router] LLM classifier init failed: %s", e)

    def _classify_with_fallback(self, message, has_image=False):
        """V4: LLM→正则降级链"""
        if self._llm_classifier and self._llm_classifier.available():
            r = self._llm_classifier.classify(message, has_image)
            if r and r.get("confidence", 0) >= 0.6:
                return r["task_type"]
        return self._classifier.classify(message, has_image)

    def route(self, message: str, has_image: bool = False, force_model: str = None) -> RouteDecision:
        """路由决策"""
        if force_model:
            return RouteDecision(
                model=force_model,
                provider="manual",
                task_type="manual",
                model_category="manual",
                reason="用户强制指定模型",
                backup_model=None,
                fallback_model=None,
                route_chain=[force_model],
            )

        task_type = self._classify_with_fallback(message, has_image)
        model_config = self._config.get_model_for_task(task_type)
        primary_model = model_config.get("primary", "")
        fallback_model = model_config.get("fallback")
        provider = model_config.get("provider", "nous")
        binding = None
        try:
            from core.provider_resolver import ProviderResolver
            raw_cfg = self._config.to_dict() if hasattr(self._config, "to_dict") else getattr(self._config, "_config", {})
            resolver = ProviderResolver(raw_cfg)
            binding = resolver.resolve_binding(primary_model, provider) if primary_model else None
            if binding:
                provider = binding.provider
        except Exception:
            binding = None

        # 进化反馈：如果有历史数据表明某模型在此任务上表现更佳，优先用它
        if self._evolution:
            try:
                evolved_best = self._evolution.get_best_model_for_task(task_type)
                if evolved_best and evolved_best != primary_model:
                    if not self._circuit_mgr or self._circuit_mgr.is_available(evolved_best):
                        return RouteDecision(
                            model=evolved_best,
                            provider=provider,
                            task_type=task_type,
                            model_category=model_config.get("_category", task_type),
                            reason=f"进化推荐：{evolved_best}在{task_type}上综合评分最高",
                            estimated_cost_tier=self._estimate_cost(evolved_best),
                            backup_model=primary_model,
                            fallback_model=fallback_model,
                            route_chain=[evolved_best, primary_model, fallback_model],
                        )
            except Exception as exc:
                _ = exc

        if self._circuit_mgr and not self._circuit_mgr.is_available(primary_model):
            if fallback_model and self._circuit_mgr.is_available(fallback_model):
                return RouteDecision(
                    model=fallback_model,
                    provider=provider,
                    task_type=task_type,
                    model_category=model_config.get("_category", task_type),
                    reason=f"主模型{primary_model}已熔断，降级到备选",
                    is_fallback=True,
                    estimated_cost_tier=self._estimate_cost(fallback_model),
                    backup_model=fallback_model,
                    fallback_model=model_config.get("emergency"),
                    route_chain=[m for m in [primary_model, fallback_model, model_config.get("emergency")] if m],
                )

            emergency = model_config.get("emergency", "google/gemini-2.5-flash")
            route_chain = [m for m in [primary_model, fallback_model, emergency] if m]
            return RouteDecision(
                model=emergency,
                provider="nous",
                task_type=task_type,
                model_category="emergency",
                reason="主备模型都已熔断，紧急兜底",
                is_fallback=True,
                estimated_cost_tier="free",
                backup_model=fallback_model,
                fallback_model=emergency,
                route_chain=route_chain,
            )

        # 读取secondary模型（真神模式: Opus + GPT-5.5 双引擎）
        secondary_model = model_config.get("secondary")

        return RouteDecision(
            model=primary_model,
            provider=provider,
            task_type=task_type,
            model_category=task_type,
            reason=f"任务类型={task_type}，路由到{primary_model}",
            estimated_cost_tier=self._estimate_cost(primary_model),
            backup_model=fallback_model,
            fallback_model=model_config.get("emergency"),
            route_chain=[m for m in [primary_model, fallback_model, model_config.get("emergency")] if m],
            secondary_model=secondary_model,
            base_url=binding.base_url if binding else model_config.get("base_url"),
            api_key_env=binding.api_key_env if binding else model_config.get("api_key_env"),
            provider_binding=binding.as_dict(include_secret=False) if binding else None,
        )

    def get_available_models(self) -> dict:
        """获取所有可用模型（排除熔断的）"""
        result = {}
        models = self._config.get("router.models", {})
        for category, model_cfg in models.items():
            primary = model_cfg.get("primary", "")
            fallback = model_cfg.get("fallback")
            available = []
            if primary and (not self._circuit_mgr or self._circuit_mgr.is_available(primary)):
                available.append(primary)
            if fallback and (not self._circuit_mgr or self._circuit_mgr.is_available(fallback)):
                available.append(fallback)
            result[category] = available
        return result

    def _estimate_cost(self, model: str) -> str:
        """估算模型成本等级 — 优先从config读取，失败时回退到默认映射"""
        # 1. 优先从config读取
        try:
            cost_map = self._config.get("router.cost_map", {}) or {}
            if model in cost_map:
                return cost_map[model]
        except Exception as exc:
            _ = exc

        # 2. 回退到内置映射
        DEFAULT_COST_MAP = {
            "xiaomi/mimo-v2-flash": "free",
            "xiaomi/mimo-v2.5": "low",
            "xiaomi/mimo-v2-omni": "low",
            "anthropic/claude-haiku-4.5": "low",
            "anthropic/claude-sonnet-4.6": "medium",
            "anthropic/claude-opus-4.7": "high",
            "openai/gpt-5.4-mini": "low",
            "openai/gpt-5.4": "medium",
            "openai/gpt-5.4-image-2": "medium",
            "openai/gpt-5.5": "high",
            "google/gemini-2.5-flash": "low",
            "google/gemini-2.5-pro": "medium",
            "google/gemini-3-flash-preview": "low",
        }
        result = DEFAULT_COST_MAP.get(model)
        if result is None:
            # 3. 根据token_tracker.PRICING动态推断
            try:
                from phoenix.security.token_tracker import TokenTracker
                for key, pricing in TokenTracker.PRICING.items():
                    if key in model:
                        avg = (pricing["input"] + pricing["output"]) / 2
                        if avg < 0.0005:
                            return "free"
                        elif avg < 0.002:
                            return "low"
                        elif avg < 0.01:
                            return "medium"
                        else:
                            return "high"
            except Exception as exc:
                _ = exc
            import logging
            logging.getLogger("phoenix.router.engine").warning(
                "COST未命中模型: %s, 返回unknown", model
            )
            return "unknown"
        return result
