"""
不死鸟 Phoenix — Hermes架构扫描器

扫描Hermes Agent的目录结构、配置、hook系统、路由逻辑，
找出与Phoenix集成相关的变化点。
"""

import os
import re
import json
import hashlib
import logging
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass

logger = logging.getLogger("phoenix.adapt.scanner")


@dataclass
class StructuralChange:
    """结构变化"""
    category: str           # routing/memory/hooks/tools/config
    file_path: str
    change_type: str        # added/modified/deleted
    description: str
    impact: str             # high/medium/low
    auto_fixable: bool = False


class HermesScanner:
    """
    Hermes架构扫描器
    
    用法:
        scanner = HermesScanner()
        report = scanner.scan()
        # report = {
        #   "version": "0.11.0",
        #   "changes": [...],
        #   "integration_points": {...},
        #   "fingerprint": "abc123",
        # }
    """
    
    # Phoenix集成关键路径
    CRITICAL_PATHS = {
        "routing": [
            "gateway/run.py",           # 主gateway逻辑
            "gateway/hooks.py",         # hook系统
            "agent/provider_routing.py", # 模型路由
        ],
        "memory": [
            "agent/memory.py",          # 记忆管理
            "plugins/memory/",          # 记忆插件目录
            "tools/memory_tool.py",     # 记忆工具
        ],
        "hooks": [
            "gateway/hooks.py",         # Hook注册
            "gateway/builtin_hooks/",   # 内置hooks
            "plugins/__init__.py",      # 插件加载
        ],
        "tools": [
            "tools/registry.py",        # 工具注册
            "model_tools.py",           # 工具编排
        ],
        "config": [
            "hermes_cli/main.py",       # CLI入口
            "hermes_cli/commands.py",   # 命令注册
        ],
    }
    
    # 路由相关关键词
    ROUTING_KEYWORDS = [
        "_resolve_turn_agent_config",
        "_resolve_session_agent_runtime",
        "provider_routing",
        "DeliveryRouter",
        "resolve_fast_mode_overrides",
        "model_aliases",
        "credential_pool",
    ]
    
    # Hook相关关键词
    HOOK_KEYWORDS = [
        "HookRegistry",
        "discover_and_load",
        "register_hook",
        "invoke_hook",
        "gateway:startup",
        "gateway:message",
    ]
    
    def __init__(self, hermes_home: Optional[str] = None):
        self._hermes_home = Path(hermes_home or os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
        self._hermes_agent = self._hermes_home / "hermes-agent"
        self._fingerprint_file = self._hermes_home / "phoenix" / "data" / "hermes_fingerprint.json"
        self._last_fingerprint = self._load_fingerprint()
    
    def scan(self) -> dict:
        """
        完整扫描Hermes架构
        
        Returns:
            {
                "version": str,
                "fingerprint": str,
                "is_upgrade": bool,
                "changes": [StructuralChange],
                "integration_points": {category: {files...}},
                "routing_hooks": [str],
                "phoenix_hooks": [str],
            }
        """
        version = self._detect_version()
        current_fingerprint = self._compute_fingerprint()
        is_upgrade = (current_fingerprint != self._last_fingerprint)
        
        changes = []
        if is_upgrade:
            changes = self._detect_changes()
        
        integration_points = self._scan_integration_points()
        routing_hooks = self._scan_routing_hooks()
        phoenix_hooks = self._scan_phoenix_hooks()
        
        result = {
            "version": version,
            "fingerprint": current_fingerprint,
            "is_upgrade": is_upgrade,
            "changes": [vars(c) for c in changes],
            "integration_points": integration_points,
            "routing_hooks": routing_hooks,
            "phoenix_hooks": phoenix_hooks,
        }
        
        # 保存新指纹
        self._save_fingerprint(current_fingerprint, version)
        
        return result
    
    def _detect_version(self) -> str:
        """检测Hermes版本"""
        try:
            result = subprocess.run(
                ["python3", "-m", "hermes_cli.main", "--version"],
                capture_output=True, text=True, cwd=str(self._hermes_agent)
            ).stdout.strip()
            # 提取版本号
            match = re.search(r"v?([\d.]+)", result)
            if match:
                return match.group(1)
        except Exception as exc:
            _ = exc
        
        # 备用：从setup.py/pyproject.toml读取
        for fname in ["pyproject.toml", "setup.py", "setup.cfg"]:
            fpath = self._hermes_agent / fname
            if fpath.exists():
                try:
                    content = fpath.read_text()
                    match = re.search(r'version\s*=\s*["\']([\d.]+)', content)
                    if match:
                        return match.group(1)
                except Exception as exc:
                    _ = exc
        
        return "unknown"
    
    def _compute_fingerprint(self) -> str:
        """计算Hermes目录指纹"""
        hasher = hashlib.md5(usedforsecurity=False)
        
        # 扫描关键目录
        for category, paths in self.CRITICAL_PATHS.items():
            for rel_path in paths:
                full_path = self._hermes_agent / rel_path
                if full_path.is_file():
                    try:
                        stat = full_path.stat()
                        hasher.update(f"{rel_path}:{stat.st_size}:{stat.st_mtime}".encode())
                    except Exception as exc:
                        _ = exc
                elif full_path.is_dir():
                    for f in sorted(full_path.rglob("*.py")):
                        try:
                            stat = f.stat()
                            hasher.update(f"{f.relative_to(self._hermes_agent)}:{stat.st_size}:{stat.st_mtime}".encode())
                        except Exception as exc:
                            _ = exc
        
        return hasher.hexdigest()[:16]
    
    def _detect_changes(self) -> List[StructuralChange]:
        """检测具体变化"""
        changes = []
        
        if not self._last_fingerprint:
            return changes
        
        # 逐文件对比
        for category, paths in self.CRITICAL_PATHS.items():
            for rel_path in paths:
                full_path = self._hermes_agent / rel_path
                if full_path.is_file():
                    change = self._diff_file(rel_path, full_path, category)
                    if change:
                        changes.append(change)
        
        return changes
    
    def _diff_file(self, rel_path: str, full_path: Path, category: str) -> Optional[StructuralChange]:
        """对比单个文件"""
        try:
            stat = full_path.stat()
            content = full_path.read_text(errors="replace")
            lines = content.split("\n")
            
            # 检查是否包含Phoenix集成相关代码
            has_routing = any(kw in content for kw in self.ROUTING_KEYWORDS)
            has_hooks = any(kw in content for kw in self.HOOK_KEYWORDS)
            
            if not has_routing and not has_hooks:
                return None
            
            # 分析变化类型
            impact = "low"
            auto_fixable = False
            
            if has_routing:
                impact = "high"
                # 检查路由函数签名是否变了
                for kw in self.ROUTING_KEYWORDS:
                    if kw in content:
                        # 搜索函数定义
                        pattern = rf"def\s+{re.escape(kw)}\s*\((.*?)\)"
                        match = re.search(pattern, content)
                        if match:
                            auto_fixable = True
            
            if has_hooks and "HookRegistry" in content:
                impact = "high"
                auto_fixable = True
            
            return StructuralChange(
                category=category,
                file_path=rel_path,
                change_type="modified",
                description=f"文件包含Phoenix集成点（routing={has_routing}, hooks={has_hooks}）",
                impact=impact,
                auto_fixable=auto_fixable,
            )
        except Exception as e:
            logger.debug("Failed to diff %s: %s", rel_path, e)
            return None
    
    def _scan_integration_points(self) -> Dict[str, List[str]]:
        """扫描Phoenix集成点"""
        result = {}
        
        for category, paths in self.CRITICAL_PATHS.items():
            found = []
            for rel_path in paths:
                full_path = self._hermes_agent / rel_path
                if full_path.is_file():
                    try:
                        content = full_path.read_text(errors="replace")
                        if any(kw in content for kw in self.ROUTING_KEYWORDS + self.HOOK_KEYWORDS):
                            found.append(rel_path)
                    except Exception as exc:
                        _ = exc
            if found:
                result[category] = found
        
        return result
    
    def _scan_routing_hooks(self) -> List[str]:
        """扫描gateway的hook注册点"""
        hooks = []
        run_py = self._hermes_agent / "gateway" / "run.py"
        
        if run_py.exists():
            try:
                content = run_py.read_text(errors="replace")
                # 找所有hook emit/invoke调用
                patterns = [
                    r'_invoke_hook\(["\']([^"\']+)',
                    r'self\.hooks\.emit\(["\']([^"\']+)',
                    r'hook_count\s*=\s*len\(self\.hooks',
                ]
                for pattern in patterns:
                    matches = re.findall(pattern, content)
                    hooks.extend(matches)
            except Exception as exc:
                _ = exc
        
        return list(set(hooks))
    
    def _scan_phoenix_hooks(self) -> List[str]:
        """扫描Phoenix已注册的hooks"""
        hooks = []
        
        # 检查Phoenix hooks.py
        phoenix_hooks = self._hermes_home / "phoenix" / "integration" / "hooks.py"
        if phoenix_hooks.exists():
            try:
                content = phoenix_hooks.read_text(errors="replace")
                # 找hook方法
                matches = re.findall(r"def\s+(on_\w+)", content)
                hooks.extend(matches)
            except Exception as exc:
                _ = exc
        
        # 检查gateway_api.py
        gateway_api = self._hermes_home / "phoenix" / "integration" / "gateway_api.py"
        if gateway_api.exists():
            try:
                content = gateway_api.read_text(errors="replace")
                matches = re.findall(r"def\s+(\w+)", content)
                hooks.extend(matches)
            except Exception as exc:
                _ = exc
        
        return list(set(hooks))
    
    def _load_fingerprint(self) -> Optional[str]:
        """加载上次的指纹"""
        try:
            if self._fingerprint_file.exists():
                data = json.loads(self._fingerprint_file.read_text())
                return data.get("fingerprint")
        except Exception as exc:
            _ = exc
        return None
    
    def _save_fingerprint(self, fingerprint: str, version: str):
        """保存指纹"""
        try:
            self._fingerprint_file.parent.mkdir(parents=True, exist_ok=True)
            self._fingerprint_file.write_text(json.dumps({
                "fingerprint": fingerprint,
                "version": version,
                "timestamp": time.time(),
            }, indent=2))
        except Exception as exc:
            _ = exc
