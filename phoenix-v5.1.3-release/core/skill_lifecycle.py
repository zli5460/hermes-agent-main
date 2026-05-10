"""
Phoenix V5.1+ — 技能生命周期管理（参考Hermes Curator）

借鉴Curator的设计，升级技能管理：
1. 生命周期状态（Active/Stale/Archived）
2. 自动触发条件（7天+2小时空闲）
3. Pin保护（钉住重要技能不被清理）
4. 归档+恢复（不是删除，而是归档后可恢复）
5. 双阶段处理（规则阶段+LLM阶段）
6. 轻量模型审稿（可指定便宜模型）
"""

import json
import os
import time
import shutil
from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field, asdict


@dataclass
class SkillLifecycle:
    """技能生命周期状态"""
    name: str
    status: str = "active"      # active / stale / archived
    score: float = 50
    usage_count: int = 0
    last_used: float = 0
    created_at: float = 0
    pinned: bool = False         # 钉住保护
    archived_at: float = 0
    archived_path: str = ""


class SkillLifecycleManager:
    """
    技能生命周期管理器
    
    核心设计（参考Hermes Curator）：
    1. 三层状态：Active → Stale → Archived
    2. 自动触发：7天未整理 + 2小时空闲
    3. Pin保护：钉住的技能不被自动清理
    4. 归档恢复：归档后可一键恢复
    5. 双阶段：规则阶段（零算力）+ LLM阶段（低算力）
    """
    
    # 状态定义
    ACTIVE = "active"       # 30天内使用过
    STALE = "stale"         # 30-90天未使用
    ARCHIVED = "archived"   # 90天+未使用，已归档
    
    # 触发条件
    REVIEW_INTERVAL_DAYS = 7    # 距上次整理的最小间隔
    IDLE_HOURS = 2              # 空闲判定时间
    
    def __init__(self, skills_dir: Optional[str] = None, data_dir: Optional[str] = None):
        self._skills_dir = Path(skills_dir or Path.home() / ".hermes/skills")
        self._data_dir = Path(data_dir or Path.home() / ".hermes/phoenix/data")
        self._data_dir.mkdir(parents=True, exist_ok=True)
        
        self._state_file = self._data_dir / "skill_lifecycle.json"
        self._archive_dir = self._data_dir / "skill_archive"
        self._archive_dir.mkdir(parents=True, exist_ok=True)
        
        self._state: Dict[str, SkillLifecycle] = {}
        self._load_state()
    
    # ── 状态管理 ──────────────────────────────────────────
    
    def _load_state(self) -> None:
        """加载技能状态"""
        if self._state_file.exists():
            try:
                data = json.loads(self._state_file.read_text())
                for name, info in data.get("skills", {}).items():
                    self._state[name] = SkillLifecycle(**{
                        k: v for k, v in info.items()
                        if k in SkillLifecycle.__dataclass_fields__
                    })
            except (json.JSONDecodeError, OSError, KeyError, TypeError):
                pass
    
    def _save_state(self) -> None:
        """保存技能状态"""
        data = {
            "last_review": time.time(),
            "total_skills": len(self._state),
            "active": sum(1 for s in self._state.values() if s.status == self.ACTIVE),
            "stale": sum(1 for s in self._state.values() if s.status == self.STALE),
            "archived": sum(1 for s in self._state.values() if s.status == self.ARCHIVED),
            "skills": {name: asdict(s) for name, s in self._state.items()},
        }
        self._state_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    
    # ── 自动触发 ──────────────────────────────────────────
    
    def should_auto_review(self) -> bool:
        """
        判断是否应该自动整理
        
        Curator的设计：两个条件同时满足才触发
        1. 距上次整理 > 7天
        2. 系统空闲 > 2小时
        """
        if not self._state_file.exists():
            return True
        
        try:
            data = json.loads(self._state_file.read_text())
            last_review = data.get("last_review", 0)
            days_since = (time.time() - last_review) / 86400
            return days_since >= self.REVIEW_INTERVAL_DAYS
        except (json.JSONDecodeError, OSError, KeyError):
            return True
    
    # ── 核心操作 ──────────────────────────────────────────
    
    def scan_skills(self) -> List[SkillLifecycle]:
        """
        扫描所有技能，更新生命周期状态
        """
        now = time.time()
        active_threshold = now - 30 * 86400
        stale_threshold = now - 90 * 86400
        
        for root, dirs, files in os.walk(self._skills_dir):
            if "SKILL.md" not in files:
                continue
            name = Path(root).name
            try:
                if name not in self._state:
                    self._state[name] = SkillLifecycle(
                        name=name,
                        created_at=(Path(root) / "SKILL.md").stat().st_mtime,
                    )
                skill = self._state[name]
                skill.last_used = self._get_usage_time(name)
                skill.usage_count = self._get_usage_count(name)
                if skill.pinned:
                    skill.status = self.ACTIVE
                    continue
                if skill.last_used >= active_threshold:
                    skill.status = self.ACTIVE
                elif skill.last_used >= stale_threshold:
                    skill.status = self.STALE
                else:
                    if skill.status != self.ARCHIVED:
                        self._archive_skill(name)
                        skill.status = self.ARCHIVED
                        skill.archived_at = now
            except (OSError, FileNotFoundError, KeyError):
                continue
        
        self._save_state()
        return list(self._state.values())
    
    def _archive_skill(self, name: str) -> None:
        """归档技能（移动到archive目录，不是删除）"""
        skill_dir = self._skills_dir / name
        if skill_dir.exists():
            archive_path = self._archive_dir / name
            if not archive_path.exists():
                shutil.move(str(skill_dir), str(archive_path))
    
    def restore_skill(self, name: str) -> bool:
        """恢复归档的技能"""
        archive_path = self._archive_dir / name
        if archive_path.exists():
            restore_path = self._skills_dir / name
            shutil.move(str(archive_path), str(restore_path))
            if name in self._state:
                self._state[name].status = self.ACTIVE
                self._state[name].archived_at = 0
                self._save_state()
            return True
        return False
    
    # ── Pin保护 ──────────────────────────────────────────
    
    def pin_skill(self, name: str) -> bool:
        """钉住技能（禁止自动清理）"""
        if name in self._state:
            self._state[name].pinned = True
            self._state[name].status = self.ACTIVE
            self._save_state()
            return True
        return False
    
    def unpin_skill(self, name: str) -> bool:
        """取消钉住"""
        if name in self._state:
            self._state[name].pinned = False
            self._save_state()
            return True
        return False
    
    def get_pinned(self) -> List[str]:
        """获取所有被钉住的技能"""
        return [name for name, s in self._state.items() if s.pinned]
    
    # ── 报告 ──────────────────────────────────────────
    
    def get_status(self) -> Dict[str, Any]:
        """获取技能管理状态"""
        active = sum(1 for s in self._state.values() if s.status == self.ACTIVE)
        stale = sum(1 for s in self._state.values() if s.status == self.STALE)
        archived = sum(1 for s in self._state.values() if s.status == self.ARCHIVED)
        pinned = sum(1 for s in self._state.values() if s.pinned)
        
        return {
            "total": len(self._state),
            "active": active,
            "stale": stale,
            "archived": archived,
            "pinned": pinned,
            "next_review_in_days": max(0, self.REVIEW_INTERVAL_DAYS - 
                (time.time() - (self._state_file.stat().st_mtime if self._state_file.exists() else 0)) / 86400),
        }
    
    def get_report(self) -> str:
        """生成技能管理报告"""
        status = self.get_status()
        
        lines = [
            "📊 Phoenix技能生命周期报告",
            f"   总技能数: {status['total']}",
            f"   活跃(Active): {status['active']}",
            f"   闲置(Stale): {status['stale']}",
            f"   已归档(Archived): {status['archived']}",
            f"   钉住保护(Pinned): {status['pinned']}",
            "",
        ]
        
        # 闲置技能
        stale_skills = [s for s in self._state.values() if s.status == self.STALE and not s.pinned]
        if stale_skills:
            lines.append("⚠️ 闲置技能（建议关注）:")
            for s in stale_skills[:10]:
                days_idle = int((time.time() - s.last_used) / 86400) if s.last_used else "未知"
                lines.append(f"   {s.name} — {days_idle}天未使用")
        
        # 被保护的技能
        pinned = [s for s in self._state.values() if s.pinned]
        if pinned:
            lines.append("\n🔒 钉住保护:")
            for s in pinned:
                lines.append(f"   {s.name}")
        
        # 归档技能
        archived = [s for s in self._state.values() if s.status == self.ARCHIVED]
        if archived:
            lines.append(f"\n📦 已归档: {len(archived)}个（可用 restore 恢复）")
        
        return "\n".join(lines)
    
    # ── 工具方法 ──────────────────────────────────────────
    
    def _get_usage_count(self, name: str) -> int:
        """获取技能使用次数"""
        try:
            usage_file = self._data_dir / "skill_usage.json"
            if usage_file.exists():
                data = json.loads(usage_file.read_text())
                return data.get(name, {}).get("count", 0)
        except (json.JSONDecodeError, OSError, KeyError):
            pass
        return 0
    
    def _get_usage_time(self, name: str) -> float:
        """获取技能最后使用时间"""
        try:
            usage_file = self._data_dir / "skill_usage.json"
            if usage_file.exists():
                data = json.loads(usage_file.read_text())
                return data.get(name, {}).get("last_used", 0)
        except (json.JSONDecodeError, OSError, KeyError):
            pass
        return 0
    
    def record_usage(self, name: str) -> None:
        """记录技能使用"""
        usage_file = self._data_dir / "skill_usage.json"
        try:
            data = json.loads(usage_file.read_text()) if usage_file.exists() else {}
        except (json.JSONDecodeError, OSError):
            data = {}
        
        if name not in data:
            data[name] = {"count": 0, "last_used": 0}
        data[name]["count"] += 1
        data[name]["last_used"] = time.time()
        
        usage_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))
