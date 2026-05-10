"""
Phoenix V8 — 统一维护模块
合并: gc (垃圾回收) + health_checker (健康检查+自动修复) + autopilot (自维护守护)

提供：
- GarbageCollector: 清理过期记忆/无效抗体/冗余配置
- HealthChecker: 全面健康检查 + 自动修复
- Autopilot: 自动同步、提取、嵌入的守护进程
"""

import json
import time
from pathlib import Path
from typing import Dict, List


# ============================================================
# Part 1: GarbageCollector (垃圾回收)
# ============================================================

class GarbageCollector:
    """垃圾回收器"""

    def __init__(self):
        self._data_dir = Path.home() / ".hermes" / "phoenix" / "data"

    def collect(self) -> Dict:
        """执行垃圾回收"""
        results = {
            "memories_cleaned": 0,
            "antibodies_cleaned": 0,
            "tasks_cleaned": 0,
            "diary_cleaned": 0,
            "total_freed_bytes": 0,
        }
        results["memories_cleaned"] = self._clean_memories()
        results["antibodies_cleaned"] = self._clean_antibodies()
        results["tasks_cleaned"] = self._clean_tasks()
        results["diary_cleaned"] = self._clean_diary()
        return results

    def _clean_memories(self) -> int:
        """清理过期记忆（超过30天未访问）"""
        ltm_path = self._data_dir / "long_term_memory.json"
        if not ltm_path.exists():
            return 0
        try:
            memories = json.loads(ltm_path.read_text())
            now = time.time()
            threshold = 30 * 24 * 3600
            cleaned = 0
            kept = []
            for mem in memories:
                last_access = mem.get("last_access", mem.get("created_at", 0))
                if now - last_access > threshold and mem.get("access_count", 0) == 0:
                    cleaned += 1
                else:
                    kept.append(mem)
            if cleaned > 0:
                ltm_path.write_text(json.dumps(kept, ensure_ascii=False, indent=2))
            return cleaned
        except Exception:
            return 0

    def _clean_antibodies(self) -> int:
        """清理失败率过高的抗体"""
        ab_path = self._data_dir / "antibodies.json"
        if not ab_path.exists():
            return 0
        try:
            antibodies = json.loads(ab_path.read_text())
            cleaned = 0
            kept = []
            for ab in antibodies:
                applied = ab.get("applied_count", 0)
                success = ab.get("success_count", 0)
                if applied > 10 and success / applied < 0.2:
                    cleaned += 1
                else:
                    kept.append(ab)
            if cleaned > 0:
                ab_path.write_text(json.dumps(kept, ensure_ascii=False, indent=2))
            return cleaned
        except Exception:
            return 0

    def _clean_tasks(self) -> int:
        """清理旧task文件"""
        tasks_dir = self._data_dir / "tasks"
        if not tasks_dir.exists():
            return 0
        cleaned = 0
        threshold = 7 * 24 * 3600
        for task_file in tasks_dir.glob("*.json"):
            try:
                age = time.time() - task_file.stat().st_mtime
                if age > threshold:
                    task_file.unlink()
                    cleaned += 1
            except Exception as exc:
                _ = exc
        return cleaned

    def _clean_diary(self) -> int:
        """清理日记（限制大小）"""
        diary_path = self._data_dir / "diary.json"
        if not diary_path.exists():
            return 0
        try:
            size = diary_path.stat().st_size
            if size > 1024 * 1024:
                entries = json.loads(diary_path.read_text())
                now = time.time()
                threshold = 30 * 24 * 3600
                kept = [e for e in entries if now - e.get("timestamp", 0) < threshold]
                diary_path.write_text(json.dumps(kept, ensure_ascii=False, indent=2))
                return len(entries) - len(kept)
            return 0
        except Exception:
            return 0

    def stats(self) -> Dict:
        """获取存储统计"""
        stats = {}
        for name in ["long_term_memory", "extracted_memories", "antibodies",
                      "evolution", "knowledge_graph", "diary", "state"]:
            path = self._data_dir / f"{name}.json"
            if path.exists():
                stats[name] = {
                    "size_bytes": path.stat().st_size,
                    "size_kb": round(path.stat().st_size / 1024, 1),
                }
        tasks_dir = self._data_dir / "tasks"
        if tasks_dir.exists():
            stats["tasks"] = {"count": len(list(tasks_dir.glob("*.json")))}
        return stats


