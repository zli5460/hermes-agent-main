"""
不死鸟 Phoenix — Hermes自动适配器

根据scanner的扫描结果，自动适配Phoenix与新版本Hermes的集成。
"""

import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("phoenix.adapt.adapter")


def _read_phoenix_version() -> str:
    """从 VERSION.md 动态读取 Phoenix 版本号"""
    version_file = Path.home() / ".hermes" / "phoenix" / "VERSION.md"
    try:
        text = version_file.read_text(encoding="utf-8")
        # 尝试从表格行匹配版本号，如 '| V2 | ...'
        for line in text.splitlines():
            if line.startswith("|") and "进行中" in line:
                # 取当前进行中版本
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if parts:
                    return parts[0]  # e.g. "V2"
        # 回退：找最后一个带版本的行
        for line in reversed(text.splitlines()):
            if line.startswith("|") and not line.startswith("| 版本"):
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if parts:
                    return parts[0]
    except Exception as exc:
        _ = exc
    return "unknown"


class HermesAdapter:
    """
    Hermes自动适配器
    
    用法:
        scanner = HermesScanner()
        report = scanner.scan()
        
        adapter = HermesAdapter()
        result = adapter.adapt(report)
        # result = {"adapted": True, "fixes": [...], "manual_needed": [...]}
    """
    
    def __init__(self, hermes_home: Optional[str] = None):
        import os
        self._hermes_home = Path(hermes_home or os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
        self._phoenix_dir = self._hermes_home / "phoenix"
        self._hermes_agent = self._hermes_home / "hermes-agent"
        self._report_file = self._phoenix_dir / "data" / "last_adaptation.json"
        self._hook_results = []
    

    def _adapt_run_agent_patch(self) -> dict:
        """自动检测并恢复run_agent.py的hook模型覆盖补丁"""
        fixes = []
        manual_needed = []
        
        run_agent_path = Path.home() / ".hermes" / "hermes-agent" / "run_agent.py"
        if not run_agent_path.exists():
            return {"fixes": fixes, "manual_needed": manual_needed}
        
        content = run_agent_path.read_text()
        
        # 检查补丁是否已存在
        if "Hook model override" in content:
            return {"fixes": fixes, "manual_needed": manual_needed}
        
        # 补丁不存在，尝试自动修复
        logger.info("run_agent.py patch missing, auto-restoring...")
        
        # 备份
        import shutil
        backup_path = run_agent_path.with_suffix(".py.bak")
        if not backup_path.exists():
            shutil.copy2(run_agent_path, backup_path)
        
        # 简单替换：在invoke_hook调用后添加模型覆盖
        if '"pre_api_request"' in content and '_invoke_hook(' in content:
            # 找到pre_api_request调用块并替换
            old_block = '''                        _invoke_hook(
                            "pre_api_request",'''
            new_block = '''                        _hook_results = _invoke_hook(
                            "pre_api_request",'''
            
            if old_block in content:
                content = content.replace(old_block, new_block)
                
                # 在对应的except块后添加模型覆盖逻辑
                old_except = '''                    except Exception as exc:
                        _ = exc

                    if env_var_enabled("HERMES_DUMP_REQUESTS")'''
                new_except = '''                    except Exception as exc:
                        _ = exc

                    # Phoenix V4: 支持hook返回值覆盖模型
                    for _hr in _hook_results:
                        if isinstance(_hr, dict) and "model" in _hr:
                            _new_model = _hr["model"]
                            if _new_model and _new_model != self.model:
                                import logging as _log
                                _log.getLogger("hermes.agent").info(
                                    "Hook model override: %s -> %s", self.model, _new_model
                                )
                                self.model = _new_model

                    if env_var_enabled("HERMES_DUMP_REQUESTS")'''
                
                if old_except in content:
                    content = content.replace(old_except, new_except)
                    run_agent_path.write_text(content)
                    fixes.append("Auto-patched run_agent.py for hook model override")
                    logger.info("run_agent.py patched successfully")
                else:
                    manual_needed.append("run_agent.py: cannot find insertion point for model override")
            else:
                manual_needed.append("run_agent.py: _invoke_hook pattern not found")
        else:
            manual_needed.append("run_agent.py: pre_api_request not found")
        
        return {"fixes": fixes, "manual_needed": manual_needed}

    def adapt(self, scan_result: dict) -> dict:
        """
        根据扫描结果自动适配
        
        Returns:
            {
                "adapted": bool,
                "version": str,
                "fixes": [str],
                "manual_needed": [str],
                "report_path": str,
            }
        """
        fixes = []
        manual_needed = []
        
        version = scan_result.get("version", "unknown")
        is_upgrade = scan_result.get("is_upgrade", False)
        changes = scan_result.get("changes", [])
        
        if not is_upgrade:
            return {
                "adapted": True,
                "version": version,
                "fixes": [],
                "manual_needed": [],
                "message": "No upgrade detected, Phoenix is compatible",
            }
        
        logger.info("Hermes upgrade detected: %s, %d changes", version, len(changes))
        
        # 1. 检查路由集成
        routing_result = self._adapt_routing(scan_result)
        fixes.extend(routing_result.get("fixes", []))
        manual_needed.extend(routing_result.get("manual_needed", []))
        
        # 2. 检查Hook集成
        hook_result = self._adapt_hooks(scan_result)
        fixes.extend(hook_result.get("fixes", []))
        manual_needed.extend(hook_result.get("manual_needed", []))
        
        # 3. 检查配置兼容性
        config_result = self._adapt_config(scan_result)
        fixes.extend(config_result.get("fixes", []))
        manual_needed.extend(config_result.get("manual_needed", []))
        
        # 4. 自动恢复run_agent.py补丁
        patch_result = self._adapt_run_agent_patch()
        fixes.extend(patch_result.get("fixes", []))
        manual_needed.extend(patch_result.get("manual_needed", []))

        # 5. 更新Phoenix版本信息
        self._update_version_info(version, fixes, manual_needed)
        
        adapted = len(manual_needed) == 0
        
        result = {
            "adapted": adapted,
            "version": version,
            "fixes": fixes,
            "manual_needed": manual_needed,
            "report_path": str(self._report_file),
        }
        
        # 保存适配报告
        self._save_report(result, scan_result)
        
        return result
    
    def _adapt_routing(self, scan_result: dict) -> dict:
        """适配路由集成"""
        fixes = []
        manual_needed = []
        
        # 检查gateway的路由函数签名
        run_py = self._hermes_agent / "gateway" / "run.py"
        if not run_py.exists():
            manual_needed.append("gateway/run.py not found - manual routing integration needed")
            return {"fixes": fixes, "manual_needed": manual_needed}
        
        try:
            content = run_py.read_text(errors="replace")
            
            # 检查_resolve_turn_agent_config是否存在
            if "_resolve_turn_agent_config" in content:
                # 检查Phoenix是否已接入
                if "phoenix" not in content.lower():
                    manual_needed.append(
                        "Gateway uses _resolve_turn_agent_config but Phoenix routing not integrated. "
                        "Consider hooking into gateway startup to override routing."
                    )
                else:
                    fixes.append("Phoenix routing already referenced in gateway")
            else:
                manual_needed.append(
                    "_resolve_turn_agent_config not found - routing architecture may have changed. "
                    "Review gateway/run.py for new routing pattern."
                )
            
            # 检查新的路由模式
            if "_resolve_session_agent_runtime" in content:
                fixes.append("Gateway uses _resolve_session_agent_runtime (V2 pattern)")
            
        except Exception as e:
            logger.error("Failed to adapt routing: %s", e)
            manual_needed.append(f"Routing adaptation error: {e}")
        
        return {"fixes": fixes, "manual_needed": manual_needed}
    
    def _adapt_hooks(self, scan_result: dict) -> dict:
        """适配Hook集成"""
        fixes = []
        manual_needed = []
        
        hooks_py = self._hermes_agent / "gateway" / "hooks.py"
        if not hooks_py.exists():
            manual_needed.append("gateway/hooks.py not found - hook system may have changed")
            return {"fixes": fixes, "manual_needed": manual_needed}
        
        try:
            content = hooks_py.read_text(errors="replace")
            
            # 检查HookRegistry是否存在
            if "class HookRegistry" in content:
                fixes.append("HookRegistry found in gateway/hooks.py")
                
                # 检查discover_and_load方法
                if "discover_and_load" in content:
                    fixes.append("Hook discovery system available")
                    
                    # 检查Phoenix hooks是否在正确位置
                    phoenix_hooks = self._phoenix_dir / "integration" / "hooks.py"
                    if phoenix_hooks.exists():
                        fixes.append("Phoenix hooks.py exists")
                    else:
                        manual_needed.append("Phoenix hooks.py missing")
                else:
                    manual_needed.append("Hook discovery method not found")
            else:
                manual_needed.append("HookRegistry class not found - hook system architecture changed")
            
            # 检查builtin_hooks目录
            builtin_hooks = self._hermes_agent / "gateway" / "builtin_hooks"
            if builtin_hooks.exists():
                hooks_files = list(builtin_hooks.glob("*.py"))
                fixes.append(f"Builtin hooks directory: {len(hooks_files)} hooks")
            
        except Exception as e:
            logger.error("Failed to adapt hooks: %s", e)
            manual_needed.append(f"Hook adaptation error: {e}")
        
        return {"fixes": fixes, "manual_needed": manual_needed}
    
    def _adapt_config(self, scan_result: dict) -> dict:
        """适配配置"""
        fixes = []
        manual_needed = []
        
        config_file = self._hermes_home / "config.yaml"
        if not config_file.exists():
            manual_needed.append("config.yaml not found")
            return {"fixes": fixes, "manual_needed": manual_needed}
        
        try:
            import yaml
            config = yaml.safe_load(config_file.read_text()) or {}
        except ImportError:
            # 手动解析关键配置
            config = {}
            content = config_file.read_text()
            if "memory_enabled:" in content:
                config["memory"] = {"memory_enabled": "true" in content.split("memory_enabled:")[1].split("\n")[0]}
        
        # 检查memory配置
        memory_config = config.get("memory", {})
        if memory_config.get("memory_enabled"):
            fixes.append("Hermes memory enabled")
        else:
            manual_needed.append("Hermes memory disabled - enable in config.yaml")
        
        # 检查model配置
        model_config = config.get("model", {})
        if model_config.get("default"):
            fixes.append(f"Default model: {model_config['default']}")
        
        return {"fixes": fixes, "manual_needed": manual_needed}
    
    def _update_version_info(self, version: str, fixes: list, manual_needed: list):
        """更新版本信息"""
        version_file = self._phoenix_dir / "data" / "hermes_version.json"
        try:
            version_file.parent.mkdir(parents=True, exist_ok=True)
            version_file.write_text(json.dumps({
                "hermes_version": version,
                "phoenix_version": _read_phoenix_version(),
                "last_adaptation": time.time(),
                "fixes_count": len(fixes),
                "manual_needed_count": len(manual_needed),
            }, indent=2))
        except Exception as exc:
            _ = exc
    
    def _save_report(self, result: dict, scan_result: dict):
        """保存适配报告"""
        try:
            self._report_file.parent.mkdir(parents=True, exist_ok=True)
            report = {
                "timestamp": time.time(),
                "scan": {
                    "version": scan_result.get("version"),
                    "fingerprint": scan_result.get("fingerprint"),
                    "is_upgrade": scan_result.get("is_upgrade"),
                    "changes_count": len(scan_result.get("changes", [])),
                },
                "adaptation": result,
            }
            self._report_file.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        except Exception as e:
            logger.error("Failed to save adaptation report: %s", e)
