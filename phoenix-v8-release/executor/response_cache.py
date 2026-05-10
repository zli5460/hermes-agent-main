"""不死鸟 Phoenix V8 — 响应缓存"""
import json, hashlib, time
from pathlib import Path
from typing import Optional

class ResponseCache:
    def __init__(self, max_size=100, ttl=3600):
        self.max_size = max_size
        self.ttl = ttl
        self._cache = {}
        self._file = Path.home()/".hermes/phoenix/data/response_cache.json"
        self._load()
    def _hash(self, msg): return hashlib.md5(msg.strip().lower().encode()).hexdigest()[:12]
    def get(self, msg):
        e = self._cache.get(self._hash(msg))
        if not e: return None
        if time.time()-e["t"]>self.ttl: del self._cache[self._hash(msg)]; return None
        e["h"]=e.get("h",0)+1; self._save(); return e["r"]
    def set(self, msg, resp):
        self._cache[self._hash(msg)]={"r":resp,"t":time.time(),"h":0}
        if len(self._cache)>self.max_size:
            del self._cache[min(self._cache, key=lambda k:self._cache[k]["t"])]
        self._save()
    def stats(self): return {"size":len(self._cache),"hits":sum(e.get("h",0) for e in self._cache.values())}
    def _load(self):
        try:
            if self._file.exists(): self._cache=json.loads(self._file.read_text())
        except Exception as e:
            print(f"[ResponseCache] load failed: {e}")
    def _save(self):
        try: self._file.parent.mkdir(parents=True,exist_ok=True); self._file.write_text(json.dumps(self._cache,ensure_ascii=False))
        except Exception as e:
            print(f"[ResponseCache] save failed: {e}")

response_cache = ResponseCache()