# ============================================================
# Part 2: HealthChecker (健康检查+自动修复)
# ============================================================

class HealthChecker:
    """健康检查器"""

    # 每个运行时 JSON 文件都有固定形状。不能统一写 []，否则二次 doctor
    # 会在 knowledge_graph/evolution 这类 dict 文件上触发 list.get 崩溃。
    _FILE_DEFAULTS = {
        "long_term_memory.json": [],
        "extracted_memories.json": [],
        "antibodies.json": [],
        "diary.json": [],
        "knowledge_graph.json": {"entities": [], "relations": []},
        "evolution.json": {
            "events": [],
            "model_performance": {},
            "compress_quality": [],
            "latency_history": [],
        },
        "state.json": {},
    }

    def __init__(self):
        self._data_dir = Path.home() / ".hermes" / "phoenix" / "data"

    def check(self) -> Dict:
        """全面健康检查"""
        issues = []
        issues.extend(self._check_data_files())
        issues.extend(self._check_memory())
        issues.extend(self._check_kg())
        issues.extend(self._check_config())
        fixes = self._auto_fix(issues)
        return {
            "total_checks": len(issues) + len(fixes),
            "issues_found": len(issues),
            "fixes_applied": len(fixes),
            "issues": issues,
            "fixes": fixes,
            "healthy": len(issues) == 0,
        }

    def _default_for(self, filename: str):
        default = self._FILE_DEFAULTS.get(filename, [])
        return json.loads(json.dumps(default))

    def _expected_type_for(self, filename: str):
        return type(self._default_for(filename))

    def _write_default(self, path: Path, filename: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._default_for(filename), ensure_ascii=False, indent=2))

    def _check_data_files(self) -> List[Dict]:
        issues = []
        required_files = [
            "long_term_memory.json", "extracted_memories.json",
            "knowledge_graph.json", "antibodies.json", "evolution.json",
        ]
        for filename in required_files:
            path = self._data_dir / filename
            if not path.exists():
                issues.append({"type": "missing_file", "file": filename, "severity": "warning"})
                continue
            if path.stat().st_size == 0:
                issues.append({"type": "empty_file", "file": filename, "severity": "warning"})
                continue
            try:
                data = json.loads(path.read_text())
            except Exception:
                issues.append({"type": "invalid_json", "file": filename, "severity": "warning"})
                continue
            expected_type = self._expected_type_for(filename)
            if not isinstance(data, expected_type):
                issues.append({
                    "type": "wrong_shape", "file": filename,
                    "expected": expected_type.__name__,
                    "actual": type(data).__name__, "severity": "warning",
                })
        for filename in required_files:
            path = self._data_dir / filename
            if path.exists() and path.stat().st_size > 10 * 1024 * 1024:
                issues.append({
                    "type": "large_file", "file": filename,
                    "size_mb": path.stat().st_size / 1024 / 1024, "severity": "warning",
                })
        return issues

    def _check_memory(self) -> List[Dict]:
        issues = []
        ext_path = self._data_dir / "extracted_memories.json"
        if ext_path.exists():
            try:
                memories = json.loads(ext_path.read_text())
            except Exception:
                return issues
            if not isinstance(memories, list):
                return issues
            unapplied = [m for m in memories if isinstance(m, dict) and not m.get("applied", False)]
            if len(unapplied) > 50:
                issues.append({"type": "unapplied_memories", "count": len(unapplied), "severity": "info"})
        return issues

    def _check_kg(self) -> List[Dict]:
        issues = []
        kg_path = self._data_dir / "knowledge_graph.json"
        if kg_path.exists():
            try:
                kg = json.loads(kg_path.read_text())
            except Exception:
                return issues
            if not isinstance(kg, dict):
                issues.append({
                    "type": "wrong_shape", "file": "knowledge_graph.json",
                    "expected": "dict", "actual": type(kg).__name__, "severity": "warning",
                })
                return issues
            entities = kg.get("entities", [])
            relations = kg.get("relations", [])
            if len(entities) > 0 and len(relations) == 0:
                issues.append({"type": "kg_no_relations", "entities": len(entities), "severity": "warning"})
        return issues

    def _check_config(self) -> List[Dict]:
        issues = []
        config_path = Path.home() / ".hermes" / "phoenix" / "config.json"
        if not config_path.exists():
            issues.append({"type": "missing_config", "severity": "critical"})
        return issues

    def _auto_fix(self, issues: List[Dict]) -> List[Dict]:
        fixes = []
        for issue in issues:
            if issue["type"] == "missing_file":
                path = self._data_dir / issue["file"]
                self._write_default(path, issue["file"])
                fixes.append({"action": "created_file", "file": issue["file"]})
            elif issue["type"] == "empty_file":
                path = self._data_dir / issue["file"]
                self._write_default(path, issue["file"])
                fixes.append({"action": "initialized_file", "file": issue["file"]})
            elif issue["type"] in ("invalid_json", "wrong_shape"):
                path = self._data_dir / issue["file"]
                self._write_default(path, issue["file"])
                fixes.append({"action": "healed_file_shape", "file": issue["file"]})
        return fixes


