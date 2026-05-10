"""
Phoenix 沙箱执行器

在Docker容器内执行代码，隔离安全。
Agent在外面发指令，沙箱里面执行。
"""

import os
import json
import time
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Dict
from dataclasses import dataclass

logger = logging.getLogger("phoenix.sandbox")

# 沙箱基础镜像
SANDBOX_IMAGE = "python:3.12-slim"
SANDBOX_NAME = "phoenix-sandbox"
SANDBOX_TIMEOUT = 60  # 秒


@dataclass
class SandboxResult:
    """沙箱执行结果"""
    success: bool
    output: str
    error: str
    exit_code: int
    duration: float
    container_id: str = ""


class SandboxExecutor:
    """
    沙箱执行器
    
    在Docker容器内执行命令，隔离用户真实环境。
    
    用法：
        sb = SandboxExecutor()
        result = sb.run("print('hello')")
        result = sb.run_code("def add(a,b): return a+b\nprint(add(1,2))")
        result = sb.run_file("/path/to/script.py")
    """
    
    def __init__(self, image: str = SANDBOX_IMAGE, timeout: int = SANDBOX_TIMEOUT):
        self._image = image
        self._timeout = timeout
        self._container_id = None
        self._ensure_image()
    
    def _ensure_image(self):
        """确保沙箱镜像存在"""
        try:
            result = subprocess.run(
                ["docker", "image", "inspect", self._image],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                logger.info("Pulling sandbox image: %s", self._image)
                subprocess.run(
                    ["docker", "pull", self._image],
                    capture_output=True, text=True, timeout=120
                )
        except Exception as e:
            logger.warning("Failed to ensure sandbox image: %s", e)
    
    def run(self, command: str, timeout: Optional[int] = None) -> SandboxResult:
        """
        在沙箱内执行shell命令
        
        Args:
            command: 要执行的命令
            timeout: 超时秒数
        
        Returns:
            SandboxResult
        """
        timeout = timeout or self._timeout
        start = time.time()
        
        try:
            result = subprocess.run(
                [
                    "docker", "run", "--rm",
                    "--network", "none",  # 无网络，安全
                    "--memory", "256m",   # 内存限制
                    "--cpus", "0.5",      # CPU限制
                    "--read-only",        # 只读文件系统
                    "--tmpfs", "/tmp:size=10m",  # 临时目录
                    self._image,
                    "sh", "-c", command
                ],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            duration = time.time() - start
            
            return SandboxResult(
                success=result.returncode == 0,
                output=result.stdout,
                error=result.stderr,
                exit_code=result.returncode,
                duration=duration,
            )
        
        except subprocess.TimeoutExpired:
            return SandboxResult(
                success=False,
                output="",
                error=f"执行超时（{timeout}秒）",
                exit_code=-1,
                duration=time.time() - start,
            )
        except Exception as e:
            return SandboxResult(
                success=False,
                output="",
                error=str(e),
                exit_code=-1,
                duration=time.time() - start,
            )
    
    def run_code(self, code: str, language: str = "python") -> SandboxResult:
        """
        在沙箱内执行代码
        
        Args:
            code: 代码字符串
            language: 语言（python/bash）
        """
        if language == "python":
            return self.run(f"python3 -c {repr(code)}")
        elif language == "bash":
            return self.run(code)
        else:
            return SandboxResult(
                success=False,
                output="",
                error=f"不支持的语言: {language}",
                exit_code=-1,
                duration=0,
            )
    
    def run_file(self, file_path: str, timeout: Optional[int] = None) -> SandboxResult:
        """
        在沙箱内执行文件
        
        先把文件复制到沙箱，再执行。
        """
        path = Path(file_path)
        if not path.exists():
            return SandboxResult(
                success=False,
                output="",
                error=f"文件不存在: {file_path}",
                exit_code=-1,
                duration=0,
            )
        
        # 读取文件内容
        code = path.read_text(errors="ignore")
        
        # 根据扩展名选择语言
        ext = path.suffix.lower()
        if ext == ".py":
            return self.run_code(code, "python")
        elif ext in (".sh", ".bash"):
            return self.run_code(code, "bash")
        else:
            return self.run(f"cat << 'HEREDOC'\n{code}\nHEREDOC")
    
    def run_with_volume(self, command: str, host_path: str, 
                        container_path: str = "/data") -> SandboxResult:
        """
        挂载目录后执行命令
        
        用于需要读取宿主机文件的场景。
        """
        try:
            result = subprocess.run(
                [
                    "docker", "run", "--rm",
                    "--network", "none",
                    "--memory", "256m",
                    "-v", f"{host_path}:{container_path}:ro",  # 只读挂载
                    self._image,
                    "sh", "-c", command
                ],
                capture_output=True,
                text=True,
                timeout=self._timeout
            )
            
            return SandboxResult(
                success=result.returncode == 0,
                output=result.stdout,
                error=result.stderr,
                exit_code=result.returncode,
                duration=0,
            )
        except Exception as e:
            return SandboxResult(
                success=False,
                output="",
                error=str(e),
                exit_code=-1,
                duration=0,
            )
    
    def is_available(self) -> bool:
        """检查沙箱是否可用"""
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True, text=True, timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False
