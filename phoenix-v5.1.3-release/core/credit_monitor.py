"""
Phoenix V5.1 — 信用监控系统（Credit Monitor）

完整流程：
1. 正常工作时使用三方API
2. 检测到欠费 → 通知用户 → 自动切换兜底模型
3. 用户充值后 → 确认 → 自动切回三方API
"""

import json
import time
import logging
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, Dict

logger = logging.getLogger(__name__)

STATUS_FILE = Path.home() / ".hermes" / "phoenix" / "data" / "credit_status.json"


@dataclass
class CreditStatus:
    """信用状态"""
    provider: str
    is_exhausted: bool
    last_check: float
    using_fallback: bool = False
    error_message: str = ""


class CreditMonitor:
    """信用监控器"""

    def __init__(self, config: dict):
        self.config = config.get("credit_monitor", {})
        self.enabled = self.config.get("enabled", True)
        self.auto_fallback = self.config.get("auto_fallback_to_primary", True)
        self.auto_recover = self.config.get("auto_recover_on_topup", True)
        self.primary_model = config.get("router", {}).get("primary_model", {})
        self.status_file = STATUS_FILE
        self.status_file.parent.mkdir(parents=True, exist_ok=True)
        self._status = self._load_status()

    def _load_status(self) -> CreditStatus:
        """加载状态"""
        try:
            if self.status_file.exists():
                data = json.loads(self.status_file.read_text())
                return CreditStatus(**data)
        except Exception as exc:
            _ = exc
        return CreditStatus(provider="", is_exhausted=False, last_check=0)

    def _save_status(self):
        """保存状态"""
        self.status_file.write_text(json.dumps(asdict(self._status), indent=2))

    def check_credit(self, provider: str, api_key: str, base_url: str) -> CreditStatus:
        """检查三方API信用"""
        try:
            import requests
            response = requests.get(
                f"{base_url}/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10
            )

            if response.status_code == 200:
                self._status = CreditStatus(
                    provider=provider, is_exhausted=False,
                    last_check=time.time(), using_fallback=False
                )
            elif response.status_code in [401, 402, 403]:
                self._status = CreditStatus(
                    provider=provider, is_exhausted=True,
                    last_check=time.time(), using_fallback=self._status.using_fallback,
                    error_message=f"API返回{response.status_code}"
                )
            else:
                self._status = CreditStatus(
                    provider=provider, is_exhausted=False,
                    last_check=time.time(), error_message=f"API返回{response.status_code}"
                )

            self._save_status()
            return self._status

        except Exception as e:
            self._status = CreditStatus(
                provider=provider, is_exhausted=True,
                last_check=time.time(), error_message=str(e)
            )
            self._save_status()
            return self._status

    def should_fallback(self) -> bool:
        """是否应该切换到主模型"""
        return self.auto_fallback and self._status.is_exhausted

    def get_primary_model_config(self) -> Optional[dict]:
        """获取主模型配置"""
        if not self.primary_model.get("model"):
            return None
        return {
            "provider": self.primary_model.get("provider", ""),
            "model": self.primary_model.get("model", ""),
            "api_key": self.primary_model.get("api_key", ""),
            "base_url": self.primary_model.get("base_url", ""),
        }

    def confirm_topup(self) -> str:
        """用户确认充值完成"""
        self._status.is_exhausted = False
        self._status.using_fallback = False
        self._status.error_message = ""
        self._save_status()
        return "✅ 已确认充值完成，自动切回三方API"

    def get_notification(self) -> str:
        """获取通知消息"""
        if self._status.is_exhausted and not self._status.using_fallback:
            return (
                f"⚠️ 三方API {self._status.provider} 已欠费！\n"
                f"原因: {self._status.error_message}\n"
                f"已自动切换到兜底模型（小米MiMo）继续服务。\n"
                f"请尽快充值，充值后告诉我'已充值'即可自动恢复。"
            )
        elif self._status.using_fallback:
            return "ℹ️ 当前使用兜底模型运行中..."
        return ""

    def get_status_report(self) -> str:
        """获取状态报告"""
        if self._status.using_fallback:
            return f"📊 当前状态: 使用兜底模型（{self.primary_model.get('model', 'unknown')}）"
        elif self._status.is_exhausted:
            return f"📊 当前状态: {self._status.provider} 欠费，待切换"
        else:
            return f"📊 当前状态: {self._status.provider} 正常"