# ============================================================
# Part 3: Autopilot (自维护守护)
# ============================================================

class Autopilot:
    """Autopilot自维护守护"""

    def __init__(self):
        self._data_dir = Path.home() / ".hermes" / "phoenix" / "data"
        self._status_file = self._data_dir / "autopilot_status.json"
        self._running = False

    def run_cycle(self) -> Dict:
        """运行一个维护周期"""
        results = {
            "memories_synced": 0,
            "entities_extracted": 0,
            "kg_updated": 0,
            "gc_run": False,
        }
        results["memories_synced"] = self._sync_memories()
        results["entities_extracted"] = self._extract_entities()
        results["kg_updated"] = self._update_kg()
        gc = GarbageCollector()
        gc.collect()
        results["gc_run"] = True
        self._save_status(results)
        return results

    def _sync_memories(self) -> int:
        """同步记忆"""
        ext_path = self._data_dir / "extracted_memories.json"
        ltm_path = self._data_dir / "long_term_memory.json"
        if not ext_path.exists():
            return 0
        try:
            extracted = json.loads(ext_path.read_text())
            ltm = json.loads(ltm_path.read_text()) if ltm_path.exists() else []
            synced = 0
            for mem in extracted:
                if not mem.get("applied", False):
                    ltm.append({
                        "content": mem.get("content", ""),
                        "category": mem.get("category", ""),
                        "importance": mem.get("importance", 3),
                        "synced_at": time.time(),
                    })
                    mem["applied"] = True
                    synced += 1
            if synced > 0:
                ext_path.write_text(json.dumps(extracted, ensure_ascii=False, indent=2))
                ltm_path.write_text(json.dumps(ltm, ensure_ascii=False, indent=2))
            return synced
        except Exception:
            return 0

    def _extract_entities(self) -> int:
        """从记忆中提取实体"""
        ext_path = self._data_dir / "extracted_memories.json"
        if not ext_path.exists():
            return 0
        try:
            memories = json.loads(ext_path.read_text())
            count = 0
            for mem in memories:
                content = mem.get("content", "")
                if content:
                    from phoenix.memory.unified_memory import self_wiring_kg
                    result = self_wiring_kg.wire(content)
                    count += result.get("entities_added", 0)
            return count
        except Exception:
            return 0

    def _update_kg(self) -> int:
        """更新知识图谱"""
        from phoenix.memory.unified_memory import self_wiring_kg
        stats = self_wiring_kg.stats()
        return stats.get("entities", 0)

    def _save_status(self, results: Dict):
        status = {"last_run": time.time(), "results": results}
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._status_file.write_text(json.dumps(status, ensure_ascii=False, indent=2))

    def get_status(self) -> Dict:
        try:
            if self._status_file.exists():
                return json.loads(self._status_file.read_text())
        except Exception as exc:
            _ = exc
        return {"last_run": None, "results": {}}


# ============================================================
# 模块级单例
# ============================================================
gc = GarbageCollector()
health_checker = HealthChecker()
autopilot = Autopilot()
