"""
不死鸟 Phoenix V5.1 — 桌面操控模块（跨平台版）

支持 macOS / Linux / Windows 三端

能力：看屏幕（多模态视觉）+ 读UI树（精确定位）+ 操控
- macOS: AppleScript + pyautogui
- Linux: xdotool + pyautogui
- Windows: pyautogui + PowerShell

用法:
    from phoenix.desktop.controller import DesktopController
    dc = DesktopController()
    
    # 自然语言指令
    dc.execute("打开微信，给叮当发消息'今晚几点回来'")
    
    # 或手动操作
    dc.activate_app("WeChat")
    dc.see_screen("找到叮当联系人的坐标")
    dc.click_at(x, y)
    dc.type_text("你好")
    dc.press_key("Return")
"""

from __future__ import annotations

import json
import time
import base64
import subprocess
import platform
import tempfile
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass

_SYSTEM = platform.system()
_IS_MACOS = _SYSTEM == 'Darwin'
_IS_LINUX = _SYSTEM == 'Linux'
_IS_WINDOWS = _SYSTEM == 'Windows'


@dataclass
class ScreenAnalysis:
    """屏幕分析结果"""
    description: str          # AI对画面的理解
    elements: Dict             # 识别到的UI元素
    target_coords: Optional[Tuple[int, int]] = None  # 目标元素坐标
    confidence: float = 0.0   # 置信度


