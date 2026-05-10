"""
Phoenix V5.1 守门员机制
用mimo-v2.5判断任务复杂度，决定是否交给Claude
"""

import json
import os
import time
import requests
from pathlib import Path

# API配置
_config = {}
def _load_config():
    global _config
    if _config:
        return _config
    cfg_path = Path.home() / ".hermes" / "config.yaml"
    try:
        import yaml
        if cfg_path.exists():
            cfg = yaml.safe_load(cfg_path.read_text()) or {}
            model_cfg = cfg.get("model", {})
            _config["api_key"] = os.environ.get("NOUS_API_KEY", model_cfg.get("api_key", ""))
            _config["base_url"] = os.environ.get("NOUS_BASE_URL", model_cfg.get("base_url", "https://inference-api.nousresearch.com/v1"))
    except Exception as exc:
        _ = exc
    return _config

# 守门员判断prompt
GATEKEEPER_PROMPT = """你是一个任务复杂度判断器。判断以下任务是否超出轻量级AI模型(mimo-v2.5)的能力范围，需要交给更强的AI模型(Claude)处理。

判断标准：
1. 代码任务：是否需要超过50行代码、多文件协作、架构设计、复杂算法？
2. 推理任务：是否需要多步推理、专业知识、深度分析、学术论证？
3. 语义任务：是否涉及抽象概念、隐喻、深层含义、复杂逻辑？

用户消息：{message}

只返回JSON：{{"need_upgrade": true/false, "reason": "...", "confidence": 0.0-1.0}}"""

def judge_task_complexity(message: str) -> dict:
    """
    用mimo-v2.5判断任务复杂度
    
    Returns:
        {"need_upgrade": bool, "reason": str, "confidence": float}
    """
    config = _load_config()
    if not config.get("api_key"):
        # 无法判断，默认不升级
        return {"need_upgrade": False, "reason": "no_api_key", "confidence": 0.5}
    
    try:
        session = requests.Session()
        session.proxies = {"http": None, "https": None}
        session.trust_env = False
        
        prompt = GATEKEEPER_PROMPT.format(message=message[:1000])
        
        resp = session.post(
            f"{config['base_url']}/chat/completions",
            headers={"Authorization": f"Bearer {config['api_key']}", "Content-Type": "application/json"},
            json={
                "model": "xiaomi/mimo-v2.5",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 100,
                "temperature": 0.1,
            },
            timeout=5,  # 快速判断，5秒超时
        )
        
        if resp.status_code == 200:
            data = resp.json()
            msg = data.get("choices", [{}])[0].get("message", {})
            # mimo-v2.5用reasoning格式，内容可能在reasoning字段
            result_text = msg.get("content") or msg.get("reasoning") or ""
            
            # 提取JSON
            start = result_text.find("{")
            end = result_text.rfind("}") + 1
            if start >= 0 and end > start:
                result = json.loads(result_text[start:end])
                return {
                    "need_upgrade": result.get("need_upgrade", False),
                    "reason": result.get("reason", ""),
                    "confidence": float(result.get("confidence", 0.7)),
                }
    except Exception as e:
        pass
    
    # 默认不升级
    return {"need_upgrade": False, "reason": "judgment_failed", "confidence": 0.5}
