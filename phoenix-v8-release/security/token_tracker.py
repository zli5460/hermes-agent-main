"""不死鸟 Phoenix V8 — Token成本追踪
来源: OpenHarness

实时追踪Token消耗和成本。
"""

import json
import time
from pathlib import Path
from typing import Dict, Optional

class TokenTracker:
    """Token成本追踪器"""
    
    # 模型价格（每1K token，美元）
    PRICING = {
        "mimo-v2-flash": {"input": 0.0001, "output": 0.0002},
        "mimo-v2.5": {"input": 0.0003, "output": 0.0006},
        "mimo-v2-pro": {"input": 0.001, "output": 0.002},
        "claude-sonnet-4.6": {"input": 0.003, "output": 0.015},
        "claude-opus-4.7": {"input": 0.015, "output": 0.075},
        "gpt-5.4-mini": {"input": 0.00015, "output": 0.0006},
        "gpt-5.5": {"input": 0.01, "output": 0.03},
        "gemini-3-flash": {"input": 0.000075, "output": 0.0003},
        "gemini-2.5-pro": {"input": 0.00125, "output": 0.01},
    }
    
    def __init__(self):
        self._data_dir = Path.home() / ".hermes" / "phoenix" / "data"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._data_file = self._data_dir / "token_tracker.json"
        self._session_tokens = 0
        self._session_cost = 0.0
        self._daily_tokens = 0
        self._daily_cost = 0.0
        self._load_data()
    
    def record(self, model: str, input_tokens: int, output_tokens: int) -> Dict:
        """记录Token使用"""
        pricing = self.PRICING.get(model, {"input": 0.001, "output": 0.003})

        cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1000

        self._session_tokens += input_tokens + output_tokens
        self._session_cost += cost
        self._daily_tokens += input_tokens + output_tokens
        self._daily_cost += cost

        self._save_data()

        return {
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost, 6),
            "session_total": self._session_tokens,
            "daily_total": self._daily_tokens,
        }
    
    def get_session_stats(self) -> Dict:
        """获取会话统计"""
        return {
            "tokens": self._session_tokens,
            "cost_usd": round(self._session_cost, 4),
        }
    
    def get_daily_stats(self) -> Dict:
        """获取每日统计"""
        return {
            "tokens": self._daily_tokens,
            "cost_usd": round(self._daily_cost, 4),
        }
    
    def get_model_breakdown(self) -> Dict:
        """按模型分类统计"""
        # 简化版，实际可以更详细
        return {
            "session_tokens": self._session_tokens,
            "session_cost": round(self._session_cost, 4),
            "daily_tokens": self._daily_tokens,
            "daily_cost": round(self._daily_cost, 4),
        }

    def _load_data(self):
        """从磁盘加载数据"""
        if not self._data_file.exists():
            return
        try:
            data = json.loads(self._data_file.read_text())
            self._daily_tokens = data.get("daily_tokens", 0)
            self._daily_cost = data.get("daily_cost", 0.0)
            # 检查日期是否是今天
            last_date = data.get("last_date", "")
            today = time.strftime("%Y-%m-%d")
            if last_date != today:
                # 新的一天，重置每日统计
                self._daily_tokens = 0
                self._daily_cost = 0.0
        except Exception as exc:
            _ = exc

    def _save_data(self):
        """保存数据到磁盘"""
        try:
            data = {
                "daily_tokens": self._daily_tokens,
                "daily_cost": self._daily_cost,
                "last_date": time.strftime("%Y-%m-%d"),
            }
            self._data_file.write_text(json.dumps(data, indent=2))
        except Exception as exc:
            _ = exc

token_tracker = TokenTracker()
