"""
不死鸟 Phoenix V8 — AppState 全局状态机

单一事实来源。所有组件读状态、通过dispatch改状态。
类似Redux模式，保证系统状态可预测、可追踪、可恢复。
"""

import sys
import json
import time
import threading
import uuid
from enum import Enum
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Optional


@dataclass
class EventRecord:
    """统一事件记录"""
    id: str = ""
    kind: str = ""
    source: str = ""
    action: str = ""
    payload: dict = field(default_factory=dict)
    level: str = "info"
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.id:
            self.id = uuid.uuid4().hex[:12]
        if not self.timestamp:
            self.timestamp = time.time()

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EventStream:
    """最小事件流，支持追加、裁剪、查询。"""

    max_events: int = 200
    _events: list[EventRecord] = field(default_factory=list)

    def __post_init__(self):
        if self.max_events < 0:
            self.max_events = 0
        self._lock = threading.Lock()

    @property
    def _max_events(self) -> int:
        return self.max_events

    @_max_events.setter
    def _max_events(self, value: int):
        self.max_events = max(int(value), 0)

    def emit(self, kind: str, source: str, action: str = "", payload: dict = None, level: str = "info") -> EventRecord:
        with self._lock:
            record = EventRecord(
                kind=kind,
                source=source,
                action=action,
                payload=payload or {},
                level=level,
            )
            self._events.append(record)
            self.compact()
            return record

    def compact(self, keep: Optional[int] = None):
        keep = self._max_events if keep is None else keep
        if keep < 0:
            keep = 0
        if len(self._events) > keep:
            self._events = self._events[-keep:]

    def tail(self, limit: int = 50) -> list[dict]:
        return [e.to_dict() for e in self._events[-max(limit, 0):]]

    def __len__(self) -> int:
        return len(self._events)


class SystemMode(Enum):
    """系统运行模式"""
    NORMAL = "normal"           # 正常运行
    DEGRADED = "degraded"       # 降级运行（部分功能不可用）
    RECOVERY = "recovery"       # 恢复中
    EMERGENCY = "emergency"     # 紧急模式（只保留核心功能）


class CircuitState(Enum):
    """熔断器状态"""
    CLOSED = "closed"           # 正常（请求通过）
    OPEN = "open"              # 熔断（请求拒绝）
    HALF_OPEN = "half_open"    # 试探（少量请求测试）


@dataclass
class ModelBudget:
    """模型预算追踪"""
    monthly_limit: float = 50.0         # 月预算上限（美元）
    spent_today: float = 0.0            # 今日花费
    spent_month: float = 0.0            # 本月花费
    tokens_today: int = 0               # 今日token消耗
    tokens_month: int = 0               # 本月token消耗
    last_reset_day: str = ""            # 上次日重置日期
    last_reset_month: str = ""          # 上次月重置日期


@dataclass
class RouteStats:
    """路由统计"""
    total_requests: int = 0             # 总请求数
    model_usage: dict = field(default_factory=dict)   # 模型使用次数
    model_costs: dict = field(default_factory=dict)   # 模型花费
    fallback_count: int = 0             # 降级次数
    avg_latency: float = 0.0            # 平均延迟（秒）


@dataclass
class CircuitBreaker:
    """熔断器状态"""
    state: str = CircuitState.CLOSED.value
    failure_count: int = 0              # 连续失败次数
    failure_threshold: int = 5          # 熔断阈值
    success_count: int = 0              # 半开状态下的成功数
    success_threshold: int = 3          # 恢复阈值
    last_failure_time: float = 0.0      # 上次失败时间
    cooldown_seconds: int = 60          # 冷却时间（秒）


@dataclass
class CompressStats:
    """压缩统计"""
    total_compressions: int = 0         # 总压缩次数
    tokens_saved: int = 0              # 节省的token数
    micro_compact_count: int = 0       # 微压缩次数
    deep_compact_count: int = 0        # 深压缩次数
    avg_compression_ratio: float = 0.0  # 平均压缩比


