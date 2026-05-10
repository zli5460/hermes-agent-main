"""不死鸟 Phoenix V8 — Tavily搜索集成
AI专属主力搜索
"""

from typing import Dict, List

class TavilySearch:
    """Tavily AI搜索"""
    
    def __init__(self):
        self._available = False
        self._client = None
        try:
            from tavily import TavilyClient
            self._TavilyClient = TavilyClient
            self._available = True
        except ImportError:
            pass
    
    def is_available(self) -> bool:
        return self._available
    
    def search(self, query: str, max_results: int = 5) -> Dict:
        """AI搜索"""
        if not self._available:
            return {"error": "Tavily未安装", "results": []}
        
        try:
            import os
            api_key = os.environ.get("TAVILY_API_KEY", "")
            if not api_key:
                return {"error": "未配置TAVILY_API_KEY", "results": []}
            
            client = self._TavilyClient(api_key=api_key)
            response = client.search(query, max_results=max_results)
            
            results = []
            for r in response.get("results", []):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", "")[:500],
                })
            
            return {"results": results, "query": query}
        except Exception as e:
            return {"error": str(e), "results": []}

tavily_search = TavilySearch()
