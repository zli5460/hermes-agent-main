"""
Phoenix V8 — 统一搜索引擎
合并: dual_search (双层搜索) + hybrid_search (混合搜索+RRF)

提供：
- 宽搜索/窄搜索 (DualSearch模式)
- 关键词+语义+RRF融合 (HybridSearch模式)
"""

import re
from typing import List, Dict


class UnifiedSearch:
    """统一搜索引擎：双层搜索 + 混合RRF融合"""

    def __init__(self):
        self._documents = []

    def add_document(self, doc: str, metadata: Dict = None):
        """添加文档"""
        self._documents.append({
            "content": doc,
            "metadata": metadata or {},
            "tokens": set(re.findall(r'[a-zA-Z]+|[\u4e00-\u9fff]', doc.lower())),
        })

    # ===== DualSearch 接口 (wide/narrow) =====

    def search(self, query: str, mode: str = "auto", top_k: int = 5) -> List[Dict]:
        """
        搜索
        mode: "wide" (语义) / "narrow" (精确) / "hybrid" (RRF融合) / "auto"
        """
        if mode == "auto":
            mode = "hybrid"  # 默认走RRF混合搜索
        if mode == "wide":
            return self._wide_search(query)[:top_k]
        elif mode == "narrow":
            return self._narrow_search(query)[:top_k]
        elif mode == "hybrid":
            return self._hybrid_search(query, top_k)
        return self._hybrid_search(query, top_k)

    def _wide_search(self, query: str) -> List[Dict]:
        """宽搜索：语义匹配（基于token重叠）"""
        query_tokens = set(self._tokenize(query))
        results = []
        for doc in self._documents:
            doc_tokens = set(doc["tokens"])
            overlap = len(query_tokens & doc_tokens)
            if overlap > 0:
                results.append({
                    "content": doc["content"][:200],
                    "score": overlap / len(query_tokens),
                    "metadata": doc["metadata"],
                })
        results.sort(key=lambda x: x["score"], reverse=True)
        return results

    def _narrow_search(self, query: str) -> List[Dict]:
        """窄搜索：精确匹配"""
        results = []
        for doc in self._documents:
            if query.lower() in doc["content"].lower():
                results.append({
                    "content": doc["content"][:200],
                    "score": 1.0,
                    "metadata": doc["metadata"],
                })
        return results

    # ===== HybridSearch 接口 (keyword + semantic + RRF) =====

    def _hybrid_search(self, query: str, top_k: int = 5) -> List[Dict]:
        """混合搜索：关键词+语义+RRF融合"""
        keyword_results = self._keyword_search(query)
        semantic_results = self._semantic_search(query)
        return self._rrf_merge(keyword_results, semantic_results)[:top_k]

    def _keyword_search(self, query: str) -> List[Dict]:
        """关键词搜索"""
        query_tokens = set(re.findall(r'[a-zA-Z]+|[\u4e00-\u9fff]', query.lower()))
        results = []
        for i, doc in enumerate(self._documents):
            overlap = len(query_tokens & doc["tokens"])
            if overlap > 0:
                results.append({
                    "index": i,
                    "content": doc["content"][:200],
                    "score": overlap / len(query_tokens) if query_tokens else 0,
                    "method": "keyword",
                })
        results.sort(key=lambda x: x["score"], reverse=True)
        return results

    def _semantic_search(self, query: str) -> List[Dict]:
        """语义搜索（基于Jaccard相似度）"""
        query_tokens = set(re.findall(r'[a-zA-Z]+|[\u4e00-\u9fff]', query.lower()))
        results = []
        for i, doc in enumerate(self._documents):
            doc_tokens = doc["tokens"]
            if not query_tokens or not doc_tokens:
                continue
            intersection = len(query_tokens & doc_tokens)
            union = len(query_tokens | doc_tokens)
            score = intersection / union if union > 0 else 0
            if score > 0:
                results.append({
                    "index": i,
                    "content": doc["content"][:200],
                    "score": score,
                    "method": "semantic",
                })
        results.sort(key=lambda x: x["score"], reverse=True)
        return results

    def _rrf_merge(self, keyword_results: List[Dict], semantic_results: List[Dict], k: int = 60) -> List[Dict]:
        """RRF融合（Reciprocal Rank Fusion）"""
        scores = {}
        for rank, result in enumerate(keyword_results):
            idx = result["index"]
            scores[idx] = scores.get(idx, 0) + 1 / (k + rank + 1)
        for rank, result in enumerate(semantic_results):
            idx = result["index"]
            scores[idx] = scores.get(idx, 0) + 1 / (k + rank + 1)

        merged = []
        for idx, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
            doc = self._documents[idx]
            merged.append({
                "content": doc["content"][:200],
                "rrf_score": round(score, 4),
                "metadata": doc["metadata"],
            })
        return merged

    # ===== 公共工具 =====

    def _tokenize(self, text: str) -> List[str]:
        """分词（支持中英文）"""
        tokens = re.findall(r'[a-zA-Z]+', text.lower())
        tokens += [c for c in text if '\u4e00' <= c <= '\u9fff']
        return tokens


# 模块级单例
unified_search = UnifiedSearch()
