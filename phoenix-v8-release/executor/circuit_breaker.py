"""
不死鸟 Phoenix V8 — 熔断器

借鉴微服务架构的熔断模式：
- CLOSED：正常，请求通过
- OPEN：熔断，请求拒绝（直接降级）
- HALF_OPEN：试探，少量请求测试是否恢复

每个模型一个独立熔断器，互不影响。
"""

import time
import threading
from typing import Optional, Callable


class CircuitBreaker:
    """
    熔断器

    用法:
        cb = CircuitBreaker(failure_threshold=5, cooldown_seconds=60)

        # 请求前检查
        if not cb.allow_request():
            # 降级处理
            pass

        # 请求后报告结果
        try:
            result = call_model()
            cb.report_success()
        except Exception:
            cb.report_failure()
    """

    STATE_CLOSED = "closed"
    STATE_OPEN = "open"
    STATE_HALF_OPEN = "half_open"

    def __init__(
        self,
        failure_threshold: int = 5,
        success_threshold: int = 3,
        cooldown_seconds: int = 60,
        name: str = "default",
    ):
        self._name = name
        self._state = self.STATE_CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._failure_threshold = failure_threshold
        self._success_threshold = success_threshold
        self._cooldown_seconds = cooldown_seconds
        self._last_failure_time = 0.0
        self._total_requests = 0
        self._total_failures = 0
        self._total_successes = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        """当前状态"""
        with self._lock:
            if self._state == self.STATE_OPEN:
                # 检查冷却期
                if time.time() - self._last_failure_time > self._cooldown_seconds:
                    self._state = self.STATE_HALF_OPEN
                    self._success_count = 0
            return self._state

    @property
    def is_healthy(self) -> bool:
        """是否健康"""
        return self.state == self.STATE_CLOSED

    def allow_request(self) -> bool:
        """是否允许请求"""
        with self._lock:
            self._total_requests += 1
            # Don't call self.state property; it tries to acquire lock again (reentrant issue)
            # Manually check cooldown instead
            if self._state == self.STATE_OPEN:
                if time.time() - self._last_failure_time > self._cooldown_seconds:
                    self._state = self.STATE_HALF_OPEN
                    self._success_count = 0

            if self._state == self.STATE_CLOSED or self._state == self.STATE_HALF_OPEN:
                return True
            else:
                return False

    def report_success(self):
        """报告成功"""
        with self._lock:
            self._total_successes += 1

            if self._state == self.STATE_HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self._success_threshold:
                    # 恢复正常
                    self._state = self.STATE_CLOSED
                    self._failure_count = 0
                    self._success_count = 0
            elif self._state == self.STATE_CLOSED:
                # 重置失败计数
                self._failure_count = 0

    def report_failure(self):
        """报告失败"""
        with self._lock:
            self._total_failures += 1
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == self.STATE_HALF_OPEN:
                # 半开状态下失败 → 回到OPEN
                self._state = self.STATE_OPEN
                self._success_count = 0
            elif self._state == self.STATE_CLOSED:
                if self._failure_count >= self._failure_threshold:
                    # 触发熔断
                    self._state = self.STATE_OPEN

    def force_open(self):
        """强制熔断"""
        with self._lock:
            self._state = self.STATE_OPEN
            self._last_failure_time = time.time()

    def force_close(self):
        """强制恢复"""
        with self._lock:
            self._state = self.STATE_CLOSED
            self._failure_count = 0
            self._success_count = 0

    def get_stats(self) -> dict:
        """获取统计"""
        with self._lock:
            return {
                "name": self._name,
                "state": self._state,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "total_requests": self._total_requests,
                "total_failures": self._total_failures,
                "total_successes": self._total_successes,
                "failure_rate": f"{self._total_failures / max(self._total_requests, 1) * 100:.1f}%",
                "last_failure": self._last_failure_time,
            }


class CircuitBreakerManager:
    """
    熔断器管理器

    管理所有模型的熔断器

    用法:
        manager = CircuitBreakerManager()

        # 检查模型是否可用
        if manager.is_available("claude-opus-4-6"):
            # 使用该模型
            pass

        # 报告结果
        manager.report("claude-opus-4-6", success=True)

        # 获取所有熔断状态
        status = manager.get_all_status()
    """

    def __init__(self, config: dict = None):
        config = config or {}
        self._breakers: dict[str, CircuitBreaker] = {}
        self._default_config = {
            "failure_threshold": config.get("failure_threshold", 5),
            "success_threshold": config.get("success_threshold", 3),
            "cooldown_seconds": config.get("cooldown_seconds", 60),
        }

    def get_breaker(self, model: str) -> CircuitBreaker:
        """获取模型的熔断器（不存在则创建）"""
        if model not in self._breakers:
            self._breakers[model] = CircuitBreaker(
                name=model,
                **self._default_config,
            )
        return self._breakers[model]

    def is_available(self, model: str) -> bool:
        """检查模型是否可用"""
        breaker = self.get_breaker(model)
        return breaker.allow_request()

    def report(self, model: str, success: bool):
        """报告模型调用结果"""
        breaker = self.get_breaker(model)
        if success:
            breaker.report_success()
        else:
            breaker.report_failure()

    def get_available_models(self, models: list[str]) -> list[str]:
        """从模型列表中过滤出可用的"""
        return [m for m in models if self.is_available(m)]

    def get_all_status(self) -> dict:
        """获取所有熔断器状态"""
        return {
            model: breaker.get_stats()
            for model, breaker in self._breakers.items()
        }

    def get_unhealthy_models(self) -> list[str]:
        """获取不健康的模型列表"""
        return [
            model for model, breaker in self._breakers.items()
            if not breaker.is_healthy
        ]
