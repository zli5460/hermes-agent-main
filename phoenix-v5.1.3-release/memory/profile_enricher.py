"""不死鸟 Phoenix V5.1 — 人物/公司画像
来源: GBrain enrich

自动构建人物和公司档案。
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional

class ProfileEnricher:
    """人物/公司画像构建器"""
    
    def __init__(self):
        self._data_dir = Path.home() / ".hermes" / "phoenix" / "data"
        self._profiles_file = self._data_dir / "profiles.json"
        self._profiles = self._load()
    
    def enrich_person(self, name: str, context: str = "") -> Dict:
        """构建人物画像"""
        profile = self._find_or_create(name, "person")
        
        # 从上下文提取信息
        if context:
            profile["mentions"] = profile.get("mentions", 0) + 1
            profile["last_seen"] = time.time()
            
            # 提取角色/职位
            role_patterns = [
                (r"(CEO|CTO|创始人|负责人|总监|经理|工程师|设计师)", "role"),
                (r"(在|是|属于|加入).{0,10}(公司|团队|组织)", "organization"),
                (r"(使用|偏好|喜欢|擅长).{0,10}(Python|代码|设计|运营)", "skills"),
            ]
            
            for pattern, field in role_patterns:
                match = __import__("re").search(pattern, context)
                if match:
                    profile[field] = match.group(0)
        
        self._save()
        return profile
    
    def enrich_company(self, name: str, context: str = "") -> Dict:
        """构建公司画像"""
        profile = self._find_or_create(name, "company")
        
        if context:
            profile["mentions"] = profile.get("mentions", 0) + 1
            profile["last_seen"] = time.time()
            
            # 提取公司信息
            info_patterns = [
                (r"(融资|投资|收购|上市)", "events"),
                (r"(产品|服务|平台|工具)", "products"),
                (r"(AI|机器学习|深度学习|LLM)", "tech_focus"),
            ]
            
            for pattern, field in info_patterns:
                match = __import__("re").search(pattern, context)
                if match:
                    if field not in profile:
                        profile[field] = []
                    profile[field].append(match.group(0))
        
        self._save()
        return profile
    
    def get_profile(self, name: str) -> Optional[Dict]:
        """获取画像"""
        for p in self._profiles:
            if p["name"] == name:
                return p
        return None
    
    def search_profiles(self, query: str) -> List[Dict]:
        """搜索画像"""
        results = []
        for p in self._profiles:
            if query.lower() in p["name"].lower():
                results.append(p)
        return results
    
    def list_all(self, profile_type: str = None) -> List[Dict]:
        """列出所有画像"""
        if profile_type:
            return [p for p in self._profiles if p["type"] == profile_type]
        return self._profiles
    
    def _find_or_create(self, name: str, ptype: str) -> Dict:
        """查找或创建画像"""
        for p in self._profiles:
            if p["name"] == name:
                return p
        
        profile = {
            "name": name,
            "type": ptype,
            "created": time.time(),
            "last_seen": time.time(),
            "mentions": 0,
        }
        self._profiles.append(profile)
        return profile
    
    def stats(self) -> Dict:
        """统计"""
        persons = len([p for p in self._profiles if p["type"] == "person"])
        companies = len([p for p in self._profiles if p["type"] == "company"])
        return {"total": len(self._profiles), "persons": persons, "companies": companies}
    
    def _load(self):
        try:
            if self._profiles_file.exists():
                return json.loads(self._profiles_file.read_text())
        except Exception as exc:
            _ = exc
        return []
    
    def _save(self):
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._profiles_file.write_text(json.dumps(self._profiles, ensure_ascii=False, indent=2))

profile_enricher = ProfileEnricher()
