"""
Phoenix V8 审批系统 — 三级权限矩阵
V4.7: 二元审批（safe/approval/blocked）
V4.6: 升级为P0/P1/P2三级权限（来源：主控Agent投喂手册V7）

P0: 必须请示 — 删除文件、修改SOUL.md、系统配置、付费API、无法回滚的操作
P1: 需要备案 — 修改记忆文件、创建文件、修改配置、调用API
P2: 自主执行 — 读取文件、查询命令、生成报告、发送消息
"""

import re
import logging
from typing import Optional, Tuple, Dict, List

logger = logging.getLogger("phoenix.security.approval")


class ApprovalSystem:
    """
    三级权限审批系统（V4.6升级）
    
    所有操作执行前必须先判断权限级别：
    P0: 必须请示 — 执行前必须得到用户明确授权
    P1: 需要备案 — 执行前记录，执行后汇报
    P2: 自主执行 — 执行后更新记录即可
    """
    
    # ===== P0级：必须请示（执行前必须得到用户明确授权） =====
    P0_PATTERNS = [
        r"\brm\s+-rf\b",              # 递归删除
        r"\brm\b",                     # 删除文件
        r"\brmdir\b",                  # 删除目录
        r"\bunlink\b",                 # 删除文件
        r"\bchmod\b",                  # 修改权限
        r"\bchown\b",                  # 修改所有者
        r"\bsudo\b",                   # 提权
        r"\bkill\b", r"\bpkill\b",     # 杀进程
        r"\bshutdown\b", r"\breboot\b",# 关机重启
        r"\bformat\b", r"\bmkfs\b",    # 格式化
        r"\bdd\b.*of=/dev/",           # 覆写磁盘
        r"\bgit\s+push\b.*--force",    # 强制推送
        r"\bgit\s+reset\b.*--hard",    # 硬重置
        r"\bdocker\s+rm\b",            # 删除容器
        r"\bdocker\s+kill\b",          # 杀容器
        r"\bkubectl\s+delete\b",       # 删除K8s资源
        r"\bcron",                     # 修改定时任务
        r"\bcrontab\b",                # 修改crontab
    ]
    
    # P0关键词（非命令类操作）
    P0_KEYWORDS = [
        "删除", "卸载", "移除", "清空", "重置",
        "修改系统配置", "修改环境变量", "修改网络配置",
        "付费API", "产生费用", "充值",
        "无法回滚", "不可逆",
    ]
    
    # ===== P1级：需要备案（执行前记录，执行后汇报） =====
    P1_PATTERNS = [
        r"\bmkdir\b",                  # 创建目录
        r"\bmv\b",                     # 移动/重命名
        r"\bcp\b",                     # 复制
        r"\becho\b.*>>",               # 追加写入
        r"\btee\b",                    # 写入文件
        r"\bgit\s+add\b",              # 暂存文件
        r"\bgit\s+commit\b",           # 提交
        r"\bgit\s+push\b",             # 推送（非强制）
        r"\bnpm\s+install\b",          # 安装依赖
        r"\bpip\s+install\b",          # 安装Python包
        r"\bdocker\s+run\b",           # 启动容器
        r"\bdocker\s+build\b",         # 构建镜像
        r"\bhermes\s+update\b",        # 更新Hermes
        r"\bhermes\s+config\b",        # 修改配置
    ]
    
    # P1关键词
    P1_KEYWORDS = [
        "创建", "新建", "修改配置", "修改文件",
        "安装", "部署", "发布",
        "调用API", "调用外部服务",
    ]
    
    # ===== 安全命令（P2级，自动放行） =====
    SAFE_COMMANDS = {
        "ls", "cat", "head", "tail", "grep", "rg", "find", "wc",
        "echo", "pwd", "whoami", "date", "env", "which", "file",
        "git status", "git log", "git diff", "git show", "git branch",
        "git remote", "git stash list",
        "ps", "top", "df", "du", "free", "uptime",
        "python3 --version", "node --version", "npm --version",
        "curl -s", "wget -q",
    }
    
    # 绝对禁止的命令（无论如何都拒绝）
    LETHAL_PATTERNS = [
        r"\brm\s+-rf\s+/(?:\s|$)",       # rm -rf /
        r"\brm\s+-rf\s+/\*",              # rm -rf /*
        r"\bmkfs\b", r"\bdd\s+if=.*of=/dev/",
        r":\(\)\s*\{.*\}\s*;",           # fork bomb
        r"\bchmod\s+-R\s+777\s+/",
    ]

    # P0/P1/P2描述
    LEVEL_DESCRIPTIONS = {
        "P0": "必须请示 — 删除、系统配置、付费API、无法回滚",
        "P1": "需要备案 — 修改文件、创建、安装、部署",
        "P2": "自主执行 — 读取、查询、报告、消息",
    }

    def __init__(self):
        self._p0_compiled = [re.compile(p, re.IGNORECASE) for p in self.P0_PATTERNS]
        self._p1_compiled = [re.compile(p, re.IGNORECASE) for p in self.P1_PATTERNS]
        self._lethal_patterns = [re.compile(p, re.IGNORECASE) for p in self.LETHAL_PATTERNS]
        self._auto_approve = False
        self._approval_log: List[Dict] = []  # P1备案日志
    
    def set_auto_approve(self, enabled: bool):
        """设置自动审批模式（危险，仅开发用）"""
        self._auto_approve = enabled

    def classify(self, command: str, context: Dict = None) -> str:
        """
        V4.6: 三级权限分类
        
        Returns: "P0" / "P1" / "P2"
        """
        context = context or {}
        cmd = command.strip()
        cmd_lower = cmd.lower()

        # 绝对禁止 → P0
        for p in self._lethal_patterns:
            if p.search(cmd):
                return "P0"

        # P0关键词检查
        for kw in self.P0_KEYWORDS:
            if kw in command:
                return "P0"

        # P0命令模式
        for pattern in self._p0_compiled:
            if pattern.search(cmd):
                return "P0"

        # P1关键词检查
        for kw in self.P1_KEYWORDS:
            if kw in command:
                return "P1"

        # P1命令模式
        for pattern in self._p1_compiled:
            if pattern.search(cmd):
                return "P1"

        # 上下文判定
        if context.get("cost", 0) > 1.0:
            return "P1"  # 高成本操作
        if context.get("modifies_system"):
            return "P0"

        return "P2"

    def check(self, command: str, context: Dict = None) -> Tuple[str, str]:
        """
        检查命令安全级别（兼容旧API + V4.6三级）
        
        Returns:
            (level, reason)
            level: "safe" / "approval" / "blocked" / "P0" / "P1" / "P2"
        """
        if not command or not command.strip():
            return "blocked", "空命令"

        # 绝对禁止
        for p in self._lethal_patterns:
            if p.search(command):
                return "blocked", "致命命令已拦截"

        # V4.6三级分类
        level = self.classify(command, context)
        if level == "P0":
            if self._auto_approve:
                return "safe", "auto-approve模式放行P0（开发用）"
            return "P0", self.LEVEL_DESCRIPTIONS["P0"]
        if level == "P1":
            return "P1", self.LEVEL_DESCRIPTIONS["P1"]
        
        # P2: 安全命令直接放行
        if self.is_safe(command):
            return "safe", "只读命令，自动放行"
        
        return "P2", self.LEVEL_DESCRIPTIONS["P2"]
    
    def is_safe(self, command: str) -> bool:
        """检查命令是否安全（只读）"""
        cmd = command.strip().lower()
        if re.search(r'[;&|`$]|\$\(|\|\||&&', cmd):
            return False
        if re.search(r'(?<!\S)>{1,2}(?!\S)', cmd):
            return False
        for safe in self.SAFE_COMMANDS:
            if cmd == safe or cmd.startswith(safe + " "):
                return True
        if re.match(r"^git\s+(status|log|diff|show|branch|remote|stash)\b", cmd):
            return True
        return False
    
    def is_dangerous(self, command: str) -> bool:
        """检查命令是否危险"""
        for pattern in self._p0_compiled:
            if pattern.search(command):
                return True
        return False
    
    def needs_approval(self, command: str, context: Dict = None) -> bool:
        """是否需要用户审批（兼容旧API）"""
        level, _ = self.check(command, context)
        return level in ("approval", "P0", "P1")
    
    def request_approval(self, command: str, prompt_fn=None, context: Dict = None) -> bool:
        """请求用户审批"""
        level, reason = self.check(command, context)
        if level == "safe":
            return True
        if level == "blocked":
            return False
        if self._auto_approve:
            return True
        if prompt_fn is None:
            return False
        try:
            result = bool(prompt_fn(command))
            # P1备案记录
            if level == "P1" and result:
                self._approval_log.append({
                    "command": command, "level": "P1",
                    "approved": True, "reason": reason,
                })
            return result
        except Exception:
            return False

    def log_execution(self, command: str, level: str, result: str = "success"):
        """V4.6: 执行日志（P1备案）"""
        self._approval_log.append({
            "command": command, "level": level,
            "result": result,
        })

    def get_approval_log(self) -> List[Dict]:
        """获取审批日志"""
        return self._approval_log.copy()
