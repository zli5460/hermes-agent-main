"""
Phoenix V8 CubeSandbox执行器
使用CubeSandbox（KVM）替代Docker，更快更安全
"""

import os
import time
import logging
from pathlib import Path
from typing import Optional, Dict
from dataclasses import dataclass

logger = logging.getLogger("phoenix.sandbox.cube")

# CubeSandbox配置
CUBE_API_URL = os.environ.get("E2B_API_URL", "http://127.0.0.1:3000")
CUBE_API_KEY = os.environ.get("E2B_API_KEY", "")
CUBE_TEMPLATE_ID = os.environ.get("CUBE_TEMPLATE_ID", "")
CUBE_TIMEOUT = 60  # 秒


@dataclass
class CubeSandboxResult:
    """CubeSandbox执行结果"""
    success: bool
    output: str
    error: str
    exit_code: int
    duration: float
    sandbox_id: str = ""


class CubeSandboxExecutor:
    """
    CubeSandbox执行器
    
    使用CubeSandbox（KVM虚拟机）执行代码，比Docker更快更安全。
    
    用法：
        executor = CubeSandboxExecutor()
        result = executor.run_code("print('hello')")
        result = executor.run_command("ls -la")
    """
    
    def __init__(self, template_id: str = None, timeout: int = CUBE_TIMEOUT):
        self._template_id = template_id or CUBE_TEMPLATE_ID
        self._timeout = timeout
        self._sandbox = None
        
        # 设置环境变量
        os.environ["E2B_API_URL"] = CUBE_API_URL
        os.environ["E2B_API_KEY"] = CUBE_API_KEY
        
    def is_available(self) -> bool:
        """检查CubeSandbox是否可用"""
        try:
            from e2b_code_interpreter import Sandbox
            return bool(self._template_id)
        except ImportError:
            return False
    
    def _ensure_sandbox(self):
        """确保沙箱已创建"""
        if self._sandbox is not None:
            return
        
        try:
            from e2b_code_interpreter import Sandbox
            self._sandbox = Sandbox.create(template=self._template_id)
            logger.info("CubeSandbox created: %s", self._sandbox.get_info().id)
        except Exception as e:
            logger.error("Failed to create CubeSandbox: %s", e)
            raise
    
    def run_code(self, code: str, language: str = "python") -> CubeSandboxResult:
        """
        执行代码
        
        Args:
            code: 要执行的代码
            language: 编程语言（python/javascript）
        
        Returns:
            CubeSandboxResult
        """
        start = time.time()
        
        try:
            self._ensure_sandbox()
            
            if language == "python":
                output = self._sandbox.run_code(code)
                duration = time.time() - start
                return CubeSandboxResult(
                    success=True,
                    output=str(output),
                    error="",
                    exit_code=0,
                    duration=duration,
                    sandbox_id=self._sandbox.get_info().id,
                )
            else:
                # 非Python代码，使用命令执行
                return self.run_command(code)
                
        except Exception as e:
            duration = time.time() - start
            return CubeSandboxResult(
                success=False,
                output="",
                error=str(e),
                exit_code=1,
                duration=duration,
            )
    
    def run_command(self, command: str) -> CubeSandboxResult:
        """
        执行命令
        
        Args:
            command: 要执行的命令
        
        Returns:
            CubeSandboxResult
        """
        start = time.time()
        
        try:
            self._ensure_sandbox()
            
            # 使用run_code执行shell命令（shlex.quote防止注入）
            import shlex
            safe_cmd = shlex.quote(command)
            code = f"import subprocess\nresult = subprocess.run({safe_cmd}, shell=True, capture_output=True, text=True)\nprint(result.stdout)\nif result.stderr:\n    print(result.stderr, file=sys.stderr)\nexit(result.returncode)"
            
            output = self._sandbox.run_code(code)
            duration = time.time() - start
            
            return CubeSandboxResult(
                success=True,
                output=str(output),
                error="",
                exit_code=0,
                duration=duration,
                sandbox_id=self._sandbox.get_info().id,
            )
            
        except Exception as e:
            duration = time.time() - start
            return CubeSandboxResult(
                success=False,
                output="",
                error=str(e),
                exit_code=1,
                duration=duration,
            )
    
    def cleanup(self):
        """清理沙箱"""
        if self._sandbox:
            try:
                self._sandbox.kill()
                logger.info("CubeSandbox killed")
            except Exception as e:
                logger.warning("Failed to kill CubeSandbox: %s", e)
            finally:
                self._sandbox = None
    
    def __del__(self):
        self.cleanup()
