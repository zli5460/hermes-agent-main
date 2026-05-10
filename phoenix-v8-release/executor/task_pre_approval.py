"""
Phoenix V8 任务预审系统（Task Pre-Approval System）

核心功能：
1. 评估任务复杂度和成本
2. 生成执行方案
3. 提交给用户确认
4. 避免失控（$60 悲剧）
"""

import re
from dataclasses import dataclass
from typing import List, Dict, Optional


@dataclass
class TaskEstimate:
    """任务预估结果"""
    task_description: str
    subtasks: List[str]
    estimated_tokens: int
    estimated_cost: float
    estimated_time_minutes: int
    complexity: str  # simple/medium/complex
    needs_approval: bool
    reason: str


class TaskPreApprovalSystem:
    """任务预审系统"""

    # 成本阈值（超过此值需要用户确认）
    APPROVAL_THRESHOLD_COST = 0.5  # $0.5
    APPROVAL_THRESHOLD_TOKENS = 10000  # 10k tokens

    # Token 成本估算（每1k tokens）
    TOKEN_COSTS = {
        "xiaomi/mimo-v2.5": 0.0001,
        "anthropic/claude-sonnet-4.6": 0.003,
        "anthropic/claude-opus-4.7": 0.015,
    }

    def evaluate_task(self, message: str, task_type: str, model: str) -> TaskEstimate:
        """评估任务并生成预估"""

        # 1. 判断是否需要分解
        needs_decompose = self._needs_decomposition(message)

        if not needs_decompose:
            # 简单任务，直接估算
            return self._estimate_simple_task(message, task_type, model)
        else:
            # 复杂任务，分解后估算
            return self._estimate_complex_task(message, task_type, model)

    def _needs_decomposition(self, message: str) -> bool:
        """判断是否需要分解"""
        # 检查分解信号
        decompose_signals = [
            r"(?<!\w)\+(?!\w)",  # +
            r"(?<!\w)和(?!\w)",  # 和
            r"以及",
            r"分别",
            r"同时",
            r"、",
            r"，",
        ]

        for signal in decompose_signals:
            if re.search(signal, message):
                return True

        return False

    def _estimate_simple_task(self, message: str, task_type: str, model: str) -> TaskEstimate:
        """估算简单任务"""
        # 基于任务类型估算 token 消耗
        token_estimates = {
            "chat": 500,
            "code_small": 2000,
            "code_medium": 8000,
            "code_large": 20000,
            "reasoning": 15000,
            "vision": 3000,
        }

        estimated_tokens = token_estimates.get(task_type, 2000)
        token_cost = self.TOKEN_COSTS.get(model, 0.001)
        estimated_cost = (estimated_tokens / 1000) * token_cost

        # 估算时间（分钟）
        time_estimates = {
            "chat": 0.5,
            "code_small": 1,
            "code_medium": 3,
            "code_large": 8,
            "reasoning": 5,
            "vision": 2,
        }
        estimated_time = time_estimates.get(task_type, 2)

        needs_approval = (
            estimated_cost > self.APPROVAL_THRESHOLD_COST or
            estimated_tokens > self.APPROVAL_THRESHOLD_TOKENS
        )

        return TaskEstimate(
            task_description=message,
            subtasks=[message],
            estimated_tokens=estimated_tokens,
            estimated_cost=estimated_cost,
            estimated_time_minutes=estimated_time,
            complexity="simple" if not needs_approval else "medium",
            needs_approval=needs_approval,
            reason="单一任务" if not needs_approval else "任务较复杂，建议确认后执行",
        )

    def _estimate_complex_task(self, message: str, task_type: str, model: str) -> TaskEstimate:
        """估算复杂任务（需要分解）"""
        # 分解任务
        subtasks = self._decompose_message(message)

        # 估算每个子任务的成本
        total_tokens = 0
        total_cost = 0.0
        total_time = 0

        for subtask in subtasks:
            # 简化估算：每个子任务按 code_medium 计算
            tokens = 8000
            cost = (tokens / 1000) * self.TOKEN_COSTS.get(model, 0.003)
            time = 3

            total_tokens += tokens
            total_cost += cost
            total_time += time

        # 复杂任务必须审批
        needs_approval = True

        return TaskEstimate(
            task_description=message,
            subtasks=subtasks,
            estimated_tokens=total_tokens,
            estimated_cost=total_cost,
            estimated_time_minutes=total_time,
            complexity="complex",
            needs_approval=needs_approval,
            reason=f"任务需要分解为 {len(subtasks)} 个子任务，建议确认后执行",
        )

    def _decompose_message(self, message: str) -> List[str]:
        """分解消息为子任务"""
        # 按分隔符切分
        parts = re.split(r'\s*(?:\+|和|以及|、|，|；)\s*', message)
        # 过滤空白和太短的部分
        subtasks = [p.strip() for p in parts if p.strip() and len(p.strip()) > 3]
        return subtasks if len(subtasks) > 1 else [message]

    def format_approval_message(self, estimate: TaskEstimate) -> str:
        """格式化审批消息"""
        if not estimate.needs_approval:
            return None

        msg = f"""
📋 **执行方案预览**

**任务**: {estimate.task_description}

**分解**: {len(estimate.subtasks)} 个子任务
"""

        if len(estimate.subtasks) > 1:
            for i, subtask in enumerate(estimate.subtasks, 1):
                msg += f"  {i}. {subtask}\n"

        msg += f"""
**预估 Token**: ~{estimate.estimated_tokens:,}
**预估成本**: ~${estimate.estimated_cost:.2f}
**预估时间**: ~{estimate.estimated_time_minutes} 分钟

**复杂度**: {estimate.complexity}
**原因**: {estimate.reason}

---

⚠️ **请确认是否执行此任务？**

回复 "确认" 或 "执行" 开始执行
回复 "取消" 或 "不执行" 取消任务
"""
        return msg.strip()
