"""
Phoenix V5.1 真神模式（God Mode）
重大任务的用户确认机制

功能：
1. 检测重大任务
2. 显示详细预估
3. 等待用户确认
4. 记录使用情况
"""

from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class GodModeRequest:
    """真神模式请求"""
    task_description: str
    model: str
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_cost: float
    estimated_time_minutes: int
    reason: str


class GodMode:
    """真神模式管理器"""

    # 触发阈值
    COST_THRESHOLD = 5.0  # $5 以上触发
    COMPLEXITY_THRESHOLD = 8  # 复杂度 8/10 以上触发

    def __init__(self, cost_monitor):
        self.cost_monitor = cost_monitor

    def should_trigger(self, estimated_cost: float, complexity_score: float = 0) -> bool:
        """判断是否应该触发真神模式"""
        if estimated_cost >= self.COST_THRESHOLD:
            return True
        if complexity_score >= self.COMPLEXITY_THRESHOLD:
            return True
        return False

    def format_request(self, request: GodModeRequest) -> str:
        """格式化真神模式请求"""
        # 获取当前成本统计
        summary = self.cost_monitor.get_summary()
        monthly_cost = summary['monthly']['cost']
        monthly_limit = summary['monthly']['limit']
        remaining = monthly_limit - monthly_cost

        # 计算百分比
        percentage = (request.estimated_cost / monthly_limit) * 100

        msg = f"""
┌─────────────────────────────────────────────────────┐
│ 🔥 真神模式                                          │
├─────────────────────────────────────────────────────┤
│                                                     │
│ 任务：{request.task_description[:40]}{'...' if len(request.task_description) > 40 else ''}
│ 模型：{request.model}
│                                                     │
│ 预估信息：                                           │
│ • Token：~{request.estimated_input_tokens + request.estimated_output_tokens:,}
│   （输入 {request.estimated_input_tokens:,} + 输出 {request.estimated_output_tokens:,}）
│ • 成本：${request.estimated_cost:.2f}
│ • 时间：~{request.estimated_time_minutes} 分钟
│                                                     │
│ 成本影响：                                           │
│ • 本次消耗：${request.estimated_cost:.2f}（{percentage:.1f}% 月预算）
│ • 本月已用：${monthly_cost:.2f} / ${monthly_limit:.2f}
│ • 剩余预算：${remaining:.2f}
│                                                     │
│ 原因：{request.reason[:40]}{'...' if len(request.reason) > 40 else ''}
│                                                     │
├─────────────────────────────────────────────────────┤
│ ⚠️  这是一个重大任务，将消耗较多成本                   │
│                                                     │
│ 请确认是否继续：                                      │
│ • [确认] - 开启真神模式执行                           │
│ • [降级] - 使用便宜模型（可能质量下降）                │
│ • [取消] - 取消任务                                  │
└─────────────────────────────────────────────────────┘
"""
        return msg.strip()

    def request_approval(self, request: GodModeRequest, prompt_fn=None) -> str:
        """请求用户批准

        Returns:
            "approved" - 用户确认
            "downgrade" - 降级到便宜模型
            "cancelled" - 取消任务
        """
        # 显示请求
        message = self.format_request(request)
        logger.info(f"\n{message}\n")

        # 如果没有提供回调，默认拒绝
        if prompt_fn is None:
            logger.warning("无用户确认回调，默认取消真神模式")
            return "cancelled"

        try:
            # 调用用户确认回调
            result = prompt_fn(message)
            if result in ["approved", "downgrade", "cancelled"]:
                return result
            else:
                return "cancelled"
        except Exception as e:
            logger.error(f"用户确认异常: {e}")
            return "cancelled"

    def get_downgrade_model(self, original_model: str) -> str:
        """获取降级模型"""
        downgrade_map = {
            "anthropic/claude-opus-4.7": "anthropic/claude-sonnet-4.6",
            "anthropic/claude-sonnet-4.6": "openai/gpt-5.4-mini",
            "openai/gpt-5.5": "openai/gpt-5.4-mini",
        }
        return downgrade_map.get(original_model, "xiaomi/mimo-v2-pro")
