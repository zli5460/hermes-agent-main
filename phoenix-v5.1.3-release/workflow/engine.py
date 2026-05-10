"""
Phoenix 持久化工作流引擎

任务可暂停、可恢复、可追踪。
状态自动持久化到JSON，崩溃后可恢复。
"""

import json
import time
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field, asdict

from .step import WorkflowStep, StepStatus

logger = logging.getLogger("phoenix.workflow")

WORKFLOW_DATA = Path.home() / ".hermes" / "phoenix" / "data" / "workflows"


@dataclass
class Workflow:
    """工作流"""
    id: str
    name: str
    steps: List[WorkflowStep] = field(default_factory=list)
    status: str = "created"       # created/running/paused/completed/failed
    created_at: float = 0.0
    started_at: float = 0.0
    completed_at: float = 0.0
    current_step: int = 0         # 当前执行到第几步
    result: Any = None
    error: str = ""
    metadata: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        d = asdict(self)
        d["steps"] = [s.to_dict() for s in self.steps]
        return d
    
    @classmethod
    def from_dict(cls, d: dict) -> 'Workflow':
        d["steps"] = [WorkflowStep.from_dict(s) for s in d.get("steps", [])]
        return cls(**d)
    
    def progress(self) -> float:
        """进度百分比"""
        if not self.steps:
            return 0.0
        done = sum(1 for s in self.steps if s.status == StepStatus.COMPLETED)
        return done / len(self.steps) * 100
    
    def duration(self) -> float:
        """总耗时"""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        elif self.started_at:
            return time.time() - self.started_at
        return 0.0


class WorkflowEngine:
    """
    持久化工作流引擎
    
    用法：
        engine = WorkflowEngine()
        
        # 创建
        wf = engine.create("代码审查", steps=[
            {"name": "读取代码", "action": "read"},
            {"name": "分析问题", "action": "analyze"},
            {"name": "生成报告", "action": "report"},
        ])
        
        # 注册执行器
        engine.register("read", lambda step: open(step.params.get("file","")).read())
        engine.register("analyze", lambda step: "发现3个问题")
        engine.register("report", lambda step: "报告已生成")
        
        # 执行
        engine.run(wf.id)
        
        # 暂停/恢复
        engine.pause(wf.id)
        engine.resume(wf.id)
    """
    
    def __init__(self):
        WORKFLOW_DATA.mkdir(parents=True, exist_ok=True)
        self._workflows: Dict[str, Workflow] = {}
        self._executors: Dict[str, Callable] = {}
        self._load_all()
    
    def _load_all(self):
        """加载所有工作流"""
        for f in WORKFLOW_DATA.glob("*.json"):
            try:
                wf = Workflow.from_dict(json.loads(f.read_text()))
                self._workflows[wf.id] = wf
            except Exception as exc:
                _ = exc
    
    def _save(self, wf: Workflow):
        """持久化工作流"""
        path = WORKFLOW_DATA / f"{wf.id}.json"
        path.write_text(json.dumps(wf.to_dict(), indent=2, ensure_ascii=False))
        self._workflows[wf.id] = wf
    
    def register(self, action: str, executor: Callable):
        """注册步骤执行器"""
        self._executors[action] = executor
    
    def create(self, name: str, steps: List[dict], 
               metadata: dict = None) -> Workflow:
        """创建工作流"""
        wf_id = f"wf-{int(time.time())}"
        wf_steps = [WorkflowStep(**s) for s in steps]
        
        wf = Workflow(
            id=wf_id,
            name=name,
            steps=wf_steps,
            status="created",
            created_at=time.time(),
            metadata=metadata or {},
        )
        
        self._save(wf)
        logger.info("Workflow created: %s (%d steps)", name, len(steps))
        return wf
    
    def run(self, workflow_id: str) -> Workflow:
        """
        执行工作流
        
        从当前步骤开始（支持断点恢复）
        """
        wf = self._workflows.get(workflow_id)
        if not wf:
            raise ValueError(f"Workflow not found: {workflow_id}")
        
        wf.status = "running"
        if not wf.started_at:
            wf.started_at = time.time()
        
        self._save(wf)
        
        # FIX: 用while循环支持真正的重试（for循环里i-=1无效）
        i = wf.current_step
        while i < len(wf.steps):
            step = wf.steps[i]
            
            if step.status == StepStatus.COMPLETED:
                i += 1
                continue
            
            wf.current_step = i
            self._save(wf)
            
            # 执行步骤
            step.start()
            self._save(wf)
            
            executor = self._executors.get(step.action)
            if not executor:
                step.fail(f"未注册的action: {step.action}")
                wf.status = "failed"
                wf.error = f"步骤 '{step.name}' 失败: 未注册的action"
                wf.completed_at = time.time()
                self._save(wf)
                return wf
            
            try:
                result = executor(step)
                step.complete(result)
                logger.info("Step completed: %s", step.name)
                self._save(wf)
                i += 1  # 成功，前进
            except Exception as e:
                step.fail(str(e))
                logger.warning("Step failed: %s - %s", step.name, e)
                
                # 可重试 — 不推进i，下次循环重跑同一步
                if step.can_retry():
                    step.retry()
                    self._save(wf)
                    logger.info("Retrying step: %s (attempt %d)", 
                                step.name, getattr(step, 'retry_count', 0))
                    continue  # while循环继续，i不变 → 重试当前步
                
                wf.status = "failed"
                wf.error = f"步骤 '{step.name}' 失败: {e}"
                wf.completed_at = time.time()
                self._save(wf)
                return wf
            
            self._save(wf)
        
        # 全部完成
        wf.status = "completed"
        wf.completed_at = time.time()
        wf.current_step = len(wf.steps)
        self._save(wf)
        
        logger.info("Workflow completed: %s (%.1fs)", wf.name, wf.duration())
        return wf
    
    def pause(self, workflow_id: str) -> bool:
        """暂停工作流"""
        wf = self._workflows.get(workflow_id)
        if not wf or wf.status != "running":
            return False
        
        wf.status = "paused"
        self._save(wf)
        logger.info("Workflow paused: %s at step %d", wf.name, wf.current_step)
        return True
    
    def resume(self, workflow_id: str) -> Optional[Workflow]:
        """恢复工作流（从暂停处继续）"""
        wf = self._workflows.get(workflow_id)
        if not wf or wf.status != "paused":
            return None
        
        return self.run(workflow_id)
    
    def get(self, workflow_id: str) -> Optional[Workflow]:
        """获取工作流"""
        return self._workflows.get(workflow_id)
    
    def list_all(self) -> List[Workflow]:
        """列出所有工作流"""
        return sorted(self._workflows.values(), key=lambda w: w.created_at, reverse=True)
    
    def list_active(self) -> List[Workflow]:
        """列出活跃工作流"""
        return [w for w in self._workflows.values() if w.status in ("created", "running", "paused")]
    
    def cleanup(self, max_age_days: int = 30):
        """清理过期工作流"""
        cutoff = time.time() - (max_age_days * 86400)
        to_remove = []
        
        for wf_id, wf in self._workflows.items():
            if wf.status in ("completed", "failed") and wf.created_at < cutoff:
                to_remove.append(wf_id)
        
        for wf_id in to_remove:
            del self._workflows[wf_id]
            path = WORKFLOW_DATA / f"{wf_id}.json"
            if path.exists():
                path.unlink()
        
        if to_remove:
            logger.info("Cleaned up %d expired workflows", len(to_remove))
