"""不死鸟 Phoenix V8 — Claude Code CLI 执行器

通过Claude Code CLI执行代码任务（读文件、写代码、跑命令）。
这是"方式2"：直接操控你电脑上的Claude Code。

与claude_executor.py（Nous Portal API）互补：
- claude_executor: API调用，适合纯文本任务
- claude_code_executor: CLI调用，适合需要读写文件、执行命令的代码任务
"""

import os
import json
import time
import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger("phoenix.executor.claude_code")


class ClaudeCodeExecutor:
    """
    Claude Code CLI 执行器

    两种调用模式：
    1. Print模式（-p）：一次性任务，返回结果后退出
    2. PTY模式：多轮交互，适合迭代开发
    """

    CLAUDE_BIN = str(Path.home() / ".local/bin/claude")

    def __init__(self):
        self._available = None

    def is_available(self) -> bool:
        """检查Claude Code CLI是否可用"""
        if self._available is not None:
            return self._available
        try:
            result = subprocess.run(
                [self.CLAUDE_BIN, "--version"],
                capture_output=True, text=True, timeout=10
            )
            self._available = result.returncode == 0
            if self._available:
                logger.info("Claude Code CLI available: %s", result.stdout.strip())
        except Exception:
            self._available = False
        return self._available

    def run_print(self, task: str, model: str = "sonnet",
                  workdir: str = None, max_turns: int = 10,
                  timeout: int = 120, allowed_tools: str = None,
                  output_format: str = "json") -> dict:
        """
        Print模式（-p）— 一次性任务

        Args:
            task: 任务描述
            model: 模型名（sonnet/opus/haiku 或完整名）
            workdir: 工作目录
            max_turns: 最大轮次
            timeout: 超时秒数
            allowed_tools: 允许的工具（逗号分隔）
            output_format: 输出格式（text/json/stream-json）

        Returns:
            {"success": bool, "output": str, "model": str, "latency": float, "cost": float}
        """
        if not self.is_available():
            return {"success": False, "output": "Claude Code CLI未安装或不可用", "model": model}

        cmd = [self.CLAUDE_BIN, "-p", task, "--model", model]
        cmd.extend(["--max-turns", str(max_turns)])
        cmd.extend(["--output-format", output_format])

        if allowed_tools:
            cmd.extend(["--allowedTools", allowed_tools])
        if workdir:
            cmd.extend(["--workdir", workdir])

        start_time = time.time()

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout,
                env={**os.environ, "CLAUDE_CODE_NO_FLICKER": "1"}
            )
            latency = time.time() - start_time

            if result.returncode == 0:
                output = result.stdout.strip()
                # 尝试解析JSON
                cost = 0.0
                if output_format == "json":
                    try:
                        data = json.loads(output)
                        output = data.get("result", output)
                        cost = data.get("total_cost_usd", 0.0)
                    except json.JSONDecodeError:
                        pass

                return {
                    "success": True,
                    "output": output,
                    "model": model,
                    "latency": latency,
                    "cost": cost,
                    "source": "claude_code_cli",
                }
            else:
                return {
                    "success": False,
                    "output": f"Claude Code退出码{result.returncode}: {result.stderr[:500]}",
                    "model": model,
                    "latency": latency,
                    "source": "claude_code_cli",
                }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "output": f"Claude Code超时（{timeout}秒）",
                "model": model,
                "latency": time.time() - start_time,
                "source": "claude_code_cli",
            }
        except Exception as e:
            return {
                "success": False,
                "output": f"Claude Code异常: {e}",
                "model": model,
                "latency": time.time() - start_time,
                "source": "claude_code_cli",
            }

    def scan_codebase(self, task: str, workdir: str = None) -> dict:
        """扫描代码库（用Read工具）"""
        return self.run_print(
            task=task,
            model="haiku",  # sonnet太贵，haiku够用
            workdir=workdir,
            max_turns=5,    # 限制轮次
            allowed_tools="Read",  # 只读，不执行
            timeout=60,
        )

    def write_code(self, task: str, workdir: str = None, model: str = "sonnet") -> dict:
        """写代码（用Read+Edit+Write+Bash）"""
        return self.run_print(
            task=task,
            model=model,
            workdir=workdir,
            max_turns=10,   # 从15降到10
            allowed_tools="Read,Edit,Write,Bash",
            timeout=120,    # 从180降到120
        )

    def review_code(self, task: str, workdir: str = None) -> dict:
        """代码审查（只读）"""
        return self.run_print(
            task=task,
            model="sonnet",  # opus太贵，sonnet够
            workdir=workdir,
            max_turns=3,    # 从5降到3
            allowed_tools="Read",
            timeout=60,
        )


# 全局单例
claude_code_executor = ClaudeCodeExecutor()
