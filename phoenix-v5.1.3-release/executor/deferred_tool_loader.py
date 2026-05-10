"""
Phoenix V5.1 — 工具延迟加载器（Deferred Tool Loader）

参考DeerFlow的DeferredToolRegistry，按需发现工具
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass


@dataclass
class ToolInfo:
    """工具信息"""
    name: str
    description: str
    category: str
    loaded: bool = False
    priority: int = 0  # 使用次数越高，优先级越高


class DeferredToolLoader:
    """延迟工具加载器"""

    def __init__(self):
        self._tools: Dict[str, ToolInfo] = {}
        self._loaders: Dict[str, Callable] = {}
        self._usage_count: Dict[str, int] = {}

    def register_tool(self, name: str, description: str, category: str, loader: Callable):
        """注册工具（不立即加载）"""
        self._tools[name] = ToolInfo(
            name=name, description=description, category=category
        )
        self._loaders[name] = loader

    def search_tools(self, query: str, limit: int = 5) -> List[ToolInfo]:
        """搜索工具（按名称/描述匹配）"""
        query_lower = query.lower()
        results = []

        for name, tool in self._tools.items():
            score = 0
            if query_lower in name.lower():
                score += 10
            if query_lower in tool.description.lower():
                score += 5
            score += tool.priority  # 使用次数加分

            if score > 0:
                results.append(tool)

        results.sort(key=lambda x: x.priority, reverse=True)
        return results[:limit]

    def load_tool(self, name: str) -> Optional[object]:
        """加载工具（延迟加载）"""
        if name not in self._tools:
            return None

        tool = self._tools[name]
        if not tool.loaded and name in self._loaders:
            try:
                loader = self._loaders[name]
                result = loader()
                tool.loaded = True
                tool.priority += 1
                self._usage_count[name] = self._usage_count.get(name, 0) + 1
                return result
            except Exception:
                return None

        return None

    def get_stats(self) -> str:
        """获取工具统计"""
        total = len(self._tools)
        loaded = sum(1 for t in self._tools.values() if t.loaded)
        return f"📊 工具统计: {total}个注册, {loaded}个已加载"
