"""
工作流步骤定义
"""

import time
import json
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Any, Optional


class StepStatus(Enum):
    """步骤状态"""
    PENDING = "pending"       # 待执行
    RUNNING = "running"       # 执行中
    COMPLETED = "completed"   # 已完成
    FAILED = "failed"         # 失败
    SKIPPED = "skipped"       # 跳过
    PAUSED = "paused"         # 暂停


@dataclass
class WorkflowStep:
    """工作流步骤"""
    name: str                           # 步骤名称
    action: str                         # 动作类型（read/analyze/code/run等）
    params: dict = field(default_factory=dict)  # 参数
    status: StepStatus = StepStatus.PENDING
    result: Any = None                  # 执行结果
    error: str = ""                     # 错误信息
    started_at: float = 0.0
    completed_at: float = 0.0
    retry_count: int = 0                # 重试次数
    max_retries: int = 3                # 最大重试
    
    def to_dict(self) -> dict:
        """序列化"""
        d = asdict(self)
        d["status"] = self.status.value
        return d
    
    @classmethod
    def from_dict(cls, d: dict) -> 'WorkflowStep':
        """反序列化"""
        d["status"] = StepStatus(d.get("status", "pending"))
        return cls(**d)
    
    def start(self):
        """标记开始"""
        self.status = StepStatus.RUNNING
        self.started_at = time.time()
    
    def complete(self, result: Any = None):
        """标记完成"""
        self.status = StepStatus.COMPLETED
        self.result = result
        self.completed_at = time.time()
    
    def fail(self, error: str):
        """标记失败"""
        self.status = StepStatus.FAILED
        self.error = error
        self.completed_at = time.time()
    
    def can_retry(self) -> bool:
        """是否可重试"""
        return self.retry_count < self.max_retries
    
    def retry(self):
        """重试"""
        self.retry_count += 1
        self.status = StepStatus.PENDING
        self.error = ""
        self.started_at = 0
        self.completed_at = 0
    
    def duration(self) -> float:
        """耗时"""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return 0.0
