"""
Phoenix V5.1 — 中间件护栏（Guardrail Middleware）

参考DeerFlow的Middleware模式，可插拔的安全检查
"""

from typing import Callable, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class GuardrailResult:
    """护栏检查结果"""
    passed: bool
    reason: str = ""
    severity: str = "info"  # info/warning/block


class GuardrailMiddleware:
    """护栏中间件"""

    def __init__(self):
        self._middlewares: list = []

    def register(self, name: str, check_fn: Callable, severity: str = "warning"):
        """注册护栏中间件"""
        self._middlewares.append({
            "name": name,
            "check_fn": check_fn,
            "severity": severity
        })

    def check(self, context: Dict[str, Any]) -> GuardrailResult:
        """执行所有护栏检查"""
        for mw in self._middlewares:
            try:
                result = mw["check_fn"](context)
                if not result:
                    return GuardrailResult(
                        passed=False,
                        reason=f"护栏 '{mw['name']}' 拦截",
                        severity=mw["severity"]
                    )
            except Exception as e:
                return GuardrailResult(
                    passed=False,
                    reason=f"护栏 '{mw['name']}' 异常: {e}",
                    severity="block"
                )

        return GuardrailResult(passed=True)

    def list_middlewares(self) -> list:
        """列出所有注册的中间件"""
        return [mw["name"] for mw in self._middlewares]


# 内置护栏
def check_no_dangerous_commands(context: Dict) -> bool:
    """检查危险命令"""
    message = context.get("message", "").lower()
    dangerous = ["rm -rf", "curl | bash", "wget | bash", "format", "fdisk"]
    return not any(d in message for d in dangerous)


def check_no_secrets_leak(context: Dict) -> bool:
    """检查密钥泄露"""
    message = context.get("message", "")
    import re
    patterns = [r"sk-[a-zA-Z0-9]{20,}", r"api_key\s*=\s*['\"][^'\"]{20,}"]
    return not any(re.search(p, message) for p in patterns)


def check_budget_limit(context: Dict) -> bool:
    """检查预算限制"""
    estimated_cost = context.get("estimated_cost", 0)
    budget = context.get("budget", 100)
    return estimated_cost <= budget
