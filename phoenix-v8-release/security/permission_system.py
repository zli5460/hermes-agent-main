"""不死鸟 Phoenix V8 — 多级权限系统
来源: OpenHarness

细粒度的权限控制，比SafeToAutoRun更精细。
"""

from enum import Enum
from typing import Dict, List, Optional

class PermissionLevel(Enum):
    AUTO = "auto"          # 自动执行
    SOFT_CONFIRM = "soft"  # 软确认（显示提示）
    HARD_CONFIRM = "hard"  # 硬确认（必须用户确认）
    BLOCKED = "blocked"    # 禁止执行

class PermissionRule:
    """单条权限规则"""
    def __init__(self, pattern: str, level: PermissionLevel, description: str = ""):
        self.pattern = pattern
        self.level = level
        self.description = description

class PermissionSystem:
    """多级权限系统"""
    
    # 默认规则
    DEFAULT_RULES = [
        PermissionRule("read|cat|head|tail|ls|find", PermissionLevel.AUTO, "只读操作"),
        PermissionRule("grep|wc|sort|uniq|diff", PermissionLevel.AUTO, "文本处理"),
        PermissionRule("echo|printf|date|pwd|whoami", PermissionLevel.AUTO, "系统信息"),
        PermissionRule("git status|git log|git diff", PermissionLevel.AUTO, "Git只读"),
        PermissionRule("git add|git commit|git push", PermissionLevel.SOFT_CONFIRM, "Git写操作"),
        PermissionRule("pip install|npm install", PermissionLevel.SOFT_CONFIRM, "安装包"),
        PermissionRule("rm|rmdir|unlink", PermissionLevel.HARD_CONFIRM, "删除操作"),
        PermissionRule("sudo|su", PermissionLevel.BLOCKED, "权限提升"),
        PermissionRule("chmod 777|chown", PermissionLevel.HARD_CONFIRM, "权限修改"),
        PermissionRule("curl.*POST|wget.*POST", PermissionLevel.SOFT_CONFIRM, "网络写入"),
        PermissionRule("docker rm|docker kill", PermissionLevel.HARD_CONFIRM, "容器操作"),
    ]
    
    def __init__(self):
        self._rules = self.DEFAULT_RULES.copy()
    
    def check(self, command: str) -> Dict:
        """检查命令权限"""
        for rule in self._rules:
            if __import__("re").search(rule.pattern, command, __import__("re").IGNORECASE):
                return {
                    "allowed": rule.level in (PermissionLevel.AUTO, PermissionLevel.SOFT_CONFIRM),
                    "level": rule.level.value,
                    "description": rule.description,
                    "needs_confirm": rule.level == PermissionLevel.HARD_CONFIRM,
                    "blocked": rule.level == PermissionLevel.BLOCKED,
                }
        
        # 默认：软确认
        return {
            "allowed": True,
            "level": "soft",
            "description": "未知操作，默认软确认",
            "needs_confirm": True,
            "blocked": False,
        }
    
    def add_rule(self, pattern: str, level: PermissionLevel, description: str = ""):
        """添加规则"""
        self._rules.append(PermissionRule(pattern, level, description))
    
    def get_rules(self) -> List[Dict]:
        """获取所有规则"""
        return [{"pattern": r.pattern, "level": r.level.value, "description": r.description} 
                for r in self._rules]

permission_system = PermissionSystem()
