"""
Phoenix V5.1 — 子Agent并行执行器（Parallel Sub-Agent Executor）

功能：
1. 支持多个子Agent同时执行任务
2. 任务分解后并行派发
3. 结果汇总后返回
"""

import json
import time
import concurrent.futures
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class SubAgentTask:
    """子Agent任务"""
    task_id: str
    description: str
    model: str
    status: str = "pending"  # pending/running/completed/failed
    result: Optional[str] = None
    error: Optional[str] = None
    start_time: float = 0
    end_time: float = 0


@dataclass
class ParallelResult:
    """并行执行结果"""
    tasks: List[SubAgentTask]
    total_time: float
    success_count: int
    fail_count: int


class ParallelSubAgentExecutor:
    """并行子Agent执行器"""

    def __init__(self, max_workers: int = 3):
        self.max_workers = max_workers

    def execute_parallel(self, tasks: List[Dict]) -> ParallelResult:
        """
        并行执行多个子Agent任务

        Args:
            tasks: [{"description": str, "model": str, "task_id": str}]

        Returns:
            ParallelResult
        """
        start_time = time.time()

        # 创建任务对象
        sub_tasks = []
        for t in tasks:
            sub_tasks.append(SubAgentTask(
                task_id=t.get("task_id", str(len(sub_tasks))),
                description=t.get("description", ""),
                model=t.get("model", ""),
                status="pending"
            ))

        # 并行执行
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {}
            for task in sub_tasks:
                future = executor.submit(self._execute_single, task)
                futures[future] = task

            for future in concurrent.futures.as_completed(futures):
                task = futures[future]
                try:
                    result = future.result(timeout=300)
                    task.result = result
                    task.status = "completed"
                except Exception as e:
                    task.error = str(e)
                    task.status = "failed"

        total_time = time.time() - start_time
        success_count = sum(1 for t in sub_tasks if t.status == "completed")
        fail_count = sum(1 for t in sub_tasks if t.status == "failed")

        return ParallelResult(
            tasks=sub_tasks,
            total_time=total_time,
            success_count=success_count,
            fail_count=fail_count
        )

    def _execute_single(self, task: SubAgentTask) -> str:
        """执行单个子Agent任务（placeholder）"""
        task.start_time = time.time()
        task.status = "running"

        # 实际执行逻辑需要集成到Phoenix的执行管道
        # 这里返回placeholder
        task.end_time = time.time()
        return f"Task {task.task_id} completed"

    def get_status(self, result: ParallelResult) -> str:
        """获取并行执行状态报告"""
        lines = [
            f"📊 并行执行报告",
            f"   总任务数: {len(result.tasks)}",
            f"   成功: {result.success_count}",
            f"   失败: {result.fail_count}",
            f"   总耗时: {result.total_time:.2f}秒",
            ""
        ]

        for task in result.tasks:
            emoji = "✅" if task.status == "completed" else "❌"
            lines.append(f"   {emoji} {task.task_id}: {task.description[:30]}...")

        return "\n".join(lines)
