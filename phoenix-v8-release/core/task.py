"""
不死鸟 Phoenix V8 — Task 任务生命周期管理

借鉴Claude Code冠军架构的Task系统：
- 每个任务有唯一ID、类型、状态、时间戳
- 支持并行、后台、超时
- 任务结果持久化到文件
"""

import json
import time
import uuid
import threading
from enum import Enum
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Any, Optional, Callable


class TaskType(Enum):
    """任务类型"""
    CHAT = "chat"                   # 普通对话
    CODE = "code"                   # 代码生成/修复
    REASONING = "reasoning"         # 复杂推理
    TOOL_CALL = "tool_call"         # 工具调用
    DELEGATION = "delegation"       # 子Agent委派
    MEMORY_OP = "memory_op"         # 记忆操作
    ROUTING = "routing"             # 路由决策
    COMPRESSION = "compression"     # 压缩操作
    SELF_HEAL = "self_heal"         # 自我修复
    EVOLUTION = "evolution"         # 自我进化


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class Task:
    """任务对象"""
    id: str = ""
    type: str = TaskType.CHAT.value
    status: str = TaskStatus.PENDING.value
    description: str = ""
    input_data: dict = field(default_factory=dict)
    output_data: dict = field(default_factory=dict)
    error: str = ""
    model: str = ""
    provider: str = ""
    tokens_input: int = 0
    tokens_output: int = 0
    cost: float = 0.0
    start_time: float = 0.0
    end_time: float = 0.0
    timeout_seconds: int = 300
    retry_count: int = 0
    max_retries: int = 3
    parent_task_id: str = ""
    created_at: float = 0.0

    def __post_init__(self):
        if not self.id:
            self.id = f"task_{uuid.uuid4().hex[:12]}"
        if not self.created_at:
            self.created_at = time.time()

    @property
    def duration(self) -> float:
        """任务耗时（秒）"""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        elif self.start_time:
            return time.time() - self.start_time
        return 0.0

    @property
    def is_terminal(self) -> bool:
        """是否已结束"""
        return self.status in (
            TaskStatus.COMPLETED.value,
            TaskStatus.FAILED.value,
            TaskStatus.TIMEOUT.value,
            TaskStatus.CANCELLED.value,
        )

    def to_dict(self) -> dict:
        return asdict(self)


