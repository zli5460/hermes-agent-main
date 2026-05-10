"""不死鸟 Phoenix V5.1 — 查询复杂度4级分类
来源: CL4R1T4S（全球AI系统prompt泄露）

Level 1: 不用搜索（简单问答）
Level 2: 建议搜索（不确定的问题）
Level 3: 单次搜索（需要最新信息）
Level 4: 深度研究（需要2-20次搜索/调用）
"""

import re

class QueryComplexity:
    """查询复杂度分类器"""
    
    # Level 1: 简单问答，不需要搜索
    SIMPLE_PATTERNS = [
        r"^(你好|hi|hello|嗨|在吗|ok|好的|谢谢|感谢).{0,5}$",
        r"^(今天|明天|昨天).{0,10}(天气|日期|星期)",
        r"^(现在|几点|时间)",
        r"^(你是谁|你叫什么|自我介绍)",
    ]
    
    # Level 2: 建议搜索（不确定是否需要最新信息）
    SUGGEST_SEARCH_PATTERNS = [
        r"(?:哪个|哪个好|推荐|建议|选择|对比|比较)",
        r"(?:怎么|如何|怎样).{0,10}(?:做|用|设置|配置)",
        r"(?:什么是|是什么|啥意思|定义)",
    ]
    
    # Level 3: 单次搜索（需要最新信息）
    NEED_SEARCH_PATTERNS = [
        r"(?:最新|最近|今天|现在|目前|当前).{0,10}(?:新闻|动态|消息|更新|变化)",
        r"(?:价格|多少钱|费用|成本|报价)",
        r"(?:教程|怎么安装|怎么配置|步骤)",
        r"(?:GitHub|开源|项目|工具|框架)",
        r"https?://",  # URL
    ]
    
    # Level 4: 深度研究（需要多次搜索/调用）
    DEEP_RESEARCH_PATTERNS = [
        r"(?:分析|研究|调研|深度|全面|系统).{0,10}(?:分析|研究|调研|报告)",
        r"(?:帮我写.{0,10}(?:报告|论文|方案|计划|白皮书))",
        r"(?:对比.{0,10}(?:所有|全部|市面上|行业))",
        r"(?:整理|汇总|梳理).{0,10}(?:所有|全部|所有关于)",
    ]
    
    def classify(self, message: str) -> int:
        """
        分类查询复杂度
        Returns: 1-4
        """
        msg = message.strip()
        
        # Level 4: 深度研究
        for pattern in self.DEEP_RESEARCH_PATTERNS:
            if re.search(pattern, msg, re.IGNORECASE):
                return 4
        
        # Level 3: 需要搜索
        for pattern in self.NEED_SEARCH_PATTERNS:
            if re.search(pattern, msg, re.IGNORECASE):
                return 3
        
        # Level 2: 建议搜索
        for pattern in self.SUGGEST_SEARCH_PATTERNS:
            if re.search(pattern, msg, re.IGNORECASE):
                return 2
        
        # Level 1: 简单问答
        for pattern in self.SIMPLE_PATTERNS:
            if re.search(pattern, msg, re.IGNORECASE):
                return 1
        
        # 默认Level 2（建议搜索）
        return 2
    
    def describe(self, level: int) -> str:
        """返回级别描述"""
        descriptions = {
            1: "简单问答，不需要搜索",
            2: "建议搜索，可能需要最新信息",
            3: "单次搜索，需要最新信息",
            4: "深度研究，需要2-20次搜索/调用",
        }
        return descriptions.get(level, "未知级别")
