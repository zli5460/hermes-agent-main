"""
不死鸟 Phoenix V8 — 第九板块：沙箱执行

核心理念：Agent在外面发指令，沙箱里面执行。
隔离、安全、可恢复。

用法：
    from phoenix.sandbox.executor import SandboxExecutor
    
    sb = SandboxExecutor()
    result = sb.run("python3 -c 'print(1+1)'")
    print(result)  # "2"
"""

from .executor import SandboxExecutor
from .manager import SandboxManager

__all__ = ["SandboxExecutor", "SandboxManager"]
