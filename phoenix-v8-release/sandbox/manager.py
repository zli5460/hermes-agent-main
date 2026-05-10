"""
Phoenix 沙箱管理器

管理沙箱的生命周期：创建、暂停、恢复、销毁。
支持快照和恢复，任务可中断后继续。
"""

import json
import time
import logging
import subprocess
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass, asdict

logger = logging.getLogger("phoenix.sandbox.manager")

SANDBOX_DATA = Path.home() / ".hermes" / "phoenix" / "data" / "sandboxes"


@dataclass
class SandboxState:
    """沙箱状态"""
    id: str
    name: str
    status: str  # running/paused/stopped
    created_at: float
    image: str
    container_id: str = ""
    snapshot_id: str = ""
    tasks: List[dict] = None
    
    def __post_init__(self):
        if self.tasks is None:
            self.tasks = []


class SandboxManager:
    """
    沙箱管理器
    
    用法：
        manager = SandboxManager()
        
        # 创建沙箱
        sb = manager.create("code-review")
        
        # 执行任务
        result = sb.run("python3 script.py")
        
        # 暂停（快照）
        manager.pause("code-review")
        
        # 恢复
        manager.resume("code-review")
    """
    
    def __init__(self):
        SANDBOX_DATA.mkdir(parents=True, exist_ok=True)
        self._states: Dict[str, SandboxState] = {}
        self._load_states()
    
    def _load_states(self):
        """加载所有沙箱状态"""
        for f in SANDBOX_DATA.glob("*.json"):
            try:
                state = SandboxState(**json.loads(f.read_text()))
                self._states[state.id] = state
            except Exception as exc:
                _ = exc
    
    def _save_state(self, state: SandboxState):
        """保存沙箱状态"""
        path = SANDBOX_DATA / f"{state.id}.json"
        path.write_text(json.dumps(asdict(state), indent=2, ensure_ascii=False))
        self._states[state.id] = state
    
    def create(self, name: str, image: str = "python:3.12-slim") -> 'SandboxExecutor':
        """
        创建新沙箱
        
        Returns: SandboxExecutor实例
        """
        from .executor import SandboxExecutor
        
        sb_id = f"sb-{int(time.time())}"
        state = SandboxState(
            id=sb_id,
            name=name,
            status="running",
            created_at=time.time(),
            image=image,
        )
        self._save_state(state)
        
        logger.info("Sandbox created: %s (%s)", name, sb_id)
        return SandboxExecutor(image=image)
    
    def pause(self, sandbox_id: str) -> bool:
        """
        暂停沙箱 — 真正调 docker pause 冻结容器进程
        """
        import subprocess
        
        state = self._states.get(sandbox_id)
        if not state:
            return False
        
        if state.status != "running":
            logger.warning("Sandbox %s not running, skip pause", sandbox_id)
            return False
        
        # 真正调docker pause
        if state.container_id:
            try:
                r = subprocess.run(
                    ["docker", "pause", state.container_id],
                    capture_output=True, text=True, timeout=10
                )
                if r.returncode != 0:
                    logger.error("docker pause failed: %s", r.stderr.strip())
                    if "No such container" in r.stderr or "is not running" in r.stderr:
                        state.status = "stopped"
                        self._save_state(state)
                    return False
            except subprocess.TimeoutExpired:
                logger.error("docker pause timeout for %s", sandbox_id)
                return False
            except FileNotFoundError:
                logger.warning("docker not found, state-only pause")
        
        state.status = "paused"
        self._save_state(state)
        logger.info("Sandbox paused: %s (container=%s)", sandbox_id, state.container_id[:12])
        return True
    
    def resume(self, sandbox_id: str) -> Optional['SandboxExecutor']:
        """
        恢复沙箱 — 真正调 docker unpause 解冻容器
        """
        import subprocess
        from .executor import SandboxExecutor
        
        state = self._states.get(sandbox_id)
        if not state or state.status != "paused":
            return None
        
        # 真正调docker unpause
        if state.container_id:
            try:
                r = subprocess.run(
                    ["docker", "unpause", state.container_id],
                    capture_output=True, text=True, timeout=10
                )
                if r.returncode != 0:
                    logger.error("docker unpause failed: %s", r.stderr.strip())
                    return None
            except subprocess.TimeoutExpired:
                logger.error("docker unpause timeout for %s", sandbox_id)
                return None
            except FileNotFoundError:
                logger.warning("docker not found, state-only resume")
        
        state.status = "running"
        self._save_state(state)
        
        logger.info("Sandbox resumed: %s", sandbox_id)
        return SandboxExecutor(image=state.image)
    
    def stop(self, sandbox_id: str) -> bool:
        """停止沙箱"""
        state = self._states.get(sandbox_id)
        if not state:
            return False
        
        state.status = "stopped"
        self._save_state(state)
        
        logger.info("Sandbox stopped: %s", sandbox_id)
        return True
    
    def list_sandboxes(self) -> List[SandboxState]:
        """列出所有沙箱"""
        return list(self._states.values())
    
    def get_state(self, sandbox_id: str) -> Optional[SandboxState]:
        """获取沙箱状态"""
        return self._states.get(sandbox_id)
    
    def cleanup(self, max_age_hours: int = 24):
        """清理过期沙箱"""
        cutoff = time.time() - (max_age_hours * 3600)
        to_remove = []
        
        for sb_id, state in self._states.items():
            if state.status == "stopped" and state.created_at < cutoff:
                to_remove.append(sb_id)
        
        for sb_id in to_remove:
            del self._states[sb_id]
            path = SANDBOX_DATA / f"{sb_id}.json"
            if path.exists():
                path.unlink()
        
        if to_remove:
            logger.info("Cleaned up %d expired sandboxes", len(to_remove))


class CubeSandboxManager:
    """
    CubeSandbox管理器
    
    使用CubeSandbox（KVM）替代Docker，更快更安全。
    """
    
    def __init__(self):
        from .cube_executor import CubeSandboxExecutor
        self._executor = CubeSandboxExecutor()
    
    def is_available(self) -> bool:
        """检查CubeSandbox是否可用"""
        return self._executor.is_available()
    
    def run_code(self, code: str, language: str = "python") -> dict:
        """执行代码"""
        result = self._executor.run_code(code, language)
        return {
            "success": result.success,
            "output": result.output,
            "error": result.error,
            "exit_code": result.exit_code,
            "duration": result.duration,
        }
    
    def run_command(self, command: str) -> dict:
        """执行命令"""
        result = self._executor.run_command(command)
        return {
            "success": result.success,
            "output": result.output,
            "error": result.error,
            "exit_code": result.exit_code,
            "duration": result.duration,
        }
    
    def cleanup(self):
        """清理"""
        self._executor.cleanup()
