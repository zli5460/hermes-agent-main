"""不死鸟 Phoenix V8 — 子agent执行器（Nous Portal统一接口）

通过Nous Portal API调用所有模型（包括Claude），不再用CLI。
统一入口：https://inference-api.nousresearch.com/v1

用法:
    from phoenix.executor.claude_executor import claude_executor
    result = claude_executor.run("帮我写个Python爬虫", model="anthropic/claude-sonnet-4.6")
"""

import json
import os
import time
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("phoenix.executor.claude")


class ClaudeExecutor:
    """
    子agent执行器 — 通过Nous Portal统一调用所有模型
    
    不再依赖Claude Code CLI，直接走API。
    所有模型（mimo/claude/gpt/gemini）都用同一个接口。
    """
    
    DEFAULT_BASE_URL = "https://inference-api.nousresearch.com/v1"
    DEFAULT_MODEL = "anthropic/claude-sonnet-4.6"
    
    def __init__(self):
        self._api_key = ""
        self._base_url = self.DEFAULT_BASE_URL
        self._resolve_config()
    
    def _resolve_config(self):
        """从config.yaml读取API配置"""
        try:
            import yaml
            cfg_path = Path.home() / ".hermes" / "config.yaml"
            if cfg_path.exists():
                cfg = yaml.safe_load(cfg_path.read_text()) or {}
                model_cfg = cfg.get("model", {})
                self._api_key = model_cfg.get("api_key", "")
                self._base_url = model_cfg.get("base_url", self.DEFAULT_BASE_URL)
        except ImportError:
            # 没有yaml，手动解析
            try:
                cfg_path = Path.home() / ".hermes" / "config.yaml"
                if cfg_path.exists():
                    for line in cfg_path.read_text().splitlines():
                        stripped = line.strip()
                        if stripped.startswith("api_key:") and not self._api_key:
                            val = stripped.split(":", 1)[1].strip().strip("'\"")
                            if val and val != "''":
                                self._api_key = val
                        elif stripped.startswith("base_url:") and self._base_url == self.DEFAULT_BASE_URL:
                            val = stripped.split(":", 1)[1].strip().strip("'\"")
                            if val:
                                self._base_url = val
            except Exception as exc:
                _ = exc
        
        # 环境变量优先
        self._api_key = os.environ.get("NOUS_API_KEY", self._api_key)
        self._base_url = os.environ.get("NOUS_BASE_URL", self._base_url)
    
    def is_available(self) -> bool:
        """检查是否可用"""
        return bool(self._api_key)
    
    def run(self, task: str, model: str = DEFAULT_MODEL, 
            timeout: int = 120, max_tokens: int = 4096) -> dict:
        """
        执行任务（通过Nous Portal API）
        
        Args:
            task: 任务描述
            model: 模型名（完整格式：provider/model-name）
            timeout: 超时秒数
            max_tokens: 最大输出token数
        
        Returns:
            {"success": bool, "output": str, "model": str, "latency": float}
        """
        if not self.is_available():
            return {"success": False, "output": "Nous Portal API Key未配置", "model": model}
        
        try:
            import requests
        except ImportError:
            return {"success": False, "output": "requests库未安装", "model": model}
        
        start_time = time.time()
        
        try:
            resp = requests.post(
                f"{self._base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": task}],
                    "max_tokens": max_tokens,
                },
                timeout=timeout,
            )
            
            latency = time.time() - start_time
            
            if resp.status_code == 200:
                data = resp.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return {
                    "success": True,
                    "output": content,
                    "model": model,
                    "latency": latency,
                }
            else:
                error_msg = f"API错误 {resp.status_code}: {resp.text[:200]}"
                logger.warning("Nous Portal call failed: %s", error_msg)
                return {
                    "success": False,
                    "output": error_msg,
                    "model": model,
                    "latency": latency,
                }
        
        except Exception as e:
            latency = time.time() - start_time
            return {
                "success": False,
                "output": f"执行异常: {e}",
                "model": model,
                "latency": latency,
            }
    
    def run_with_fallback(self, task: str, model: str = DEFAULT_MODEL,
                          fallback_model: str = "", timeout: int = 120) -> dict:
        """
        执行任务（带自动fallback）
        
        如果主力模型失败，自动切换到备用模型。
        """
        result = self.run(task, model, timeout)
        
        if result["success"]:
            return result
        
        if fallback_model:
            logger.info("Primary model %s failed, trying fallback %s", model, fallback_model)
            result = self.run(task, fallback_model, timeout)
            result["used_fallback"] = True
            return result
        
        return result


# 全局单例
claude_executor = ClaudeExecutor()
