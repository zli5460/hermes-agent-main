"""
Phoenix V5.1.3 — ProviderResolver

模型 → Provider → base_url → api_key_env/api_key 绑定解析器。
目标：防止多 Provider / 本地模型混用时发生 Key 串位、端点串位。

安全约束：
- 默认不返回/打印真实 API Key。
- 云端 Provider 推荐使用 api_key_env，只保存环境变量名。
- 本地 OpenAI 兼容端点允许使用占位 api_key（lm-studio/ollama/vllm）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional, Dict, Tuple, List, Any


@dataclass(frozen=True)
class ProviderBinding:
    """单个模型的 Provider 绑定结果。"""
    model: str
    provider: str
    base_url: str
    api_key_env: Optional[str] = None
    api_key: Optional[str] = None
    is_local: bool = False
    source: str = "unknown"
    slot: str = "primary"
    tier: str = ""
    api_mode: str = "chat_completions"
    route_chain: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def redacted_key(self) -> str:
        if self.api_key_env:
            return f"env:{self.api_key_env}"
        if self.api_key:
            return "[REDACTED]"
        return ""

    def as_dict(self, include_secret: bool = False) -> Dict[str, Any]:
        data = {
            "model": self.model,
            "provider": self.provider,
            "base_url": self.base_url,
            "api_key_env": self.api_key_env,
            "api_key": self.api_key if include_secret else self.redacted_key,
            "is_local": self.is_local,
            "source": self.source,
            "slot": self.slot,
            "tier": self.tier,
            "api_mode": self.api_mode,
            "route_chain": self.route_chain,
        }
        return data


class ProviderResolver:
    """
    V5.1 统一 Provider 解析器。

    解析优先级：
    1. 显式 provider + model：只允许命中该 provider。
    2. phoenix_open.model_tiers：五档槽位直接绑定 provider/base_url/api_key_env。
    3. phoenix_open.providers：provider.models 中声明的模型。
    4. 模型名前缀 provider/model：按前缀查 provider。
    5. 不做“第一个云端 Provider”兜底，避免串 Key；解析失败直接报错。
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._config = config or {}
        open_cfg = self._config.get("phoenix_open", {}) or {}
        self._providers = open_cfg.get("providers", {}) or {}
        self._tiers = open_cfg.get("model_tiers", {}) or {}
        self._fallback = open_cfg.get("fallback", {}) or {}
        self._cache: Dict[Tuple[Optional[str], str], ProviderBinding] = {}
        self._build_mapping()

    @staticmethod
    def _normalize_model(model: str) -> str:
        return (model or "").strip()

    @staticmethod
    def _short_model(model: str) -> str:
        model = (model or "").strip()
        return model.split("/", 1)[1] if "/" in model else model

    @staticmethod
    def _provider_from_model(model: str) -> Optional[str]:
        model = (model or "").strip()
        if "/" in model:
            return model.split("/", 1)[0]
        return None

    def _provider_conf(self, provider: Optional[str]) -> Dict[str, Any]:
        return self._providers.get(provider or "", {}) or {}

    def _make_binding(
        self,
        *,
        model: str,
        provider: Optional[str],
        base_url: Optional[str] = None,
        api_key_env: Optional[str] = None,
        api_key: Optional[str] = None,
        is_local: Optional[bool] = None,
        source: str,
        slot: str = "primary",
        tier: str = "",
        route_chain: Optional[List[Dict[str, Any]]] = None,
    ) -> ProviderBinding:
        model = self._normalize_model(model)
        provider = provider or self._provider_from_model(model)
        p_conf = self._provider_conf(provider)

        final_base_url = base_url or p_conf.get("base_url") or ""
        final_api_key_env = api_key_env or p_conf.get("api_key_env")
        final_api_key = api_key if api_key is not None else p_conf.get("api_key")
        final_is_local = bool(is_local if is_local is not None else p_conf.get("is_local", False))

        # 兼容旧写法：api_key="$ENV_NAME"
        if isinstance(final_api_key, str) and final_api_key.startswith("$") and not final_api_key_env:
            final_api_key_env = final_api_key[1:]
            final_api_key = None

        # 本地 OpenAI 兼容端点允许占位 key。
        if final_is_local and not final_api_key and not final_api_key_env:
            final_api_key = provider or "local"

        if not provider:
            raise ValueError(f"模型 '{model}' 缺少 provider，无法安全解析")
        if not final_base_url:
            raise ValueError(f"模型 '{model}' 的 provider '{provider}' 缺少 base_url")
        if not final_is_local and not final_api_key_env and not final_api_key:
            raise ValueError(f"模型 '{model}' 的 provider '{provider}' 缺少 api_key_env/api_key")

        return ProviderBinding(
            model=model,
            provider=provider,
            base_url=final_base_url,
            api_key_env=final_api_key_env,
            api_key=final_api_key,
            is_local=final_is_local,
            source=source,
            slot=slot,
            tier=tier,
            api_mode="chat_completions",
            route_chain=route_chain or [],
        )

    def _register(self, binding: ProviderBinding) -> None:
        names = {binding.model, self._short_model(binding.model)}
        if binding.provider:
            names.add(f"{binding.provider}/{self._short_model(binding.model)}")
        for name in names:
            if name:
                self._cache[(binding.provider, name)] = binding
                self._cache[(None, name)] = binding

    def _tier_route_chain(self, tier_key: str, tier: Dict[str, Any]) -> List[Dict[str, Any]]:
        chain: List[Dict[str, Any]] = []
        if tier.get("model"):
            chain.append({"slot": "primary", "model": tier.get("model"), "provider": tier.get("provider")})
        if tier_key == "super_god" and tier.get("model_b"):
            chain.append({"slot": "secondary_reserved", "model": tier.get("model_b"), "provider": tier.get("provider_b")})
        for slot in ("fallback", "emergency"):
            item = tier.get(slot)
            if isinstance(item, dict) and item.get("model"):
                chain.append({"slot": slot, "model": item.get("model"), "provider": item.get("provider") or tier.get("provider")})
        return chain

    def _build_mapping(self) -> None:
        # Provider 声明模型
        for provider_name, provider in self._providers.items():
            for model in provider.get("models", []) or []:
                binding = self._make_binding(
                    model=model,
                    provider=provider_name,
                    base_url=provider.get("base_url"),
                    api_key_env=provider.get("api_key_env"),
                    api_key=provider.get("api_key"),
                    is_local=provider.get("is_local", False),
                    source=f"providers.{provider_name}.models",
                )
                self._register(binding)

        # 五档槽位直接注册，优先覆盖 provider 通用注册。V5.1.3 每档登记 primary/fallback/emergency。
        for tier_key, tier in self._tiers.items():
            route_chain = self._tier_route_chain(tier_key, tier)
            # fallback / emergency 托底槽位
            for slot in ("fallback", "emergency"):
                item = tier.get(slot)
                if isinstance(item, dict) and item.get("model"):
                    binding = self._make_binding(
                        model=item.get("model"),
                        provider=item.get("provider") or tier.get("provider"),
                        base_url=item.get("base_url") or tier.get("base_url"),
                        api_key_env=item.get("api_key_env") or tier.get("api_key_env"),
                        api_key=item.get("api_key") or tier.get("api_key"),
                        is_local=item.get("is_local", tier.get("is_local", False)),
                        source=f"model_tiers.{tier_key}.{slot}",
                        slot=slot,
                        tier=tier_key,
                        route_chain=route_chain,
                    )
                    self._register(binding)

            # primary + super_god secondary_reserved
            slot_specs = [
                ("primary", "model", "provider", "base_url", "api_key_env", "api_key"),
                ("secondary_reserved", "model_b", "provider_b", "base_url_b", "api_key_env_b", "api_key_b"),
            ]
            for slot, model_key, provider_key, base_url_key, api_key_env_key, api_key_key in slot_specs:
                if model_key not in tier:
                    continue
                model = tier.get(model_key)
                if not model:
                    continue
                binding = self._make_binding(
                    model=model,
                    provider=tier.get(provider_key) or tier.get("provider"),
                    base_url=tier.get(base_url_key) or tier.get("base_url"),
                    api_key_env=tier.get(api_key_env_key) or tier.get("api_key_env"),
                    api_key=tier.get(api_key_key) or tier.get("api_key"),
                    is_local=tier.get("is_local", False),
                    source=f"model_tiers.{tier_key}.{slot}",
                    slot=slot,
                    tier=tier_key,
                    route_chain=route_chain,
                )
                self._register(binding)

        # fallback 注册
        if self._fallback.get("model"):
            binding = self._make_binding(
                model=self._fallback.get("model"),
                provider=self._fallback.get("provider"),
                base_url=self._fallback.get("base_url"),
                api_key_env=self._fallback.get("api_key_env"),
                api_key=self._fallback.get("api_key"),
                is_local=self._fallback.get("is_local"),
                source="phoenix_open.fallback",
            )
            self._register(binding)

    def resolve_binding(self, model: str, provider: Optional[str] = None, include_secret: bool = False) -> ProviderBinding:
        """返回完整 ProviderBinding。include_secret 仅兼容参数，不影响对象内容。"""
        model = self._normalize_model(model)
        if not model:
            raise ValueError("resolve_binding() 缺少 model")

        candidates = []
        if provider:
            candidates.extend([
                (provider, model),
                (provider, self._short_model(model)),
                (provider, f"{provider}/{self._short_model(model)}"),
            ])
        pref = self._provider_from_model(model)
        if pref:
            candidates.extend([
                (pref, model),
                (pref, self._short_model(model)),
            ])
        candidates.extend([
            (None, model),
            (None, self._short_model(model)),
        ])

        seen = set()
        for key in candidates:
            if key in seen:
                continue
            seen.add(key)
            if key in self._cache:
                binding = self._cache[key]
                if provider and binding.provider != provider:
                    raise ValueError(
                        f"Provider串位风险: model='{model}' 请求 provider='{provider}'，"
                        f"但缓存绑定 provider='{binding.provider}'"
                    )
                return binding

        # 明确 provider 但 provider.models 未声明时，仍允许用该 provider 的通用配置解析。
        if provider and provider in self._providers:
            return self._make_binding(model=model, provider=provider, source=f"explicit_provider.{provider}")

        # 模型名前缀 provider/model 可作为强绑定。
        pref = self._provider_from_model(model)
        if pref and pref in self._providers:
            return self._make_binding(model=model, provider=pref, source=f"model_prefix.{pref}")

        raise ValueError(
            f"无法解析模型 '{model}' 的 Provider 绑定。"
            f"请在 phoenix_open.model_tiers 或 phoenix_open.providers.models 中配置。"
            f"已配置 Provider: {list(self._providers.keys())}"
        )

    def resolve(self, model: str, provider: Optional[str] = None, include_secret: bool = True) -> Tuple[str, str]:
        """
        兼容旧接口：返回 (base_url, api_key)。
        新代码优先使用 resolve_binding()，因为它能携带 api_key_env 和 provider。
        """
        binding = self.resolve_binding(model, provider)
        key = ""
        if binding.api_key_env:
            key = os.environ.get(binding.api_key_env, "") if include_secret else f"env:{binding.api_key_env}"
        elif binding.api_key:
            key = binding.api_key if include_secret else "[REDACTED]"
        return binding.base_url, key

    def get_api_key(self, model: str, provider: Optional[str] = None, include_secret: bool = True) -> str:
        _, api_key = self.resolve(model, provider, include_secret=include_secret)
        return api_key

    def get_base_url(self, model: str, provider: Optional[str] = None) -> str:
        return self.resolve_binding(model, provider).base_url

    def get_api_key_env(self, model: str, provider: Optional[str] = None) -> Optional[str]:
        return self.resolve_binding(model, provider).api_key_env

    def validate_all(self) -> List[str]:
        """验证五档槽位与 Provider 绑定完整性；不泄露真实 key。"""
        issues: List[str] = []
        required = ["daily", "medium", "deep", "god", "super_god"]
        for tier_key in required:
            if tier_key not in self._tiers:
                issues.append(f"{tier_key}: 缺少模型槽位")

        for tier_key, tier in self._tiers.items():
            for suffix in ("", "_a", "_b"):
                model_key = "model" + suffix
                if model_key not in tier:
                    continue
                model = tier.get(model_key)
                provider = tier.get("provider" + suffix) or tier.get("provider")
                if not model:
                    issues.append(f"{tier_key}{suffix}: 未配置模型")
                    continue
                try:
                    binding = self.resolve_binding(model, provider)
                    if provider and binding.provider != provider:
                        issues.append(f"{tier_key}{suffix}: provider串位 {provider} -> {binding.provider}")
                    if not binding.base_url:
                        issues.append(f"{tier_key}{suffix}: 缺少base_url")
                    if not binding.is_local and not binding.api_key_env and not binding.api_key:
                        issues.append(f"{tier_key}{suffix}: 云端Provider缺少api_key_env/api_key")
                except Exception as e:
                    issues.append(f"{tier_key}{suffix}: {e}")

            if tier.get("auto_execute") is True:
                issues.append(f"{tier_key}: V5.1.3 下 auto_execute 必须为 false")
            expected_trigger = {"deep": "/深度", "god": "/大神", "super_god": "/真神"}.get(tier_key)
            if expected_trigger:
                if tier.get("requires_approval") is not True:
                    issues.append(f"{tier_key}: 高档必须 requires_approval=true")
                if tier.get("trigger") != expected_trigger:
                    issues.append(f"{tier_key}: 缺少明确手动触发词")
            for required_slot in ("fallback", "emergency"):
                item = tier.get(required_slot)
                if not isinstance(item, dict) or not item.get("model") or not item.get("provider"):
                    issues.append(f"{tier_key}: 缺少 {required_slot} 托底模型")
            if tier.get("api_mode") == "openai":
                issues.append(f"{tier_key}: api_mode_openai_forbidden，必须使用 chat_completions")

        return issues

    def audit_bindings(self) -> List[Dict[str, Any]]:
        """返回脱敏绑定表，用于 doctor/审计。"""
        rows = []
        seen = set()
        for binding in self._cache.values():
            key = (binding.model, binding.provider, binding.source)
            if key in seen:
                continue
            seen.add(key)
            rows.append(binding.as_dict(include_secret=False))
        return sorted(rows, key=lambda x: (x["provider"], x["model"], x["source"]))