@dataclass
class PhoenixState:
    """不死鸟全局状态"""
    mode: str = SystemMode.NORMAL.value
    version: str = "5.1.0"
    started_at: float = 0.0
    uptime_seconds: float = 0.0

    # 事件流
    event_stream: EventStream = field(default_factory=EventStream)

    # 预算
    budget: ModelBudget = field(default_factory=ModelBudget)

    # 路由
    route_stats: RouteStats = field(default_factory=RouteStats)

    # 熔断器（每个模型一个）
    circuit_breakers: dict = field(default_factory=dict)

    # 压缩
    compress_stats: CompressStats = field(default_factory=CompressStats)

    # 当前活跃任务
    active_tasks: dict = field(default_factory=dict)

    # 当前使用的模型
    current_model: str = ""
    current_provider: str = ""

    # 会话上下文大小（tokens估计）
    context_size: int = 0

    # 自我进化统计
    evolution: dict = field(default_factory=lambda: {
        "antibodies_generated": 0,
        "antibodies_applied": 0,
        "self_repairs": 0,
        "optimizations_applied": 0,
    })


class AppStateManager:
    """
    全局状态管理器

    用法:
        state_mgr = AppStateManager()
        state = state_mgr.get_state()
        state_mgr.dispatch("update_budget", {"spent_today": 0.05})
        state_mgr.on_change(lambda s: print(f"状态变更: {s.mode}"))
    """

    def __init__(self, state_file: Optional[str] = None):
        self._state = PhoenixState(started_at=time.time())
        self._lock = threading.RLock()
        self._listeners: list[Callable] = []
        self._state_file = Path(state_file) if state_file else None

        # 加载持久化状态
        if self._state_file and self._state_file.exists():
            self._load_state()

    def emit_event(self, kind: str, source: str, action: str = "", payload: dict = None, level: str = "info") -> EventRecord:
        """写入统一事件流"""
        with self._lock:
            record = self._state.event_stream.emit(kind, source, action, payload or {}, level)
            self._save_state()
            return record

    def get_state(self) -> PhoenixState:
        """获取当前状态（快照）"""
        with self._lock:
            self._state.uptime_seconds = time.time() - self._state.started_at
            return self._state

    def dispatch(self, action: str, payload: dict = None) -> bool:
        """
        派发状态变更

        支持的action:
        - set_mode: 设置系统模式
        - update_budget: 更新预算
        - update_route: 更新路由统计
        - circuit_trip: 熔断器触发
        - circuit_reset: 熔断器重置
        - update_compress: 更新压缩统计
        - add_task: 添加活跃任务
        - remove_task: 移除活跃任务
        - update_context: 更新上下文大小
        - update_model: 更新当前模型
        - evolution_event: 自我进化事件
        """
        payload = payload or {}

        with self._lock:
            old_state = self._state

            if action == "set_mode":
                self._state.mode = payload.get("mode", SystemMode.NORMAL.value)

            elif action == "update_budget":
                for k, v in payload.items():
                    if hasattr(self._state.budget, k):
                        setattr(self._state.budget, k, v)

            elif action == "emit_event":
                self._state.event_stream.emit(
                    kind=payload.get("kind", action),
                    source=payload.get("source", "state"),
                    action=payload.get("event_action", ""),
                    payload=payload.get("payload", {}),
                    level=payload.get("level", "info"),
                )

            elif action == "update_route":
                for k, v in payload.items():
                    if hasattr(self._state.route_stats, k):
                        setattr(self._state.route_stats, k, v)

            elif action == "circuit_trip":
                model = payload.get("model", "default")
                if model not in self._state.circuit_breakers:
                    self._state.circuit_breakers[model] = CircuitBreaker()
                cb = self._state.circuit_breakers[model]
                cb.state = CircuitState.OPEN.value
                cb.failure_count += 1
                cb.last_failure_time = time.time()

            elif action == "circuit_reset":
                model = payload.get("model", "default")
                if model in self._state.circuit_breakers:
                    cb = self._state.circuit_breakers[model]
                    cb.state = CircuitState.CLOSED.value
                    cb.failure_count = 0
                    cb.success_count = 0

            elif action == "circuit_half_open":
                model = payload.get("model", "default")
                if model in self._state.circuit_breakers:
                    self._state.circuit_breakers[model].state = CircuitState.HALF_OPEN.value

            elif action == "circuit_success":
                model = payload.get("model", "default")
                if model in self._state.circuit_breakers:
                    cb = self._state.circuit_breakers[model]
                    if cb.state == CircuitState.HALF_OPEN.value:
                        cb.success_count += 1
                        if cb.success_count >= cb.success_threshold:
                            cb.state = CircuitState.CLOSED.value
                            cb.failure_count = 0
                            cb.success_count = 0

            elif action == "update_compress":
                for k, v in payload.items():
                    if hasattr(self._state.compress_stats, k):
                        setattr(self._state.compress_stats, k, v)

            elif action == "add_task":
                task_id = payload.get("task_id")
                if task_id:
                    self._state.active_tasks[task_id] = payload

            elif action == "remove_task":
                task_id = payload.get("task_id")
                self._state.active_tasks.pop(task_id, None)

            elif action == "update_context":
                self._state.context_size = payload.get("size", 0)

            elif action == "update_model":
                self._state.current_model = payload.get("model", "")
                self._state.current_provider = payload.get("provider", "")

            elif action == "evolution_event":
                event_type = payload.get("type", "")
                if event_type in self._state.evolution:
                    self._state.evolution[event_type] += 1

            elif action == "event_stream":
                self._state.event_stream.emit(
                    kind=payload.get("type", "unknown"),
                    source=payload.get("source", "phoenix"),
                    action=payload.get("action", "model_result"),
                    payload=payload.get("content", {}),
                    level=payload.get("level", "info"),
                )
                max_len = payload.get("max_len", 200)
                self._state.event_stream.compact(max_len)

            elif action == "gc":
                self.gc(payload)

            # 通知监听器
            for listener in self._listeners:
                try:
                    listener(self._state)
                except Exception as exc:
                    _ = exc

            # 持久化
            self._save_state()

            return True

    def gc(self, payload: dict = None):
        """最小垃圾回收：当前只裁剪事件流长度。"""
        payload = payload or {}
        max_events = payload.get("event_history_max", 200)
        if len(self._state.event_stream) > max_events:
            self._state.event_stream.compact(max_events)
        self._save_state()
        return True

    def on_change(self, callback: Callable[[PhoenixState], None]):
        """注册状态变更监听器"""
        self._listeners.append(callback)

    def _save_state(self):
        """持久化状态到磁盘"""
        if not self._state_file:
            return
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            data = asdict(self._state)
            self._state_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[AppStateManager] 状态持久化失败: {e}", file=sys.stderr)

    def _load_state(self):
        """从磁盘加载状态"""
        try:
            data = json.loads(self._state_file.read_text())
            # 恢复关键字段，保留运行时字段
            if "budget" in data:
                for k, v in data["budget"].items():
                    if hasattr(self._state.budget, k):
                        setattr(self._state.budget, k, v)
            if "route_stats" in data:
                for k, v in data["route_stats"].items():
                    if hasattr(self._state.route_stats, k):
                        setattr(self._state.route_stats, k, v)
            if "compress_stats" in data:
                for k, v in data["compress_stats"].items():
                    if hasattr(self._state.compress_stats, k):
                        setattr(self._state.compress_stats, k, v)
            if "active_tasks" in data:
                self._state.active_tasks = data["active_tasks"]
            if "event_stream" in data:
                events = data["event_stream"]
                if isinstance(events, dict) and "_events" in events:
                    self._state.event_stream._events = [EventRecord(**e) for e in events.get("_events", [])]
                elif isinstance(events, list):
                    self._state.event_stream._events = [EventRecord(**e) for e in events]
            if "evolution" in data:
                self._state.evolution.update(data["evolution"])
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[AppStateManager] 状态加载失败: {e}", file=sys.stderr)

    def get_health_summary(self) -> dict:
        """获取系统健康摘要"""
        state = self.get_state()
        open_circuits = [
            model for model, cb in state.circuit_breakers.items()
            if cb.state == CircuitState.OPEN.value
        ]
        return {
            "mode": state.mode,
            "uptime": f"{state.uptime_seconds / 3600:.1f}h",
            "budget_used": f"${state.budget.spent_month:.2f}/${state.budget.monthly_limit:.2f}",
            "budget_pct": f"{state.budget.spent_month / max(state.budget.monthly_limit, 1e-9) * 100:.1f}%",
            "active_tasks": len(state.active_tasks),
            "context_size": state.context_size,
            "event_stream_size": len(state.event_stream),
            "open_circuits": open_circuits,
            "compressions": state.compress_stats.total_compressions,
            "tokens_saved": state.compress_stats.tokens_saved,
            "antibodies": state.evolution["antibodies_generated"],
        }
