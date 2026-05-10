"""
Phoenix V5.1 — 失败追踪器 + 超时保护
V4.7: 3次失败求助
V4.6: 新增超时保护 + 循环检测（来源：主控Agent投喂手册V7 + Hermes 25个坑）

超时保护规则：
- 单次执行超过30分钟：强制汇报
- 单次执行超过60分钟：暂停执行，等待用户确认
- 连续失败3次同一步骤：触发汇报，不再自行尝试
- 同一模式循环3次：强制跳出
"""

import time
from typing import Dict, Optional, List
from datetime import datetime, timedelta


class FailureTracker:
    """失败追踪器 + 超时保护（V4.6升级）"""
    
    def __init__(self, threshold: int = 3):
        self.threshold = threshold
        self._failures: Dict[str, Dict] = {}
        self._task_start: Optional[float] = None
        self._mode_history: List[str] = []  # V4.6: 模式循环检测
        self._max_mode_history = 10
    
    def record_failure(self, error: str, context: Dict = None) -> Dict:
        """记录失败"""
        pattern = self._extract_pattern(error)
        
        if pattern not in self._failures:
            self._failures[pattern] = {
                "count": 0, "first": time.time(), "last": time.time(),
                "history": [],
            }
        
        self._failures[pattern]["count"] += 1
        self._failures[pattern]["last"] = time.time()
        self._failures[pattern]["history"].append({
            "time": datetime.now().isoformat(),
            "error": error[:100],
        })
        
        count = self._failures[pattern]["count"]
        
        return {
            "pattern": pattern,
            "count": count,
            "should_ask_user": count >= self.threshold,
            "message": f"同一问题已失败{count}次，建议向用户求助" if count >= self.threshold else None,
        }
    
    def record_success(self, error: str):
        """记录成功（重置计数）"""
        pattern = self._extract_pattern(error)
        if pattern in self._failures:
            del self._failures[pattern]
    
    # ===== V4.6: 超时保护 =====
    
    def start_task(self):
        """开始任务计时"""
        self._task_start = time.time()
    
    def check_timeout(self) -> Dict:
        """
        检查超时状态
        
        Returns:
            {"status": "ok"|"warning"|"critical", "elapsed_min": float, "action": str}
        """
        if not self._task_start:
            return {"status": "ok", "elapsed_min": 0, "action": "无计时"}
        
        elapsed = time.time() - self._task_start
        elapsed_min = elapsed / 60
        
        if elapsed_min >= 60:
            return {
                "status": "critical",
                "elapsed_min": round(elapsed_min, 1),
                "action": "暂停执行，等待用户确认继续",
            }
        elif elapsed_min >= 30:
            return {
                "status": "warning",
                "elapsed_min": round(elapsed_min, 1),
                "action": "强制汇报当前进度",
            }
        
        return {"status": "ok", "elapsed_min": round(elapsed_min, 1), "action": "继续执行"}
    
    # ===== V4.6: 循环检测 =====
    
    def record_mode(self, mode: str) -> Dict:
        """
        记录执行模式，检测循环
        
        Args:
            mode: 当前执行模式（如 "thinking", "tool_call", "retry"）
        
        Returns:
            {"loop_detected": bool, "repeat_count": int, "action": str}
        """
        self._mode_history.append(mode)
        if len(self._mode_history) > self._max_mode_history:
            self._mode_history = self._mode_history[-self._max_mode_history:]
        
        # 检测同一模式连续出现3次
        if len(self._mode_history) >= 3:
            last_3 = self._mode_history[-3:]
            if last_3[0] == last_3[1] == last_3[2]:
                return {
                    "loop_detected": True,
                    "repeat_count": 3,
                    "mode": mode,
                    "action": f"检测到同一模式'{mode}'循环3次，强制跳出并汇报",
                }
        
        return {
            "loop_detected": False,
            "repeat_count": self._mode_history.count(mode),
            "mode": mode,
            "action": "继续执行",
        }
    
    def clear_mode_history(self):
        """清除模式历史（任务完成后调用）"""
        self._mode_history.clear()
    
    # ===== 兼容旧API =====
    
    def _extract_pattern(self, error: str) -> str:
        """提取错误模式"""
        return error[:50].strip().lower()
    
    def get_stats(self) -> Dict:
        """获取统计"""
        return {
            "tracked_patterns": len(self._failures),
            "patterns": {k: v["count"] for k, v in self._failures.items()},
            "task_elapsed_min": round((time.time() - self._task_start) / 60, 1) if self._task_start else 0,
            "mode_history": self._mode_history[-5:],
        }


failure_tracker = FailureTracker()
