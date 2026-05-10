"""
Phoenix V5.1 记忆系统 - 人脑级三层记忆 + 越用越聪明

三层记忆：
1. 短期记忆（当前对话）- 内存，最近10条
2. 工作记忆（事实+纠正）- JSON，重要信息
3. 长期记忆（用户+项目）- JSON，永久保存

四个维度：
- 自动提取：根据消息内容判断重要性
- 智能存储：四层文件分门别类
- 上下文检索：回复前自动检索相关记忆
- 进化循环：越用越准，纠正规则永久生效
"""

import json
import os
import time
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple


class MemorySystem:
    """Phoenix V5.1 人脑级记忆系统"""

    def __init__(self, base_dir: str = None):
        if base_dir is None:
            base_dir = os.path.expanduser("~/.hermes/phoenix/memory")

        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.user_profile_path = self.base_dir / "user_profile.json"
        self.projects_path = self.base_dir / "projects.json"
        self.facts_path = self.base_dir / "facts.json"
        self.conversations_dir = self.base_dir / "conversations"
        self.conversations_dir.mkdir(exist_ok=True)

        self.short_term: List[Dict] = []
        self.user_profile = self._load_json(self.user_profile_path, {
            "name": "", "role": "", "preferences": {},
            "created_at": self._now(), "updated_at": self._now()
        })
        self.projects = self._load_json(self.projects_path, {"projects": []})
        self.facts = self._load_json(self.facts_path, {"facts": [], "corrections": []})

    # ===== 基础工具 =====

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat()

    def _load_json(self, path: Path, default: Any) -> Any:
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as exc:
                _ = exc
        return default

    def _save_json(self, path: Path, data: Any):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ===== V4.6: 写入后读回验证 =====
    
    def _save_and_verify(self, path: Path, data: Any) -> bool:
        """保存后立即读回验证 — 防止写入失败但声称成功"""
        try:
            self._save_json(path, data)
            # 读回验证
            with open(path, 'r', encoding='utf-8') as f:
                readback = json.load(f)
            # 简单校验：数据量不能差太多
            return len(json.dumps(readback)) > len(json.dumps(data)) * 0.5
        except Exception:
            return False

    # ===== 维度1：自动提取 =====

    def process_message(self, role: str, content: str) -> Optional[str]:
        """处理每条消息，自动判断重要性并存储"""
        self.add_to_short_term(role, content)
        if role != "user":
            return None

        importance, category = self._assess_importance(content)

        if importance >= 10:
            self._add_fact(self._make_fact(content, "permanent", 10))
            return "permanent"
        elif importance >= 8:
            self._add_correction(self._make_correction(content))
            return "correction"
        elif importance >= 6:
            self._add_fact(self._make_fact(content, category, importance))
            return "fact"
        return None

    def _assess_importance(self, content: str) -> Tuple[int, str]:
        cl = content.lower()
        if any(k in cl for k in ["记住", "不要忘", "以后都", "永远", "每次都要"]):
            return 10, "permanent"
        if any(k in cl for k in ["不对", "不是", "记错了", "搞错了", "别这样", "不要这样", "错了"]):
            return 9, "correction"
        if any(k in cl for k in ["决定", "确认", "就这样做", "方案", "选这个"]):
            return 7, "decision"
        if any(k in cl for k in ["我叫", "我是", "我做", "我在", "我的"]):
            return 6, "personal"
        return 3, "chat"

    @staticmethod
    def _make_fact(content: str, category: str, importance: int) -> Dict:
        return {
            "content": content[:200], "category": category,
            "importance": importance, "weight": importance,
            "access_count": 0, "last_accessed": datetime.now().isoformat(),
            "created_at": datetime.now().isoformat(), "decay": True,
        }

    @staticmethod
    def _make_correction(content: str) -> Dict:
        return {
            "content": content[:200], "category": "correction",
            "importance": 10, "weight": 10,
            "access_count": 0, "last_accessed": datetime.now().isoformat(),
            "created_at": datetime.now().isoformat(), "decay": False,
        }

    def _add_fact(self, fact: Dict):
        for existing in self.facts.get("facts", []):
            if self._similar(existing["content"], fact["content"]):
                existing["weight"] = max(existing["weight"], fact["weight"])
                existing["access_count"] = existing.get("access_count", 0) + 1
                existing["last_accessed"] = self._now()
                self._save_json(self.facts_path, self.facts)
                return
        self.facts.setdefault("facts", []).append(fact)
        self._save_and_verify(self.facts_path, self.facts)  # V4.6: 写入后读回验证

    def _add_correction(self, correction: Dict):
        self.facts.setdefault("corrections", []).append(correction)
        self._save_and_verify(self.facts_path, self.facts)  # V4.6: 写入后读回验证

    @staticmethod
    def _similar(a: str, b: str) -> bool:
        if not a or not b:
            return False
        set_a, set_b = set(a[:50]), set(b[:50])
        return len(set_a & set_b) / max(len(set_a | set_b), 1) > 0.6

    # ===== 维度2：存储管理 =====

    def add_to_short_term(self, role: str, content: str):
        self.short_term.append({"role": role, "content": content, "timestamp": self._now()})
        if len(self.short_term) > 10:
            self.short_term = self.short_term[-10:]

    def get_short_term_context(self, max_messages: int = 5) -> str:
        recent = self.short_term[-max_messages:]
        if not recent:
            return ""
        return "最近对话：\n" + "\n".join(f"- {m['role']}: {m['content'][:80]}" for m in recent)

    def add_project(self, name: str, description: str, key_decisions: List[str] = None):
        project = {
            "name": name, "description": description,
            "key_decisions": key_decisions or [], "status": "进行中",
            "created_at": self._now(), "updated_at": self._now()
        }
        for i, p in enumerate(self.projects["projects"]):
            if p["name"] == name:
                self.projects["projects"][i] = project
                self._save_json(self.projects_path, self.projects)
                return
        self.projects["projects"].append(project)
        self._save_json(self.projects_path, self.projects)

    def update_user_profile(self, **kwargs):
        self.user_profile.update(kwargs)
        self.user_profile["updated_at"] = self._now()
        self._save_json(self.user_profile_path, self.user_profile)

    # ===== 维度3：智能检索 =====

    def retrieve_relevant_memory(self, query: str, max_results: int = 5) -> str:
        parts = []
        corrections = self.facts.get("corrections", [])
        if corrections:
            top = sorted(corrections, key=lambda x: x.get("weight", 0), reverse=True)[:3]
            parts.append("纠正规则（必须遵守）：\n" + "\n".join(f"- ❌ {c['content'][:80]}" for c in top))
        facts = self._search_facts(query)
        if facts:
            parts.append("相关记忆：\n" + "\n".join(f"- {f['content'][:80]}" for f in facts[:3]))
        if self.user_profile.get("name"):
            info = f"用户：{self.user_profile['name']}"
            if self.user_profile.get("role"):
                info += f"，{self.user_profile['role']}"
            parts.append(info)
        active = [p for p in self.projects.get("projects", []) if p.get("status") == "进行中"]
        if active:
            parts.append(f"进行中项目：{active[0]['name']} - {active[0]['description']}")
        short = self.get_short_term_context(3)
        if short:
            parts.append(short)
        if not parts:
            return ""
        return "记忆上下文：\n" + "\n---\n".join(parts)

    def _search_facts(self, query: str) -> List[Dict]:
        ql = query.lower()
        results = []
        for fact in self.facts.get("facts", []):
            cl = fact["content"].lower()
            score = sum(1 for w in ql if w in cl)
            if score > 0:
                results.append({**fact, "_score": score * fact.get("weight", 5)})
                fact["access_count"] = fact.get("access_count", 0) + 1
                fact["last_accessed"] = self._now()
                if fact["access_count"] > 5:
                    fact["weight"] = min(fact.get("weight", 5) + 1, 10)
        results.sort(key=lambda x: x["_score"], reverse=True)
        if results:
            self._save_json(self.facts_path, self.facts)
        return results

    # ===== 对话归档 =====

    def clear_short_term(self):
        if self.short_term:
            self._save_conversation(self.short_term)
        self.short_term = []

    def _save_conversation(self, messages: List[Dict]):
        now = datetime.now()
        cid = f"{now.strftime('%Y-%m-%d_%H%M')}_{hashlib.md5(str(time.time()).encode()).hexdigest()[:4]}"
        self._save_json(self.conversations_dir / f"{cid}.json", {
            "messages": messages, "created_at": self._now(), "message_count": len(messages),
        })

    def get_last_conversation(self, max_messages: int = 5) -> str:
        convs = sorted(self.conversations_dir.glob("*.json"), reverse=True)
        if not convs:
            return ""
        try:
            with open(convs[0], 'r', encoding='utf-8') as f:
                msgs = json.load(f).get("messages", [])[-max_messages:]
            if not msgs:
                return ""
            return "上次对话：\n" + "\n".join(f"- {m['role']}: {m['content'][:80]}" for m in msgs)
        except Exception:
            return ""

    def recover_from_crash(self) -> Dict:
        result = {"recovered": False, "context": ""}
        last = self.get_last_conversation(5)
        if last:
            result["recovered"] = True
            result["context"] = last
        if self.user_profile.get("name"):
            result["user"] = self.user_profile["name"]
        return result

    # ===== 进化机制 =====

    def evolve(self):
        """定期调用：低频记忆降权 + 过期归档清理"""
        now = time.time()
        decayed, cleaned = 0, 0
        for fact in self.facts.get("facts", []):
            if not fact.get("decay", True):
                continue
            la = fact.get("last_accessed", "")
            if la:
                try:
                    days = (now - datetime.fromisoformat(la).timestamp()) / 86400
                    if days > 30 and fact.get("weight", 5) > 1:
                        fact["weight"] -= 1
                        decayed += 1
                except Exception as exc:
                    _ = exc
        cutoff = datetime.now() - timedelta(days=30)
        for f in self.conversations_dir.glob("*.json"):
            try:
                if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                    f.unlink()
                    cleaned += 1
            except Exception as exc:
                _ = exc
        self._save_json(self.facts_path, self.facts)
        return {"decayed": decayed, "cleaned": cleaned}

    def get_stats(self) -> Dict:
        return {
            "short_term": len(self.short_term),
            "facts": len(self.facts.get("facts", [])),
            "corrections": len(self.facts.get("corrections", [])),
            "projects": len([p for p in self.projects.get("projects", []) if p.get("status") == "进行中"]),
            "conversations": len(list(self.conversations_dir.glob("*.json"))),
            "user_profile": self.user_profile.get("name", "未设置"),
            "session_summaries": len(list(self.base_dir.glob("session_*.json"))),
        }

    # ===== V4.6 自动持久化：会话摘要 =====

    def save_session_summary(self, key_work: List[str], decisions: List[str] = None,
                              next_steps: List[str] = None, context: str = ""):
        """保存会话摘要 — 关键工作成果不丢失"""
        now = datetime.now()
        summary = {
            "timestamp": self._now(),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M"),
            "key_work": key_work,
            "decisions": decisions or [],
            "next_steps": next_steps or [],
            "context": context,
        }
        # 按日期存储，同一天多次保存会追加
        day_file = self.base_dir / f"session_{now.strftime('%Y-%m-%d')}.json"
        existing = []
        if day_file.exists():
            try:
                existing = json.loads(day_file.read_text(encoding='utf-8'))
            except Exception:
                existing = []
        existing.append(summary)
        self._save_json(day_file, existing)
        return summary

    def save_checkpoint(self, label: str, data: Dict = None):
        """显式检查点保存 — 里程碑式存储"""
        checkpoint = {
            "label": label,
            "timestamp": self._now(),
            "data": data or {},
        }
        cp_file = self.base_dir / "checkpoints.json"
        existing = []
        if cp_file.exists():
            try:
                existing = json.loads(cp_file.read_text(encoding='utf-8'))
            except Exception:
                existing = []
        existing.append(checkpoint)
        # 只保留最近50个检查点
        if len(existing) > 50:
            existing = existing[-50:]
        self._save_json(cp_file, existing)
        return checkpoint

    def get_recent_summaries(self, days: int = 3) -> str:
        """获取最近N天的会话摘要 — 启动时加载"""
        parts = []
        now = datetime.now()
        for d in range(days):
            date = (now - timedelta(days=d)).strftime("%Y-%m-%d")
            day_file = self.base_dir / f"session_{date}.json"
            if day_file.exists():
                try:
                    summaries = json.loads(day_file.read_text(encoding='utf-8'))
                    for s in summaries:
                        work = " | ".join(s.get("key_work", [])[:3])
                        parts.append(f"[{s.get('date', '')} {s.get('time', '')}] {work}")
                        if s.get("next_steps"):
                            parts.append(f"  → 下一步: {', '.join(s['next_steps'][:2])}")
                except Exception as exc:
                    _ = exc
        if not parts:
            return ""
        return "最近工作记录：\n" + "\n".join(parts)

    def auto_milestone(self, trigger: str, detail: str = ""):
        """自动里程碑检测 — 在关键节点自动保存"""
        milestones_keywords = {
            "分析完成": "analysis_done",
            "升级完成": "upgrade_done",
            "修复完成": "fix_done",
            "测试通过": "test_passed",
            "部署完成": "deploy_done",
        }
        for keyword, category in milestones_keywords.items():
            if keyword in trigger:
                self.save_session_summary(
                    key_work=[f"{category}: {trigger} {detail}".strip()],
                    context=f"auto_milestone triggered by '{trigger}'"
                )
                return category
        return None
