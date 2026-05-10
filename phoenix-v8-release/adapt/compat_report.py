"""
不死鸟 Phoenix — 兼容性报告

生成人类可读的适配报告，告诉你Phoenix和Hermes的融合状态。
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional


class CompatReport:
    """
    兼容性报告生成器
   
    用法:
        report = CompatReport()
        text = report.generate(scan_result, adapt_result)
        print(text)
    """

    @staticmethod
    def _read_phoenix_version() -> str:
        """从 VERSION.md 动态读取 Phoenix 版本号"""
        from pathlib import Path as _P
        version_file = _P.home() / ".hermes" / "phoenix" / "VERSION.md"
        try:
            text = version_file.read_text(encoding="utf-8")
            for line in text.splitlines():
                if line.startswith("|") and "进行中" in line:
                    parts = [p.strip() for p in line.split("|") if p.strip()]
                    if parts:
                        return parts[0]
            for line in reversed(text.splitlines()):
                if line.startswith("|") and not line.startswith("| 版本"):
                    parts = [p.strip() for p in line.split("|") if p.strip()]
                    if parts:
                        return parts[0]
        except Exception as exc:
            _ = exc
        return "unknown"
    
    def __init__(self, hermes_home: Optional[str] = None):
        import os
        self._hermes_home = Path(hermes_home or os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
    
    def generate(self, scan_result: dict, adapt_result: dict) -> str:
        """生成完整报告"""
        lines = []
        
        # Header
        lines.append("=" * 60)
        lines.append("🦅 不死鸟 Phoenix × Hermes 兼容性报告")
        lines.append("=" * 60)
        lines.append("")
        
        # 版本信息
        version = scan_result.get("version", "unknown")
        is_upgrade = scan_result.get("is_upgrade", False)
        lines.append(f"📋 Hermes版本: v{version}")
        lines.append(f"📋 Phoenix版本: {CompatReport._read_phoenix_version()}")
        lines.append(f"📋 升级检测: {'是' if is_upgrade else '否（首次运行或无变化）'}")
        lines.append("")
        
        # 扫描结果
        changes = scan_result.get("changes", [])
        if changes:
            lines.append(f"🔍 检测到 {len(changes)} 个变化点:")
            for change in changes:
                icon = "🔴" if change.get("impact") == "high" else "🟡" if change.get("impact") == "medium" else "🟢"
                fixable = "✅可自动修复" if change.get("auto_fixable") else "⚠️需手动处理"
                lines.append(f"  {icon} [{change.get('category')}] {change.get('file_path')}")
                lines.append(f"     {change.get('description')} — {fixable}")
            lines.append("")
        else:
            lines.append("🔍 无结构变化（Phoenix与当前Hermes版本兼容）")
            lines.append("")
        
        # 集成点
        integration = scan_result.get("integration_points", {})
        if integration:
            lines.append("🔗 Phoenix集成点:")
            for category, files in integration.items():
                lines.append(f"  [{category}] {len(files)}个文件")
                for f in files:
                    lines.append(f"    - {f}")
            lines.append("")
        
        # 适配结果
        adapted = adapt_result.get("adapted", False)
        fixes = adapt_result.get("fixes", [])
        manual = adapt_result.get("manual_needed", [])
        
        if adapted:
            lines.append("✅ 自动适配完成!")
        else:
            lines.append("⚠️ 需要手动处理:")
        
        if fixes:
            lines.append("")
            lines.append("已修复/已兼容:")
            for fix in fixes:
                lines.append(f"  ✅ {fix}")
        
        if manual:
            lines.append("")
            lines.append("需要手动处理:")
            for item in manual:
                lines.append(f"  ⚠️ {item}")
        
        lines.append("")
        lines.append("=" * 60)
        
        return "\n".join(lines)
    
    def generate_quick_status(self) -> str:
        """快速状态检查"""
        lines = []
        lines.append("🦅 Phoenix快速状态:")
        
        # 检查各模块
        modules = {
            "core": "核心模块",
            "router": "路由引擎",
            "executor": "执行管道",
            "memory": "记忆系统",
            "self_heal": "自愈系统",
            "integration": "集成层",
            "security": "安全模块",
            "adapt": "适配模块（第八板块）",
        }
        
        phoenix_dir = self._hermes_home / "phoenix"
        
        for module, name in modules.items():
            module_dir = phoenix_dir / module
            if module_dir.exists():
                py_files = list(module_dir.glob("*.py"))
                lines.append(f"  ✅ {name} ({len(py_files)}个文件)")
            else:
                lines.append(f"  ❌ {name} (未找到)")
        
        # 检查数据文件
        data_dir = phoenix_dir / "data"
        if data_dir.exists():
            json_files = list(data_dir.glob("*.json"))
            lines.append(f"  📊 数据文件: {len(json_files)}个")
        
        # 检查Skills
        skills_dir = Path.home() / ".hermes" / "skills"
        phoenix_skills = [d for d in skills_dir.iterdir() if d.is_dir() and "phoenix" in d.name] if skills_dir.exists() else []
        lines.append(f"  🛠️ Phoenix Skills: {len(phoenix_skills)}个")
        
        return "\n".join(lines)
    
    def save_report(self, scan_result: dict, adapt_result: dict, output_dir: Optional[str] = None):
        """保存报告到文件"""
        if output_dir is None:
            output_dir = str(self._hermes_home / "phoenix" / "data")
        
        output_path = Path(output_dir) / f"compat_report_{int(time.time())}.txt"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        report_text = self.generate(scan_result, adapt_result)
        output_path.write_text(report_text, encoding="utf-8")
        
        return str(output_path)
