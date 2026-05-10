"""不死鸟 Phoenix V4 — LLM任务分类器"""
import os, json, logging
from typing import Optional

logger = logging.getLogger("phoenix.router.llm_classifier")

class LLMClassifier:
    def __init__(self, model="claude-3-haiku-20240307", timeout=3.0):
        self.model = model
        self._client = None
        try:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if api_key:
                import anthropic
                self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout)
        except Exception as e:
            logger.debug("[phoenix.router] LLM classifier init failed: %s", e)

    def available(self): return self._client is not None

    def classify(self, message, has_image=False):
        if not self._client: return None
        try:
            resp = self._client.messages.create(
                model=self.model, max_tokens=100,
                messages=[{"role":"user","content":f'返回JSON: {{"task_type":"类型","confidence":0-1}}\n类型: chat/code_small/code_medium/code_large/reasoning_light/reasoning/vision\n消息: {message[:500]}\nhas_image: {has_image}\n只返回JSON'}])
            text = resp.content[0].text.strip()
            s,e = text.find("{"), text.rfind("}")
            if s<0 or e<0: return None
            data = json.loads(text[s:e+1])
            t = data.get("task_type")
            valid = {"chat","code_small","code_medium","code_large","reasoning_light","reasoning","vision","vision_screenshot","vision_image","vision_video","vision_document"}
            if t not in valid: return None
            return {"task_type":t,"confidence":float(data.get("confidence",0.7)),"source":"llm"}
        except Exception: return None
