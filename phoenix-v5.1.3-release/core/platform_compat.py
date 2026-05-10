"""
不死鸟 Phoenix V5.1 — 平台兼容层

解决 macOS / Linux / Windows 三端差异：
- 路径分隔符
- Shell命令
- 桌面操作
- 服务管理
"""

import os
import sys
import platform
import subprocess
import shutil
from pathlib import Path
from typing import Optional


class PlatformCompat:
    """平台兼容层 — 自动检测当前系统并提供统一接口"""
    
    _instance = None
    
    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        self.system = platform.system()  # 'Darwin', 'Linux', 'Windows'
        self.is_macos = self.system == 'Darwin'
        self.is_linux = self.system == 'Linux'
        self.is_windows = self.system == 'Windows'
        self.is_unix = self.is_macos or self.is_linux
        
        # 路径
        self.home = Path.home()
        self.phoenix_dir = self.home / '.hermes' / 'phoenix'
        self.data_dir = self.phoenix_dir / 'data'
        self.config_dir = self.phoenix_dir / 'config'
        self.skins_dir = self.home / '.hermes' / 'skins'
        self.hermes_config = self.home / '.hermes' / 'config.yaml'
    
    # ── 路径兼容 ──────────────────────────────────────────────
    
    @staticmethod
    def safe_path(path_str: str) -> Path:
        """统一路径分隔符"""
        return Path(path_str.replace('/', os.sep).replace('\\', os.sep))
    
    @staticmethod
    def to_posix(path: Path) -> str:
        """转POSIX路径（配置文件用）"""
        return path.as_posix()
    
    # ── Shell命令兼容 ─────────────────────────────────────────
    
    def run_command(self, cmd: str, **kwargs) -> subprocess.CompletedProcess:
        """跨平台执行Shell命令"""
        if self.is_windows:
            # Windows用cmd.exe
            return subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                executable='cmd.exe', **kwargs
            )
        else:
            return subprocess.run(
                cmd, shell=True, capture_output=True, text=True, **kwargs
            )
    
    @staticmethod
    def dev_null() -> str:
        """获取null设备路径"""
        return 'NUL' if platform.system() == 'Windows' else '/dev/null'
    
    @staticmethod
    def which(cmd: str) -> Optional[str]:
        """跨平台which命令"""
        return shutil.which(cmd)
    
    # ── 配置读写兼容 ─────────────────────────────────────────
    
    def get_hermes_config_path(self) -> Path:
        """获取Hermes配置文件路径"""
        if self.is_windows:
            # Windows: %USERPROFILE%\.hermes\config.yaml
            return self.home / '.hermes' / 'config.yaml'
        else:
            return self.home / '.hermes' / 'config.yaml'
    
    def get_hermes_binary(self) -> str:
        """获取hermes命令路径"""
        hermes = shutil.which('hermes')
        if hermes:
            return hermes
        # 尝试常见路径
        candidates = []
        if self.is_windows:
            candidates = [
                self.home / '.hermes' / 'hermes.exe',
                self.home / '.local' / 'bin' / 'hermes.exe',
                Path('hermes.exe'),
            ]
        else:
            candidates = [
                self.home / '.local' / 'bin' / 'hermes',
                Path('hermes'),
                Path('/usr/local/bin/hermes'),
            ]
        for c in candidates:
            if c.exists():
                return str(c)
        return 'hermes'  # fallback to PATH
    
    # ── 桌面操作兼容 ─────────────────────────────────────────
    
    def open_file(self, file_path: str) -> bool:
        """跨平台打开文件"""
        try:
            if self.is_macos:
                subprocess.run(['open', file_path], check=True)
            elif self.is_linux:
                subprocess.run(['xdg-open', file_path], check=True)
            elif self.is_windows:
                os.startfile(file_path)
            return True
        except Exception:
            return False
    
    def open_url(self, url: str) -> bool:
        """跨平台打开URL"""
        try:
            if self.is_macos:
                subprocess.run(['open', url], check=True)
            elif self.is_linux:
                subprocess.run(['xdg-open', url], check=True)
            elif self.is_windows:
                os.startfile(url)
            return True
        except Exception:
            return False
    
    def take_screenshot(self, output_path: str) -> bool:
        """跨平台截屏"""
        try:
            if self.is_macos:
                subprocess.run(['screencapture', '-x', output_path], check=True)
            elif self.is_linux:
                subprocess.run(['scrot', output_path], check=True)
            elif self.is_windows:
                # Windows 10+ 截屏到剪贴板，需要PowerShell保存
                ps_cmd = (
                    f'Add-Type -AssemblyName System.Windows.Forms;'
                    f'[System.Windows.Forms.Screen]::PrimaryScreen | '
                    f'ForEach-Object {{ $bmp = New-Object System.Drawing.Bitmap($_.Bounds.Width, $_.Bounds.Height); '
                    f'$gfx = [System.Drawing.Graphics]::FromImage($bmp); '
                    f'$gfx.CopyFromScreen($_.Bounds.Location, [System.Drawing.Point]::Empty, $_.Bounds.Size); '
                    f'$bmp.Save("{output_path}") }}'
                )
                subprocess.run(['powershell', '-Command', ps_cmd], check=True)
            return True
        except Exception:
            return False
    
    # ── 服务管理兼容 ─────────────────────────────────────────
    
    def get_process_info(self, name: str) -> list:
        """跨平台获取进程信息"""
        try:
            if self.is_windows:
                result = subprocess.run(
                    ['tasklist', '/FI', f'IMAGENAME eq {name}'],
                    capture_output=True, text=True
                )
            else:
                result = subprocess.run(
                    ['pgrep', '-f', name],
                    capture_output=True, text=True
                )
            return result.stdout.strip().split('\n') if result.stdout.strip() else []
        except Exception:
            return []
    
    def kill_process(self, pid: int) -> bool:
        """跨平台杀死进程"""
        try:
            if self.is_windows:
                subprocess.run(['taskkill', '/F', '/PID', str(pid)], check=True)
            else:
                import signal
                os.kill(pid, signal.SIGTERM)
            return True
        except Exception:
            return False
    
    # ── 环境变量兼容 ─────────────────────────────────────────
    
    def get_env(self, key: str, default: str = '') -> str:
        """跨平台获取环境变量"""
        return os.environ.get(key, default)
    
    def set_env(self, key: str, value: str):
        """设置环境变量（仅当前进程）"""
        os.environ[key] = value
    
    # ── Python路径兼容 ────────────────────────────────────────
    
    def ensure_phoenix_in_path(self):
        """确保phoenix目录在sys.path中"""
        phoenix_str = str(self.phoenix_dir)
        parent_str = str(self.phoenix_dir.parent)
        for p in (phoenix_str, parent_str):
            if p not in sys.path:
                sys.path.insert(0, p)
    
    # ── 平台信息 ─────────────────────────────────────────────
    
    def get_platform_info(self) -> dict:
        """返回完整的平台信息"""
        return {
            'system': self.system,
            'is_macos': self.is_macos,
            'is_linux': self.is_linux,
            'is_windows': self.is_windows,
            'is_unix': self.is_unix,
            'python_version': platform.python_version(),
            'architecture': platform.machine(),
            'phoenix_dir': str(self.phoenix_dir),
            'data_dir': str(self.data_dir),
        }


# 全局单例
compat = PlatformCompat.get()
