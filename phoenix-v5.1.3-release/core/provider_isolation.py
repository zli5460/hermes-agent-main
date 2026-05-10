"""
Phoenix Open — Provider隔离层（核心架构）

设计原则：
1. 每个模型必须绑定到唯一的Provider
2. 每个API调用必须经过隔离层
3. 每次调用必须记录完整审计日志
4. Provider之间完全隔离，互不影响

这是整个系统的安全底线。
"""

import os
import json
import time
import logging
from pathlib import Path
from typing import Optional, Dict, Tuple, Any, List
from dataclasses import dataclass, field, asdict
from threading import Lock


# ── 审计日志 ──────────────────────────────────────────────────

@dataclass
class APICallRecord:
    """单次API调用的完整审计记录"""
    timestamp: float
    model: str
    provider: str
    base_url: str
    api_key_masked: str       # 脱敏后的key（只显示前4位+后4位）
    task_type: str
    success: bool
    status_code: int = 0
    error_message: str = ""
    latency_ms: float = 0
    input_tokens: int = 0
    output_tokens: int = 0
    
    def to_dict(self) -> dict:
        return asdict(self)


class AuditTrail:
    """
    API调用审计日志
    
    记录每次调用的完整上下文：
    - 哪个模型
    - 哪个Provider
    - 哪个端点
    - 哪个Key（脱敏）
    - 成功/失败
    - 延迟
    - Token消耗
    """
    
    def __init__(self, log_dir: Optional[str] = None):
        self._log_dir = Path(log_dir or Path.home() / ".hermes/phoenix-open/logs")
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._records: list = []
        self._lock = Lock()
        self._logger = logging.getLogger("phoenix.audit")
    
    def record(self, call: APICallRecord) -> None:
        """记录一次API调用"""
        with self._lock:
            self._records.append(call)
            
            # 写入日志文件
            log_file = self._log_dir / f"api_calls_{time.strftime('%Y%m%d')}.jsonl"
            with open(log_file, 'a') as f:
                f.write(json.dumps(call.to_dict(), ensure_ascii=False) + '\n')
            
            # 控制台输出
            status = "✅" if call.success else "❌"
            self._logger.info(
                f"{status} {call.provider}/{call.model} → {call.base_url[:40]} "
                f"[{call.status_code}] {call.latency_ms:.0f}ms"
            )
    
    def get_records(self, provider: Optional[str] = None, model: Optional[str] = None,
                    hours: int = 24) -> List[APICallRecord]:
        """查询审计记录"""
        cutoff = time.time() - hours * 3600
        with self._lock:
            records = [r for r in self._records if r.timestamp > cutoff]
            if provider:
                records = [r for r in records if r.provider == provider]
            if model:
                records = [r for r in records if r.model == model]
            return records
    
    def get_stats(self, provider: Optional[str] = None) -> Dict[str, Any]:
        """获取统计信息"""
        records = self.get_records(provider=provider)
        total = len(records)
        success = sum(1 for r in records if r.success)
        failed = total - success
        avg_latency = sum(r.latency_ms for r in records) / max(total, 1)
        
        return {
            "total_calls": total,
            "success": success,
            "failed": failed,
            "success_rate": f"{success/max(total,1)*100:.1f}%",
            "avg_latency_ms": f"{avg_latency:.0f}",
        }


# ── Provider配置 ──────────────────────────────────────────────

@dataclass
class ProviderConfig:
    """单个Provider的完整配置（不可变）"""
    name: str                 # Provider名称（如 "openai"）
    base_url: str             # API端点
    api_key: str              # API Key（明文，仅内部使用）
    is_local: bool = False    # 是否本地模型
    models: list = field(default_factory=list)  # 支持的模型列表
    rate_limit: int = 60      # 每分钟请求限制
    timeout: int = 60         # 超时时间（秒）
    priority: int = 0         # 优先级（越高越优先）
    
    def mask_key(self) -> str:
        """脱敏显示Key"""
        if len(self.api_key) <= 8:
            return "****"
        return f"{self.api_key[:4]}...{self.api_key[-4:]}"


# ── Provider注册表 ────────────────────────────────────────────

