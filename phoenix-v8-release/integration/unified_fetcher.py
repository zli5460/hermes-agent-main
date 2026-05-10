"""
Phoenix V8 — 统一网络抓取模块
合并: scrapling_fetcher (Scrapling爬虫) + jina_reader (Jina Reader) + smart_link_reader (智能链接读取)

提供：
- ScraplingFetcher: HTTP直接抓取（绕过反爬）
- JinaReader: Jina Reader API快速抓取
- SmartLinkReader: 智能优先级降级链 (Scrapling → Jina → Chrome fallback)
"""

import time
from typing import Dict, Optional


# ============================================================
# Part 1: ScraplingFetcher (Scrapling爬虫)
# ============================================================

class ScraplingFetcher:
    """Scrapling爬虫集成"""

    def __init__(self):
        self._available = False
        try:
            from scrapling.fetchers import Fetcher, StealthyFetcher
            self._Fetcher = Fetcher
            self._StealthyFetcher = StealthyFetcher
            self._available = True
        except ImportError:
            pass

    def is_available(self) -> bool:
        return self._available

    def fetch(self, url: str, stealthy: bool = False) -> Dict:
        """抓取网页内容"""
        if not self._available:
            return {"error": "Scrapling未安装", "title": "", "text": "", "status": 0}
        try:
            if stealthy:
                page = self._StealthyFetcher.fetch(url, headless=True, network_idle=True)
            else:
                page = self._Fetcher.get(url)
            title = ""
            if page.css("title"):
                title = page.css("title")[0].text or ""
            text = page.text or ""
            return {"title": title, "text": text[:5000], "status": 200, "url": url}
        except Exception as e:
            return {"error": str(e), "title": "", "text": "", "status": 0}

    def fetch_article(self, url: str) -> Dict:
        """抓取文章内容（优化版）"""
        result = self.fetch(url)
        if result.get("error"):
            return result
        try:
            page = self._Fetcher.get(url)
            for tag in page.css("script, style, nav, footer, header"):
                tag.element.getparent().remove(tag.element)
            article = page.css("article, .content, .post, .entry, main")
            if article:
                text = article[0].text or ""
            else:
                text = page.text or ""
            result["text"] = text[:10000]
            result["extracted"] = True
        except Exception:
            result["extracted"] = False
        return result


# ============================================================
# Part 2: JinaReader (Jina Reader API)
# ============================================================

class JinaReader:
    """Jina Reader快速抓取"""

    def __init__(self):
        self._available = False
        try:
            import jina
            self._available = True
        except ImportError:
            pass

    def is_available(self) -> bool:
        return self._available

    def read(self, url: str) -> Dict:
        """快速抓取网页"""
        if not self._available:
            return {"error": "Jina未安装", "content": ""}
        try:
            from jina import Client
            c = Client()
            docs = c.search(inputs=[url])
            if docs and len(docs) > 0:
                return {
                    "title": docs[0].text[:200] if docs[0].text else "",
                    "content": docs[0].text[:10000] if docs[0].text else "",
                    "status": 200,
                    "method": "jina",
                }
            return {"error": "无内容", "content": "", "status": 0}
        except Exception as e:
            return {"error": str(e), "content": "", "status": 0}


# ============================================================
# Part 3: SmartLinkReader (智能链接读取器)
# ============================================================

class SmartLinkReader:
    """智能链接读取器 — 优先级降级: Scrapling → Jina → Chrome fallback"""

    def __init__(self):
        self._scrapling: Optional[ScraplingFetcher] = None
        self._jina: Optional[JinaReader] = None

    def _get_scrapling(self) -> Optional[ScraplingFetcher]:
        if self._scrapling is None:
            self._scrapling = ScraplingFetcher()
        return self._scrapling

    def _get_jina(self) -> Optional[JinaReader]:
        if self._jina is None:
            self._jina = JinaReader()
        return self._jina

    def read(self, url: str) -> Dict:
        """
        智能读取链接内容

        优先级:
        1. Scrapling直接抓取（最快，1-3秒）
        2. Jina Reader（备用API）
        3. Chrome fallback（最后手段）
        """
        start = time.time()

        # 方法1: Scrapling直接抓取
        scrapling = self._get_scrapling()
        if scrapling and scrapling.is_available():
            result = scrapling.fetch_article(url)
            if not result.get("error") and result.get("text"):
                elapsed = int((time.time() - start) * 1000)
                return {
                    "title": result.get("title", ""),
                    "content": result["text"],
                    "method": "scrapling",
                    "time_ms": elapsed,
                }

        # 方法2: Jina Reader
        jina = self._get_jina()
        if jina and jina.is_available():
            result = jina.read(url)
            if not result.get("error") and result.get("content"):
                elapsed = int((time.time() - start) * 1000)
                return {
                    "title": result.get("title", ""),
                    "content": result["content"],
                    "method": "jina",
                    "time_ms": elapsed,
                }

        # 方法3: Chrome fallback
        elapsed = int((time.time() - start) * 1000)
        return {
            "title": "",
            "content": "[需要Chrome截图+Vision分析]",
            "method": "chrome_fallback",
            "time_ms": elapsed,
        }


# ============================================================
# 模块级单例
# ============================================================
scrapling_fetcher = ScraplingFetcher()
jina_reader = JinaReader()
smart_link_reader = SmartLinkReader()