class DesktopController:
    """
    跨平台桌面操控器
    
    三层能力：
    1. 视觉层：多模态看屏幕
    2. UI层：平台原生读控件树
    3. 操控层：平台原生操作
    """
    
    def __init__(self, api_key: str = None, base_url: str = None):
        self.api_key = api_key or self._load_api_key()
        self.base_url = base_url or "https://inference-api.nousresearch.com/v1"
        self.vision_model = "xiaomi/mimo-v2-omni"
        
        # pyautogui（跨平台）
        try:
            import pyautogui
            pyautogui.PAUSE = 0.3
            pyautogui.FAILSAFE = True
            self._pyautogui = pyautogui
        except ImportError:
            self._pyautogui = None
        
        # 屏幕分辨率
        self.screen_size = self._get_screen_size()
        # Retina缩放比例
        self.retina_scale = 2 if _IS_MACOS else 1
    
    def _load_api_key(self) -> str:
        """从config加载API key"""
        try:
            import yaml
            cfg = yaml.safe_load((Path.home() / ".hermes/config.yaml").read_text())
            providers = cfg.get("custom_providers", [])
            for p in providers:
                if p.get("name") == "nous-api":
                    return p.get("api_key", "")
        except Exception as exc:
            _ = exc
        return ""
    
    def _get_screen_size(self) -> Tuple[int, int]:
        """获取屏幕逻辑尺寸"""
        if self._pyautogui:
            size = self._pyautogui.size()
            return (size.width, size.height)
        return (2560, 1440)
    
    # ==================== 视觉层 ====================
    
    def take_screenshot(self, output_path: str = None) -> str:
        """截图，返回路径（跨平台）"""
        if not output_path:
            tmp_dir = tempfile.gettempdir()
            output_path = f"{tmp_dir}/phoenix_screen_{int(time.time())}.png"
        
        if self._pyautogui:
            self._pyautogui.screenshot().save(output_path)
        elif _IS_MACOS:
            subprocess.run(["screencapture", "-x", output_path], timeout=10)
        elif _IS_LINUX:
            subprocess.run(["scrot", output_path], timeout=10)
        elif _IS_WINDOWS:
            ps_cmd = (
                'Add-Type -AssemblyName System.Windows.Forms;'
                '$bmp = New-Object System.Drawing.Bitmap('
                '[System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Width,'
                '[System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Height);'
                '$gfx = [System.Drawing.Graphics]::FromImage($bmp);'
                '$gfx.CopyFromScreen(0, 0, 0, $bmp.Size);'
                f'$bmp.Save("{output_path}")'
            )
            subprocess.run(['powershell', '-Command', ps_cmd], timeout=10)
        
        return output_path
    
    def see_screen(self, question: str, screenshot_path: str = None,
                   resize_for_analysis: bool = True) -> ScreenAnalysis:
        """
        用多模态模型理解屏幕
        """
        if not screenshot_path:
            screenshot_path = self.take_screenshot()
        
        # 缩小图片省token
        if resize_for_analysis:
            from PIL import Image
            img = Image.open(screenshot_path)
            w, h = img.size
            if w > 1280:
                new_w = 1280
                new_h = int(h * new_w / w)
                img_small = img.resize((new_w, new_h), Image.LANCZOS)
                screenshot_path = screenshot_path.replace(".png", "_small.png")
                img_small.save(screenshot_path)
                analysis_size = (new_w, new_h)
            else:
                analysis_size = (w, h)
        else:
            from PIL import Image
            img = Image.open(screenshot_path)
            analysis_size = img.size
        
        # 图片转base64
        with open(screenshot_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()
        
        # 调用多模态模型
        prompt = f"""分析这个屏幕截图。用户想找: {question}

请返回JSON格式:
{{
  "description": "屏幕内容描述",
  "elements": {{"element_name": {{"position": [x, y], "description": "描述"}}}},
  "target_coords": [x, y]  // 目标元素坐标（如有）
}}
注意: 坐标基于 {analysis_size[0]}x{analysis_size[1]} 分辨率。"""
        
        try:
            import httpx
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.vision_model,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {
                                "url": f"data:image/png;base64,{img_b64}"
                            }}
                        ]
                    }],
                    "max_tokens": 1000,
                },
                timeout=30
            )
            
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            # 提取JSON
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return ScreenAnalysis(
                    description=data.get("description", ""),
                    elements=data.get("elements", {}),
                    target_coords=tuple(data.get("target_coords", [])) if data.get("target_coords") else None,
                    confidence=0.8,
                )
        except Exception as exc:
            _ = exc
        
        return ScreenAnalysis(description="分析失败", elements={})
    
    # ==================== UI层 ====================
    
    def read_ui_tree(self, app_name: str) -> Dict:
        """读取应用的UI树（跨平台）"""
        if _IS_MACOS:
            return self._read_ui_tree_macos(app_name)
        elif _IS_LINUX:
            return self._read_ui_tree_linux(app_name)
        elif _IS_WINDOWS:
            return self._read_ui_tree_windows(app_name)
        return {"app": app_name, "windows": "", "error": "不支持的平台"}
    
    def _read_ui_tree_macos(self, app_name: str) -> Dict:
        """macOS: AppleScript读UI树"""
        script = f'''
tell application "System Events"
    tell process "{app_name}"
        set winCount to count of windows
        set winInfo to ""
        repeat with i from 1 to winCount
            try
                set winName to name of window i
                set winInfo to winInfo & "[W" & i & "] " & winName & linefeed
            end try
        end repeat
        return winInfo
    end tell
end tell'''
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=10
        )
        return {
            "app": app_name,
            "windows": result.stdout.strip(),
            "error": result.stderr.strip() if result.stderr else None,
        }
    
    def _read_ui_tree_linux(self, app_name: str) -> Dict:
        """Linux: xdotool读窗口"""
        try:
            result = subprocess.run(
                ["xdotool", "search", "--name", app_name],
                capture_output=True, text=True, timeout=5
            )
            return {"app": app_name, "windows": result.stdout.strip(), "error": None}
        except FileNotFoundError:
            return {"app": app_name, "windows": "", "error": "xdotool未安装"}
    
    def _read_ui_tree_windows(self, app_name: str) -> Dict:
        """Windows: PowerShell读窗口"""
        ps_cmd = (
            f'Get-Process | Where-Object {{$_.MainWindowTitle -like "*{app_name}*"}} | '
            f'Select-Object ProcessName, Id, MainWindowTitle | Format-Table -AutoSize'
        )
        try:
            result = subprocess.run(
                ['powershell', '-Command', ps_cmd],
                capture_output=True, text=True, timeout=5
            )
            return {"app": app_name, "windows": result.stdout.strip(), "error": None}
        except Exception as e:
            return {"app": app_name, "windows": "", "error": str(e)}
    
    # ==================== 操控层 ====================
    
    def activate_app(self, app_name: str) -> bool:
        """激活应用到前台（跨平台）"""
        try:
            if _IS_MACOS:
                subprocess.run(["open", "-a", app_name], timeout=5)
                time.sleep(1.5)
                r = subprocess.run([
                    "osascript", "-e",
                    'tell application "System Events" to return name of first application process whose frontmost is true'
                ], capture_output=True, text=True, timeout=5)
                return app_name.lower() in r.stdout.lower()
            
            elif _IS_LINUX:
                subprocess.run(["xdotool", "search", "--name", app_name, "windowactivate"], timeout=5)
                time.sleep(1)
                return True
            
            elif _IS_WINDOWS:
                ps_cmd = (
                    f'$proc = Get-Process | Where-Object {{$_.MainWindowTitle -like "*{app_name}*"}} | Select-Object -First 1; '
                    f'if ($proc) {{ [System.Diagnostics.Process]::GetProcessById($proc.Id).MainWindowHandle | '
                    f'For-Object {{ Add-Type -Name Win -Namespace Native -MemberDefinition \'[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);\'; '
                    f'[Native.Win]::SetForegroundWindow($_) }} }}'
                )
                subprocess.run(['powershell', '-Command', ps_cmd], timeout=5)
                time.sleep(1)
                return True
        except Exception:
            return False
    
    def click_at(self, x: int, y: int, double: bool = False) -> bool:
        """点击屏幕坐标（跨平台）"""
        if not self._pyautogui:
            return False
        try:
            if double:
                self._pyautogui.doubleClick(x, y)
            else:
                self._pyautogui.click(x, y)
            time.sleep(0.3)
            return True
        except Exception:
            return False
    
    def type_text(self, text: str) -> bool:
        """输入文字（跨平台，支持中文）"""
        if _IS_MACOS:
            escaped = text.replace('"', '\\"').replace('\\', '\\\\')
            script = f'tell application "System Events" to keystroke "{escaped}"'
            try:
                subprocess.run(["osascript", "-e", script], timeout=10)
                time.sleep(0.3)
                return True
            except Exception:
                return False
        else:
            # Linux/Windows: 使用pyautogui
            if not self._pyautogui:
                return False
            try:
                self._pyautogui.typewrite(text, interval=0.05)
                time.sleep(0.3)
                return True
            except Exception:
                return False
    
    def press_key(self, key: str, modifiers: List[str] = None) -> bool:
        """按键（跨平台）"""
        if _IS_MACOS:
            return self._press_key_macos(key, modifiers)
        else:
            return self._press_key_pyautogui(key, modifiers)
    
    def _press_key_macos(self, key: str, modifiers: List[str] = None) -> bool:
        """macOS: AppleScript按键"""
        key_codes = {
            "Return": 36, "Enter": 36, "Tab": 48, "Space": 49,
            "Escape": 53, "Delete": 51, "Up": 126, "Down": 125,
            "Left": 123, "Right": 124,
        }
        
        if key in key_codes:
            code = key_codes[key]
            if modifiers:
                mod_str = ", ".join(f"{m} down" for m in modifiers)
                script = f'tell application "System Events" to key code {code} using {{{mod_str}}}'
            else:
                script = f'tell application "System Events" to key code {code}'
        else:
            if modifiers:
                mod_str = ", ".join(f"{m} down" for m in modifiers)
                script = f'tell application "System Events" to keystroke "{key}" using {{{mod_str}}}'
            else:
                script = f'tell application "System Events" to keystroke "{key}"'
        
        try:
            subprocess.run(["osascript", "-e", script], timeout=5)
            time.sleep(0.3)
            return True
        except Exception:
            return False
    
    def _press_key_pyautogui(self, key: str, modifiers: List[str] = None) -> bool:
        """Linux/Windows: pyautogui按键"""
        if not self._pyautogui:
            return False
        
        key_map = {
            "Return": "enter", "Enter": "enter", "Tab": "tab",
            "Space": "space", "Escape": "esc", "Delete": "delete",
            "Up": "up", "Down": "down", "Left": "left", "Right": "right",
        }
        mapped_key = key_map.get(key, key.lower())
        
        try:
            if modifiers:
                mod_keys = []
                for m in modifiers:
                    if m.lower() in ('command', 'cmd'):
                        mod_keys.append('ctrl' if _IS_WINDOWS else 'command')
                    elif m.lower() == 'alt':
                        mod_keys.append('alt')
                    elif m.lower() == 'shift':
                        mod_keys.append('shift')
                    elif m.lower() == 'control':
                        mod_keys.append('ctrl')
                    else:
                        mod_keys.append(m.lower())
                self._pyautogui.hotkey(*mod_keys, mapped_key)
            else:
                self._pyautogui.press(mapped_key)
            time.sleep(0.3)
            return True
        except Exception:
            return False
    
    def hotkey(self, *keys) -> bool:
        """组合键 hotkey('command', 'f')（跨平台）"""
        if _IS_MACOS:
            modifiers = [f"{k} down" for k in keys[:-1]]
            main_key = keys[-1]
            mod_str = ", ".join(modifiers)
            script = f'tell application "System Events" to keystroke "{main_key}" using {{{mod_str}}}'
            try:
                subprocess.run(["osascript", "-e", script], timeout=5)
                time.sleep(0.3)
                return True
            except Exception:
                return False
        else:
            if not self._pyautogui:
                return False
            mapped = []
            for k in keys:
                if k.lower() in ('command', 'cmd'):
                    mapped.append('ctrl' if _IS_WINDOWS else 'command')
                else:
                    mapped.append(k.lower())
            try:
                self._pyautogui.hotkey(*mapped)
                time.sleep(0.3)
                return True
            except Exception:
                return False
    
    # ==================== 高级任务编排 ====================
    
    def find_and_click(self, target_desc: str, app_name: str = None) -> bool:
        """找到目标并点击（视觉+操控闭环）"""
        if app_name:
            self.activate_app(app_name)
        
        analysis = self.see_screen(f"找到'{target_desc}'的位置，返回精确坐标")
        if analysis.target_coords:
            x, y = analysis.target_coords
            return self.click_at(x, y)
        return False
    
    def execute(self, task: str) -> Dict:
        """
        高级接口：自然语言任务（以后扩展）
        
        Args:
            task: "打开微信给叮当发消息'今晚几点回来'"
        
        Returns:
            {"success": bool, "steps": [...], "result": str}
        """
        return {
            "success": False,
            "steps": [],
            "result": "execute()需要进一步开发LLM任务规划器",
        }


# 全局单例
_controller = None

def get_controller() -> DesktopController:
    global _controller
    if _controller is None:
        _controller = DesktopController()
    return _controller
