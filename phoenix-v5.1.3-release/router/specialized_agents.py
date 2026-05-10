"""
Phoenix 专门化子agent

不同任务用不同的专门化子agent，提高效率和质量。

用法：
    from phoenix.router.specialized_agents import SpecializedRouter
    
    router = SpecializedRouter()
    agent = router.select("帮我设计一个landing page")
    # → DesignAgent（专门做设计）
    
    agent = router.select("分析这段代码的性能问题")
    # → AnalysisAgent（专门做分析）
"""

import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger("phoenix.router.specialized")


@dataclass
class AgentProfile:
    """专门化agent档案"""
    name: str
    description: str
    model_preference: str      # 首选模型
    system_prompt: str         # 专用系统提示词
    tools: list               # 专用工具集
    keywords: list            # 触发关键词


# === 专门化agent定义 ===

DESIGN_AGENT = AgentProfile(
    name="design",
    description="UI/UX设计专家，创建生产级前端界面",
    model_preference="anthropic/claude-sonnet-4.6",
    system_prompt="""你是设计专家。创建独特、生产级的前端界面。
避免通用的"AI风格"美学，实现真正的可用代码。
设计前先思考：目的、调性、约束、差异化。
选择一个明确的审美方向并精确执行。""",
    tools=["read_file", "write_file", "terminal", "browser_vision"],
    keywords=["设计", "design", "UI", "UX", "界面", "landing", "页面", "样式", "CSS", "布局"],
)

ANALYSIS_AGENT = AgentProfile(
    name="analysis",
    description="深度分析专家，系统性分析问题",
    model_preference="anthropic/claude-opus-4.7",
    system_prompt="""你是深度分析专家。系统性分析问题，找出根因。
分析步骤：1.理解现状 2.识别问题 3.分析原因 4.给出方案。
输出结构化的分析报告。""",
    tools=["read_file", "search_files", "terminal"],
    keywords=["分析", "analyze", "分析一下", "为什么", "原因", "根因", "诊断", "review"],
)

RESEARCH_AGENT = AgentProfile(
    name="research",
    description="研究专家，深度调研和信息收集",
    model_preference="anthropic/claude-sonnet-4.6",
    system_prompt="""你是研究专家。深度调研主题，收集可靠信息。
步骤：1.搜索信息 2.验证来源 3.整理要点 4.给出结论。
引用来源，确保信息准确。""",
    tools=["web_search", "web_extract", "read_file"],
    keywords=["研究", "research", "调研", "查找", "搜索", "了解", "学习"],
)

WRITING_AGENT = AgentProfile(
    name="writing",
    description="写作专家，高质量内容创作",
    model_preference="xiaomi/mimo-v2.5",
    system_prompt="""你是写作专家。创作高质量的中文内容。
风格：简洁有力，不啰嗦，有洞察。
根据场景调整：技术文档要准确，营销文案要有感染力。""",
    tools=["read_file", "write_file"],
    keywords=["写", "write", "文案", "文章", "内容", "创作", "撰写", "起草"],
)

DEBUGGING_AGENT = AgentProfile(
    name="debugging",
    description="调试专家，系统性定位和修复bug",
    model_preference="anthropic/claude-sonnet-4.6",
    system_prompt="""你是调试专家。系统性定位和修复bug。
步骤：1.复现问题 2.定位根因 3.最小修复 4.验证修复。
不猜测，基于证据推理。""",
    tools=["read_file", "search_files", "terminal", "patch"],
    keywords=["debug", "调试", "bug", "报错", "错误", "修复", "fix", "error", "异常"],
)

PLANNING_AGENT = AgentProfile(
    name="planning",
    description="规划专家，任务分解和项目规划",
    model_preference="anthropic/claude-opus-4.7",
    system_prompt="""你是规划专家。把大任务拆成可执行的小步骤。
输出：明确的目标、有序的步骤、每步的验证标准。
考虑依赖关系和优先级。""",
    tools=["read_file", "write_file", "search_files"],
    keywords=["规划", "plan", "计划", "拆解", "分解", "步骤", "安排", "架构"],
)

# agent注册表
SPECIALIZED_AGENTS: Dict[str, AgentProfile] = {
    "design": DESIGN_AGENT,
    "analysis": ANALYSIS_AGENT,
    "research": RESEARCH_AGENT,
    "writing": WRITING_AGENT,
    "debugging": DEBUGGING_AGENT,
    "planning": PLANNING_AGENT,
}


class SpecializedRouter:
    """
    专门化子agent路由器
    
    根据任务内容选择最合适的专门化agent。
    
    用法：
        router = SpecializedRouter()
        
        agent = router.select("帮我设计一个登录页面")
        print(agent.name)  # "design"
        print(agent.model_preference)  # "anthropic/claude-sonnet-4.6"
        
        agent = router.select("你好")
        print(agent)  # None（普通对话不需要专门化agent）
    """
    
    def __init__(self):
        self._agents = SPECIALIZED_AGENTS
    
    def select(self, task: str) -> Optional[AgentProfile]:
        """
        根据任务选择专门化agent
        
        Returns: AgentProfile or None（普通对话返回None）
        """
        task_lower = task.lower()
        
        best_match = None
        best_score = 0
        
        for name, profile in self._agents.items():
            score = 0
            for keyword in profile.keywords:
                if keyword.lower() in task_lower:
                    score += len(keyword)  # 长关键词权重更高
            
            if score > best_score:
                best_score = score
                best_match = profile
        
        # 需要至少匹配一个关键词
        if best_score >= 2:
            logger.info("Specialized agent selected: %s (score=%d)", best_match.name, best_score)
            return best_match
        
        return None
    
    def get(self, name: str) -> Optional[AgentProfile]:
        """按名称获取agent"""
        return self._agents.get(name)
    
    def list_all(self) -> Dict[str, str]:
        """列出所有专门化agent"""
        return {name: profile.description for name, profile in self._agents.items()}