class ProviderRegistry:
    """
    Provider中央注册表
    
    核心职责：
    1. 注册所有Provider（云端+本地）
    2. 模型→Provider绑定（一对多）
    3. 路由查找（模型名→完整Provider信息）
    4. 隔离验证（确保不会串Key）
    
    数据结构：
    providers: {provider_name: ProviderConfig}
    model_map: {model_name: provider_name}  # 一个模型只能属于一个Provider
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._providers: Dict[str, ProviderConfig] = {}
        self._model_map: Dict[str, str] = {}  # model → provider_name
        self._lock = Lock()
        
        if config:
            self._load_from_config(config)
    
    def _load_from_config(self, config: Dict[str, Any]) -> None:
        """从config.json加载Provider配置"""
        open_config = config.get("phoenix_open", {})
        providers = open_config.get("providers", {})
        tiers = open_config.get("model_tiers", {})
        
        # 注册所有Provider
        for name, p in providers.items():
            # 解析api_key（可能是环境变量引用）
            api_key = p.get("api_key", "")
            if api_key.startswith("$"):
                api_key = os.environ.get(api_key[1:], "")
            
            self.register(ProviderConfig(
                name=name,
                base_url=p.get("base_url", ""),
                api_key=api_key,
                is_local=p.get("is_local", False),
                models=p.get("models", []),
                rate_limit=p.get("rate_limit", 60),
                timeout=p.get("timeout", 60),
            ))
        
        # 从tier配置补充模型映射
        for tier_key, tier in tiers.items():
            model = tier.get("model") or tier.get("model_a")
            provider_name = tier.get("provider", "")
            if model and provider_name:
                # 不覆盖已注册的映射（provider配置优先）
                if model not in self._model_map:
                    self._model_map[model] = provider_name
                # 也注册带前缀的版本
                full_name = f"{provider_name}/{model}"
                if full_name not in self._model_map:
                    self._model_map[full_name] = provider_name
    
    def register(self, provider: ProviderConfig) -> None:
        """注册一个Provider"""
        with self._lock:
            self._providers[provider.name] = provider
            # 注册该Provider下的所有模型
            for model in provider.models:
                if model not in self._model_map:
                    self._model_map[model] = provider.name
    
    def resolve(self, model: str) -> Tuple[ProviderConfig, str]:
        """
        解析模型→Provider配置
        
        Args:
            model: 模型名（如 "gpt-5.5" 或 "openai/gpt-5.5"）
        
        Returns:
            (ProviderConfig, resolved_model_name)
        
        Raises:
            ValueError: 找不到对应的Provider
        """
        provider_name = None
        resolved_model = model
        
        # 1. 精确匹配（带前缀）
        if model in self._model_map:
            provider_name = self._model_map[model]
            # 如果输入是 "openai/gpt-5.5"，实际模型名是 "gpt-5.5"
            if "/" in model:
                resolved_model = model.split("/", 1)[1]
        
        # 2. 不带前缀匹配
        if not provider_name:
            for registered_model, pname in self._model_map.items():
                if registered_model.endswith(f"/{model}") or registered_model == model:
                    provider_name = pname
                    resolved_model = model
                    break
        
        # 3. 从Provider的models列表反查
        if not provider_name:
            for pname, pconfig in self._providers.items():
                if model in pconfig.models or f"{pname}/{model}" in pconfig.models:
                    provider_name = pname
                    resolved_model = model
                    break
        
        if not provider_name:
            raise ValueError(
                f"模型 '{model}' 未注册到任何Provider。"
                f"已注册的模型: {list(self._model_map.keys())[:10]}..."
            )
        
        provider = self._providers.get(provider_name)
        if not provider:
            raise ValueError(f"Provider '{provider_name}' 不存在")
        
        return provider, resolved_model
    
    def validate_isolation(self) -> List[str]:
        """
        验证隔离性：检查是否有模型被多个Provider注册
        
        Returns:
            问题列表（空=完全隔离）
        """
        issues = []
        
        # 检查同一模型是否被多个Provider注册
        model_providers = {}
        for model, provider in self._model_map.items():
            base_model = model.split("/", 1)[-1] if "/" in model else model
            if base_model not in model_providers:
                model_providers[base_model] = set()
            model_providers[base_model].add(provider)
        
        for model, providers in model_providers.items():
            if len(providers) > 1:
                issues.append(
                    f"⚠️ 模型 '{model}' 被多个Provider注册: {providers} — 可能串Key！"
                )
        
        # 检查是否有Provider缺少base_url
        for name, p in self._providers.items():
            if not p.base_url:
                issues.append(f"⚠️ Provider '{name}' 缺少base_url")
            if not p.is_local and not p.api_key:
                issues.append(f"⚠️ Provider '{name}' 是云端但缺少api_key")
        
        return issues
    
    def get_all_models(self) -> List[str]:
        """获取所有已注册的模型"""
        return list(self._model_map.keys())
    
    def get_all_providers(self) -> List[str]:
        """获取所有已注册的Provider"""
        return list(self._providers.keys())


# ── 隔离调用层 ────────────────────────────────────────────────

class IsolatedAPICaller:
    """
    隔离API调用层
    
    每次调用的完整流程：
    1. 从Registry解析模型→Provider
    2. 使用Provider的base_url+api_key
    3. 发送请求
    4. 记录审计日志
    5. 返回结果
    
    保证：
    - 每次调用使用正确的端点
    - 每次调用使用正确的Key
    - 每次调用都被记录
    - Provider之间完全隔离
    """
    
    def __init__(self, registry: ProviderRegistry, audit: AuditTrail = None):
        self._registry = registry
        self._audit = audit or AuditTrail()
        self._lock = Lock()
    
    def call(self, model: str, messages: List[Dict[str, str]],
             task_type: str = "unknown",
             provider_override: Optional[str] = None,
             **kwargs) -> Dict[str, Any]:
        """
        隔离调用API
        
        Args:
            model: 模型名
            messages: 消息列表
            task_type: 任务类型（用于审计）
            provider_override: 强制指定Provider（可选）
            **kwargs: 额外参数
        
        Returns:
            API响应字典
        """
        try:
            import requests
        except ImportError:
            raise RuntimeError("requests库未安装。请运行: pip install requests")

        # Step 1: 解析Provider
        try:
            provider, resolved_model = self._registry.resolve(model)
        except ValueError as e:
            # 记录失败
            self._audit.record(APICallRecord(
                timestamp=time.time(),
                model=model,
                provider="unknown",
                base_url="",
                api_key_masked="",
                task_type=task_type,
                success=False,
                error_message=str(e),
            ))
            raise
        
        # Step 2: 构建请求
        base_url = provider.base_url.rstrip("/")
        url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {provider.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": resolved_model,
            "messages": messages,
            **kwargs,
        }
        
        # Step 3: 发送请求（带超时）
        start_time = time.time()
        success = False
        status_code = 0
        error_msg = ""
        response_data = {}
        
        try:
            resp = requests.post(
                url, 
                headers=headers, 
                json=payload, 
                timeout=provider.timeout
            )
            status_code = resp.status_code
            response_data = resp.json()
            
            if resp.status_code == 200:
                success = True
            else:
                error_msg = f"HTTP {resp.status_code}: {resp.text[:200]}"
        
        except requests.exceptions.Timeout:
            error_msg = f"超时 ({provider.timeout}s)"
        except requests.exceptions.ConnectionError:
            error_msg = f"连接失败: {base_url}"
        except Exception as e:
            error_msg = str(e)
        
        latency_ms = (time.time() - start_time) * 1000
        
        # Step 4: 记录审计日志
        self._audit.record(APICallRecord(
            timestamp=time.time(),
            model=resolved_model,
            provider=provider.name,
            base_url=base_url,
            api_key_masked=provider.mask_key(),
            task_type=task_type,
            success=success,
            status_code=status_code,
            error_message=error_msg,
            latency_ms=latency_ms,
        ))
        
        # Step 5: 返回结果
        if not success:
            raise RuntimeError(
                f"API调用失败: {provider.name}/{resolved_model} → {base_url}\n"
                f"状态码: {status_code}\n"
                f"错误: {error_msg}"
            )
        
        return response_data


# ── 全局实例 ──────────────────────────────────────────────────

_registry: Optional[ProviderRegistry] = None
_caller: Optional[IsolatedAPICaller] = None
_audit: Optional[AuditTrail] = None


def init_provider_system(config: Dict[str, Any]) -> ProviderRegistry:
    """初始化Provider隔离系统（启动时调用一次）"""
    global _registry, _caller, _audit
    
    _audit = AuditTrail()
    _registry = ProviderRegistry(config)
    _caller = IsolatedAPICaller(_registry, _audit)
    
    # 验证隔离性
    issues = _registry.validate_isolation()
    if issues:
        for issue in issues:
            print(f"  {issue}")
    
    return _registry


def get_api_caller() -> IsolatedAPICaller:
    """获取隔离API调用器"""
    global _caller
    if _caller is None:
        raise RuntimeError("Provider系统未初始化，请先调用 init_provider_system()")
    return _caller


def get_audit_trail() -> AuditTrail:
    """获取审计日志"""
    global _audit
    if _audit is None:
        raise RuntimeError("Provider系统未初始化")
    return _audit
