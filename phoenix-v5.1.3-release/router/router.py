"""Phoenix V5.1 - 双维度智能路由：关键词 + LLM理解"""
import re
import os
import requests
from dataclasses import dataclass
from typing import Optional, Tuple

try:
    from .model_registry import MODEL_REGISTRY, get_model_info, ModelInfo
except ImportError:
    MODEL_REGISTRY = {}
    get_model_info = lambda x: None
    ModelInfo = None


@dataclass
class TaskSignature:
    task_type: str
    context_size: int = 0
    requires_tools: bool = False
    latency_sensitive: bool = False
    cost_budget: str = "low"


@dataclass
class ModelChoice:
    model: str
    reason: str
    confidence: float
    source: str = "keyword"  # "keyword" / "llm" / "hybrid" / "fallback"


class Router:
    """双维度智能路由器：关键词（免费快判）+ LLM理解（精准判断）"""

    # ===== 本地模型映射（用于未在model_registry中注册的模型）=====
    LOCAL_MODEL_MAP = {

        "xiaomi/mimo-v2.5": {"name": "Mimo V2.5", "provider": "xiaomi"},
        "xiaomi/mimo-v2.5-pro": {"name": "Mimo V2.5 Pro", "provider": "xiaomi"},
        "anthropic/claude-haiku-4.5": {"name": "Claude Haiku 4.5", "provider": "anthropic"},
        "anthropic/claude-sonnet-4.6": {"name": "Claude Sonnet 4.6", "provider": "anthropic"},
        "anthropic/claude-opus-4.7": {"name": "Claude Opus 4.7", "provider": "anthropic"},
        "openai/gpt-5.5": {"name": "GPT-5.5", "provider": "openai"},
    }

    # ===== 路由表 =====
    ROUTE_TABLE = {
        # 第1档：日常档（聊天+轻任务）
        "daily":          ("xiaomi/mimo-v2.5",            "日常"),
        # 第2档：中等档
        "medium":         ("xiaomi/mimo-v2.5-pro",        "中等"),
        "medium_content": ("anthropic/claude-haiku-4.5",  "文案"),
        "medium_code":    ("xiaomi/mimo-v2.5-pro",        "中码"),
        # 第3档：深度（需确认）
        "deep":           ("anthropic/claude-sonnet-4.6", "深度"),
        # 第4档：大神（需确认）
        "god":            ("anthropic/claude-opus-4.7",   "大神"),
        # 第5档：真神（需确认）— 双王
        "super_god":      ("anthropic/claude-opus-4.7",   "真神主"),
        "super_god_gpt":  ("openai/gpt-5.5",              "真神副"),
    }

    # ===== 快速排除模式（第0层：同步，0成本）=====
    # 匹配到任何一条 → 直接判定为日常档，不进意图判断
    EXCLUSION_PATTERNS = [
        # ★ Python 3.9.6兼容：flag必须在compile时传入，不能传给search()
        re.compile(r'[?？]$', re.MULTILINE),
        re.compile(r'(?:不要|不需要|不用|关掉|关闭|取消|去掉|没用|不是|别用|停掉).{0,5}(?:深度|大神|真神|架构|战略)', re.MULTILINE),
        re.compile(r'^(?:好|好的|收到|明白|OK|ok|嗯|知道了|可以|行|了解|谢谢|感谢|对|是的|没错|就这样)$', re.MULTILINE),
        re.compile(r'(?:看图|截图|这张图|图片里|照片里|识别一下|分析一下这张)', re.MULTILINE),
    ]

    # ===== 关键词短语 → 中低档映射 =====
    # V5.1铁律：deep/god/super_god 只允许 /深度 /大神 /真神 手动触发。
    # 这里绝不出现高档关键词，避免“深度学习/架构图/分析一下”误触发烧钱。
    KEYWORD_MAP = [
        # 第2档
        (["写代码", "爬虫", "自动化脚本"], "medium_code"),
        (["文案", "选题", "洗稿", "公众号", "小红书"], "medium_content"),
        (["帮我写", "生成", "创建", "做一个", "总结一下", "分析一下"], "medium"),
        # 第1档翻译/日常
        (["翻译", "translate"], "daily"),
        # 日常聊天
        (["在吗", "你好", "hi", "hello", "哈哈", "ok", "好的", "谢谢", "再见", "嗯", "no"], "daily"),
    ]

    # ===== 高成本确认档位：仅手动命令触发 =====
    HIGH_TIER_KEYWORDS = {}


    # ===== LLM分类提示词 =====
    CLASSIFY_PROMPT = (
        "你是一个消息分类器。将用户消息分类为以下之一，只回复分类词（不要解释）：\n"
        "daily - 日常聊天/闲聊/问候/翻译/简单问题\n"
        "medium_code - 写代码/脚本/爬虫/技术任务\n"
        "medium_content - 写文案/文章/内容创作\n"
        "medium - 中等任务：总结/整理/分析/普通方案\n\n"
        "注意：不要输出 deep/god/super_god。高成本模式只由 /深度 /大神 /真神 手动命令触发。\n"
        "用户消息：{message}\n"
        "分类："
    )

    VALID_TYPES = {
        "daily", "medium", "medium_content", "medium_code",
    }

    # ===== 构造函数 =====
    def __init__(self):
        self._nous_key = self._load_nous_key()
        self._nous_url = "https://inference-api.nousresearch.com/v1/chat/completions"

    def _load_nous_key(self) -> str:
        """从Hermes config加载Nous Portal API key"""
        try:
            import yaml
            cfg_path = os.path.expanduser("~/.hermes/config.yaml")
            if os.path.exists(cfg_path):
                cfg = yaml.safe_load(open(cfg_path)) or {}
                return cfg.get("model", {}).get("api_key", "")
        except Exception as exc:
            _ = exc
        return os.environ.get("NOUS_API_KEY", "")

    # ===== 维度1：关键词提取（3ms，免费）=====
    def _keyword_classify(self, message: str) -> Optional[str]:
        """从消息中抓取关键词，返回档位"""
        msg = message.lower()
        for keywords, task_type in self.KEYWORD_MAP:
            if any(k in msg for k in keywords):
                return task_type
        return None

    # ===== 维度2：LLM理解判断（~200ms，走Nous Portal）=====
    def _llm_classify(self, message: str) -> Optional[str]:
        """调Hermes 4-70B理解消息，返回档位"""
        if not self._nous_key or len(message) <= 15:
            return None
        try:
            resp = requests.post(
                self._nous_url,
                headers={
                    "Authorization": f"Bearer {self._nous_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "xiaomi/mimo-v2.5",
                    "messages": [
                        {"role": "user", "content": self.CLASSIFY_PROMPT.format(message=message[:500])}
                    ],
                    "max_tokens": 10,
                    "temperature": 0,
                },
                timeout=3,
                proxies={"http": None, "https": None},
            )
            result = resp.json()["choices"][0]["message"]["content"].strip().lower()
            # 只接受有效档位词
            if result in self.VALID_TYPES:
                return result
            # 模糊匹配
            for vt in self.VALID_TYPES:
                if vt in result:
                    return vt
            return None
        except Exception:
            return None

    # ===== 双维度汇合 =====
    def classify(self, message: str, has_image: bool = False) -> Tuple[str, float, str]:
        """
        双维度分类，返回 (task_type, confidence, source)
        两边一致 → 高置信(hybrid)
        两边不同 → 取LLM（LLM理解更准）
        只有关键词 → 取关键词(keyword)
        只有LLM → 取LLM(llm)
        都没命中 → 兜底mimo(fallback)
        """
        if has_image:
            return ("daily", 1.0, "vision")

        raw = (message or "").strip()
        lowered = raw.lower()
        if lowered.startswith("/深度"):
            return ("deep", 1.0, "manual")
        if lowered.startswith("/大神"):
            return ("god", 1.0, "manual")
        if lowered.startswith("/真神"):
            return ("super_god", 1.0, "manual")

        # 维度1：关键词（只允许中低档）
        kw_result = self._keyword_classify(message)

        # 维度2：LLM理解（只允许中低档）
        llm_result = self._llm_classify(message)

        if kw_result and llm_result:
            if kw_result == llm_result:
                return (kw_result, 1.0, "hybrid")
            return (llm_result, 0.9, "llm")
        elif llm_result:
            return (llm_result, 0.8, "llm")
        elif kw_result:
            return (kw_result, 0.7, "keyword")
        else:
            return ("daily", 0.6, "fallback")

    # ===== 主接口 =====
    def select_model(self, task_type: str) -> ModelChoice:
        """根据档位返回模型"""
        if task_type in self.ROUTE_TABLE:
            m, r = self.ROUTE_TABLE[task_type]
        else:
            m, r = self.ROUTE_TABLE["daily"]
        return ModelChoice(model=m, reason=r, confidence=1.0)

    def route(self, message: str, has_image: bool = False) -> ModelChoice:
        """完整路由：双维度分类 → 选模型 → 返回"""
        task_type, confidence, source = self.classify(message, has_image)
        choice = self.select_model(task_type)
        choice.confidence = confidence
        choice.source = source
        return choice

    # ===== 高成本任务三层判断（第0层排除 → LLM意图 → 命令触发）=====
    # LLM意图判断提示词
    _INTENT_PROMPT = """你是一个消息意图分类器。判断用户的请求是否真正需要使用高级AI模型做深度任务。

深度任务 = 用户要求系统性分析/架构设计/战略规划，需要长时间推理和复杂思考。
非深度任务 = 聊天/提问/确认/闲聊/单步执行/含有关键词但意图不在此。

判断规则：
1. 否定句（"不需要深度"、"关掉"）→ 非深度任务
2. 问句（"？"结尾）→ 非深度任务
3. 单句确认（"好的"、"收到"）→ 非深度任务
4. 只是提到词但不是在请求（"深度相机"、"架构图在哪里"）→ 非深度任务
5. 短消息(<15字)无明确任务 → 非深度任务

只回复一个词：
- "日常" = 非深度任务
- "深度" = 需要深度分析(Sonnet)
- "大神" = 需要系统设计(Opus)
- "真神" = 需要顶层战略(Opus+GPT)

用户消息：{message}
分类："""

    def _check_exclusions(self, message: str) -> bool:
        """第0层：快速排除。返回True=应该排除（不触发高成本确认）"""
        for pattern in self.EXCLUSION_PATTERNS:
            if pattern.search(message):
                return True
        return False

    def _keyword_high_tier(self, message: str) -> Optional[str]:
        """第2层：短语关键词匹配。返回档位或None"""
        return None

    def _llm_intent_classify(self, message: str) -> Optional[str]:
        """第1层：LLM意图判断（~200ms）。返回档位或None"""
        if not self._nous_key or len(message) <= 15:
            return None
        try:
            resp = requests.post(
                self._nous_url,
                headers={
                    "Authorization": f"Bearer {self._nous_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "xiaomi/mimo-v2.5",
                    "messages": [
                        {"role": "user", "content": self._INTENT_PROMPT.format(message=message[:500])}
                    ],
                    "max_tokens": 10,
                    "temperature": 0,
                },
                timeout=3,
                proxies={"http": None, "https": None},
            )
            result = resp.json()["choices"][0]["message"]["content"].strip().lower()
            _INTENT_MAP = {"深度": "deep", "大神": "god", "真神": "super_god"}
            if result in _INTENT_MAP:
                return _INTENT_MAP[result]
            return None
        except Exception:
            return None

    def classify_high_tier(self, message: str) -> Tuple[Optional[str], str]:
        """V5.1稳定口径：高成本档只认手动命令。

        /深度 → deep
        /大神 → god
        /真神 → super_god

        不再使用 LLM 意图或关键词自动升级，避免误触发烧钱。
        """
        raw = (message or "").strip().lower()
        if raw.startswith("/深度"):
            return "deep", "manual"
        if raw.startswith("/大神"):
            return "god", "manual"
        if raw.startswith("/真神"):
            return "super_god", "manual"
        return None, "manual_only"

    # ===== 工具方法 =====
    def needs_user_confirm(self, task_type: str) -> bool:
        """深度/大神/真神需要用户确认"""
        return task_type in ["deep", "god", "super_god"]

    def get_super_god_pair(self) -> Tuple[str, str]:
        """真神双王：返回(主力Opus, 副攻GPT-5.5)"""
        return (
            self.ROUTE_TABLE["super_god"][0],
            self.ROUTE_TABLE["super_god_gpt"][0],
        )

    # 向后兼容旧接口
    def _find_cheaper(self, current_model, task_type):
        return None

    def _find_faster(self, current_model, task_type):
        return None