class TaskManager:
    """
    任务管理器

    用法:
        tm = TaskManager()

        # 创建任务
        task = tm.create(TaskType.CHAT, description="用户问天气")

        # 开始任务
        tm.start(task.id, model="gpt-5.4-2", provider="nous")

        # 完成任务
        tm.complete(task.id, output={"response": "今天晴天"})

        # 查看活跃任务
        active = tm.get_active_tasks()

        # 查看统计
        stats = tm.get_stats()
    """

    def __init__(self, max_concurrent: int = 5, task_dir: Optional[str] = None):
        self._tasks: dict[str, Task] = {}
        self._lock = threading.RLock()
        self._max_concurrent = max_concurrent
        self._task_dir = Path(task_dir) if task_dir else None
        self._listeners: list[Callable] = []

        # 加载历史任务
        if self._task_dir:
            self._task_dir.mkdir(parents=True, exist_ok=True)
            self._load_tasks()

    def create(
        self,
        task_type: TaskType,
        description: str = "",
        input_data: dict = None,
        parent_task_id: str = "",
        timeout_seconds: int = 300,
    ) -> Task:
        """创建新任务"""
        with self._lock:
            # 检查并发限制
            active_count = len(self.get_active_tasks())
            if active_count >= self._max_concurrent:
                raise RuntimeError(
                    f"并发任务数已达上限({self._max_concurrent})，"
                    f"当前活跃: {active_count}"
                )

            task = Task(
                type=task_type.value,
                description=description,
                input_data=input_data or {},
                parent_task_id=parent_task_id,
                timeout_seconds=timeout_seconds,
            )
            self._tasks[task.id] = task
            self._notify("created", task)
            self._save_task(task)
            return task

    def start(self, task_id: str, model: str = "", provider: str = "") -> Task:
        """开始执行任务"""
        with self._lock:
            task = self._get_task(task_id)
            task.status = TaskStatus.RUNNING.value
            task.start_time = time.time()
            task.model = model
            task.provider = provider
            self._notify("started", task)
            self._save_task(task)
            return task

    def complete(self, task_id: str, output: dict = None, tokens_in: int = 0,
                 tokens_out: int = 0, cost: float = 0.0) -> Task:
        """任务完成"""
        with self._lock:
            task = self._get_task(task_id)
            task.status = TaskStatus.COMPLETED.value
            task.end_time = time.time()
            task.output_data = output or {}
            task.tokens_input = tokens_in
            task.tokens_output = tokens_out
            task.cost = cost
            self._notify("completed", task)
            self._save_task(task)
            return task

    def fail(self, task_id: str, error: str = "") -> Task:
        """任务失败"""
        with self._lock:
            task = self._get_task(task_id)
            task.status = TaskStatus.FAILED.value
            task.end_time = time.time()
            task.error = error
            self._notify("failed", task)
            self._save_task(task)
            return task

    def timeout(self, task_id: str) -> Task:
        """任务超时"""
        with self._lock:
            task = self._get_task(task_id)
            task.status = TaskStatus.TIMEOUT.value
            task.end_time = time.time()
            task.error = f"任务超时({task.timeout_seconds}s)"
            self._notify("timeout", task)
            self._save_task(task)
            return task

    def cancel(self, task_id: str) -> Task:
        """取消任务"""
        with self._lock:
            task = self._get_task(task_id)
            task.status = TaskStatus.CANCELLED.value
            task.end_time = time.time()
            self._notify("cancelled", task)
            self._save_task(task)
            return task

    def retry(self, task_id: str) -> Optional[Task]:
        """重试失败的任务"""
        with self._lock:
            old_task = self._get_task(task_id)
            if old_task.retry_count >= old_task.max_retries:
                return None

            # 创建新任务（继承参数）
            new_task = self.create(
                task_type=TaskType(old_task.type),
                description=f"[重试{old_task.retry_count + 1}] {old_task.description}",
                input_data=old_task.input_data,
                parent_task_id=old_task.parent_task_id,
                timeout_seconds=old_task.timeout_seconds,
            )
            new_task.retry_count = old_task.retry_count + 1
            return new_task

    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务"""
        with self._lock:
            return self._tasks.get(task_id)

    def get_active_tasks(self) -> list[Task]:
        """获取所有活跃任务"""
        with self._lock:
            return [
                t for t in self._tasks.values()
                if t.status == TaskStatus.RUNNING.value
            ]

    def check_timeouts(self) -> list[Task]:
        """检查并处理超时任务"""
        timed_out = []
        with self._lock:
            now = time.time()
            for task in self.get_active_tasks():
                if now - task.start_time > task.timeout_seconds:
                    self.timeout(task.id)
                    timed_out.append(task)
        return timed_out

    def get_stats(self) -> dict:
        """获取任务统计"""
        with self._lock:
            all_tasks = list(self._tasks.values())
            completed = [t for t in all_tasks if t.status == TaskStatus.COMPLETED.value]
            failed = [t for t in all_tasks if t.status == TaskStatus.FAILED.value]

            total_cost = sum(t.cost for t in completed)
            total_tokens_in = sum(t.tokens_input for t in completed)
            total_tokens_out = sum(t.tokens_output for t in completed)

            avg_duration = 0.0
            if completed:
                avg_duration = sum(t.duration for t in completed) / len(completed)

            # 按类型统计
            type_stats = {}
            for t in all_tasks:
                if t.type not in type_stats:
                    type_stats[t.type] = {"total": 0, "completed": 0, "failed": 0}
                type_stats[t.type]["total"] += 1
                if t.status == TaskStatus.COMPLETED.value:
                    type_stats[t.type]["completed"] += 1
                elif t.status == TaskStatus.FAILED.value:
                    type_stats[t.type]["failed"] += 1

            return {
                "total": len(all_tasks),
                "active": len(self.get_active_tasks()),
                "completed": len(completed),
                "failed": len(failed),
                "total_cost": f"${total_cost:.4f}",
                "total_tokens_in": total_tokens_in,
                "total_tokens_out": total_tokens_out,
                "avg_duration": f"{avg_duration:.2f}s",
                "by_type": type_stats,
            }

    def get_recent_tasks(self, limit: int = 10) -> list[dict]:
        """获取最近的任务摘要"""
        with self._lock:
            tasks = sorted(self._tasks.values(), key=lambda t: t.created_at, reverse=True)
            return [
                {
                    "id": t.id,
                    "type": t.type,
                    "status": t.status,
                    "description": t.description[:50],
                    "model": t.model,
                    "duration": f"{t.duration:.1f}s",
                    "cost": f"${t.cost:.4f}",
                }
                for t in tasks[:limit]
            ]

    def on_event(self, callback: Callable[[str, Task], None]):
        """注册事件监听器"""
        self._listeners.append(callback)

    def _get_task(self, task_id: str) -> Task:
        """获取任务（内部，带锁）"""
        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(f"任务不存在: {task_id}")
        return task

    def _notify(self, event: str, task: Task):
        """通知监听器"""
        for listener in self._listeners:
            try:
                listener(event, task)
            except Exception as exc:
                _ = exc

    def _save_task(self, task: Task):
        """持久化任务到磁盘"""
        if not self._task_dir:
            return
        try:
            task_file = self._task_dir / f"{task.id}.json"
            task_file.write_text(json.dumps(task.to_dict(), indent=2, ensure_ascii=False))
        except Exception as exc:
            _ = exc

    def _load_tasks(self):
        """从磁盘加载历史任务"""
        if not self._task_dir or not self._task_dir.exists():
            return
        try:
            for task_file in self._task_dir.glob("task_*.json"):
                data = json.loads(task_file.read_text())
                task = Task(**data)
                self._tasks[task.id] = task
        except Exception as exc:
            _ = exc
