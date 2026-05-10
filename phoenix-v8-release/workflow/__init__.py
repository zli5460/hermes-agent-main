"""
不死鸟 Phoenix — 第十板块：持久化工作流

任务可暂停、可恢复、可追踪。
崩溃后自动恢复，不丢进度。

用法：
    from phoenix.workflow.engine import WorkflowEngine
    
    engine = WorkflowEngine()
    
    # 创建工作流
    wf = engine.create("代码审查", steps=[
        {"name": "读取代码", "action": "read", "params": {"file": "main.py"}},
        {"name": "分析问题", "action": "analyze", "params": {}},
        {"name": "生成报告", "action": "report", "params": {}},
    ])
    
    # 执行（支持暂停/恢复）
    engine.run(wf.id)
"""

from .engine import WorkflowEngine
from .step import WorkflowStep, StepStatus

__all__ = ["WorkflowEngine", "WorkflowStep", "StepStatus"]
