"""不死鸟 Phoenix V8 — 意图分类器
来源: GBrain

4类意图：实体/时间/事件/通用 → 自动选择搜索详情级别
"""

import re
from typing import Dict

class IntentClassifier:
    """意图分类器"""
    
    INTENT_PATTERNS = {
        "entity": [
            r"(谁|哪个|什么人|什么公司|哪个团队)",
            r"(关于|介绍|了解).{0,10}(人|公司|组织)",
        ],
        "temporal": [
            r"(什么时候|何时|最近|之前|之后|上次|下次)",
            r"(今天|昨天|明天|上周|下周|这个月)",
        ],
        "event": [
            r"(发生了什么|有什么|有哪些|更新了)",
            r"(新闻|动态|进展|变化|事件)",
        ],
        "general": [],  # 默认
    }
    
    # 搜索详情级别
    DETAIL_LEVELS = {
        "entity": "high",      # 实体查询：高精度
        "temporal": "medium",  # 时间查询：中等
        "event": "medium",     # 事件查询：中等
        "general": "low",      # 通用查询：快速
    }
    
    def classify(self, query: str) -> Dict:
        """分类查询意图"""
        for intent, patterns in self.INTENT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, query, re.IGNORECASE):
                    return {
                        "intent": intent,
                        "detail": self.DETAIL_LEVELS[intent],
                        "confidence": 0.8,
                    }
        
        return {
            "intent": "general",
            "detail": "low",
            "confidence": 0.5,
        }

intent_classifier = IntentClassifier()
