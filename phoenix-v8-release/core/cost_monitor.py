"""
Phoenix V8 成本监控系统（Cost Monitor）

核心功能：
1. 实时监控 token 消耗
2. 超限自动暂停
3. 透明的成本控制
4. 避免失控
"""

import time
import json
import threading
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class CostRecord:
    """成本记录"""
    timestamp: float
    model: str
    tokens: int
    cost: float
    task_type: str
    session_id: str


class CostLimitExceeded(Exception):
    """成本超限异常"""
    pass


class CostMonitor:
    """成本监控器"""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.cost_file = data_dir / "cost_monitor.json"

        # 限额配置
        self.session_limit = 5.0   # 单次会话上限 $5
        self.daily_limit = 20.0    # 每日上限 $20
        self.monthly_limit = 100.0 # 每月上限 $100

        # 当前统计
        self.session_cost = 0.0
        self.session_tokens = 0
        self.session_start = time.time()

        # 线程安全
        self._lock = threading.Lock()

        # 加载历史数据
        self._load_history()

    def _load_history(self):
        """加载历史成本数据"""
        if not self.cost_file.exists():
            self.history = []
            return

        try:
            with open(self.cost_file, 'r', encoding='utf-8') as f:
                self.history = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load cost history: {e}")
            self.history = []

    def _save_history(self):
        """保存历史数据"""
        try:
            with open(self.cost_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save cost history: {e}")

    def check_before_call(self, estimated_tokens: int, estimated_cost: float, model: str) -> bool:
        """调用前检查（返回 True 表示可以执行）"""
        # 检查会话限额
        if self.session_cost + estimated_cost > self.session_limit:
            raise CostLimitExceeded(
                f"⚠️ 会话成本将超限！\n"
                f"当前: ${self.session_cost:.2f}\n"
                f"预估: +${estimated_cost:.2f}\n"
                f"限额: ${self.session_limit:.2f}\n"
                f"建议: 开启新会话或提高限额"
            )

        # 检查每日限额
        daily_cost = self._get_daily_cost()
        if daily_cost + estimated_cost > self.daily_limit:
            raise CostLimitExceeded(
                f"⚠️ 每日成本将超限！\n"
                f"今日已用: ${daily_cost:.2f}\n"
                f"预估: +${estimated_cost:.2f}\n"
                f"限额: ${self.daily_limit:.2f}\n"
                f"建议: 明天再试或提高限额"
            )

        # 检查每月限额
        monthly_cost = self._get_monthly_cost()
        if monthly_cost + estimated_cost > self.monthly_limit:
            raise CostLimitExceeded(
                f"⚠️ 每月成本将超限！\n"
                f"本月已用: ${monthly_cost:.2f}\n"
                f"预估: +${estimated_cost:.2f}\n"
                f"限额: ${self.monthly_limit:.2f}\n"
                f"建议: 下月再试或提高限额"
            )

        # 超过 80% 发出警告
        if self.session_cost + estimated_cost > self.session_limit * 0.8:
            logger.warning(
                f"⚠️ 会话成本已达 {(self.session_cost + estimated_cost)/self.session_limit*100:.0f}%"
            )

        return True

    def record_call(self, model: str, tokens: int, cost: float, task_type: str = "unknown"):
        """记录实际成本"""
        with self._lock:
            self.session_cost += cost
            self.session_tokens += tokens

            # 记录到历史
            record = CostRecord(
                timestamp=time.time(),
                model=model,
                tokens=tokens,
                cost=cost,
                task_type=task_type,
                session_id=self._get_session_id(),
            )
            self.history.append(asdict(record))

            # 定期保存（每10条记录保存一次）
            if len(self.history) % 10 == 0:
                self._save_history()

            logger.info(
                f"💰 成本记录: {model} | {tokens} tokens | ${cost:.4f} | "
                f"会话累计: ${self.session_cost:.2f}"
            )

    def _get_session_id(self) -> str:
        """获取会话 ID"""
        return f"session_{int(self.session_start)}"

    def _get_daily_cost(self) -> float:
        """获取今日成本"""
        today_start = time.time() - 86400  # 24小时前
        return sum(
            r["cost"] for r in self.history
            if r["timestamp"] > today_start
        )

    def _get_monthly_cost(self) -> float:
        """获取本月成本"""
        month_start = time.time() - 2592000  # 30天前
        return sum(
            r["cost"] for r in self.history
            if r["timestamp"] > month_start
        )

    def get_summary(self) -> Dict:
        """获取成本摘要"""
        return {
            "session": {
                "cost": self.session_cost,
                "tokens": self.session_tokens,
                "limit": self.session_limit,
                "usage_percent": (self.session_cost / self.session_limit * 100),
            },
            "daily": {
                "cost": self._get_daily_cost(),
                "limit": self.daily_limit,
                "usage_percent": (self._get_daily_cost() / self.daily_limit * 100),
            },
            "monthly": {
                "cost": self._get_monthly_cost(),
                "limit": self.monthly_limit,
                "usage_percent": (self._get_monthly_cost() / self.monthly_limit * 100),
            },
        }

    def reset_session(self):
        """重置会话统计"""
        self.session_cost = 0.0
        self.session_tokens = 0
        self.session_start = time.time()
        logger.info("✅ 会话成本统计已重置")
