"""
不死鸟 Phoenix V8 — 自我进化引擎

核心理念：不是人在训练AI，是AI在进化自己。

进化维度：
1. 路由进化：根据实际效果优化模型选择
2. 压缩进化：根据压缩质量调整策略
3. 记忆进化：根据使用频率淘汰/升级记忆
4. 抗体进化：根据成功率优化抗体库
5. 速度进化：记录并优化响应时间

进化不是一次性的事，是每个session都在发生的持续过程。
"""

import json
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EvolutionEvent:
    """进化事件"""
    dimension: str                      # 进化维度
    description: str                    # 描述
    before: dict = field(default_factory=dict)   # 进化前
    after: dict = field(default_factory=dict)    # 进化后
    impact: float = 0.0                 # 影响程度 (0-1)
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()

    def to_dict(self) -> dict:
        return {
            "dimension": self.dimension,
            "description": self.description,
            "before": self.before,
            "after": self.after,
            "impact": self.impact,
            "timestamp": self.timestamp,
        }


class EvolutionEngine:
    """
    自我进化引擎

    用法:
        evo = EvolutionEngine()

        # 记录一次模型调用效果
        evo.record_model_performance(
            model="gpt-5.4-2",
            task_type="chat",
            latency=1.2,
            cost=0.001,
            user_satisfied=True,
        )

        # 触发进化检查
        improvements = evo.evolve()

        # 获取进化报告
        report = evo.get_report()
    """

    def __init__(self, config=None, evolution_file: Optional[str] = None):
        self._config = config
        self._file = Path(evolution_file) if evolution_file else None
        self._events: list[EvolutionEvent] = []

        # 路由效果追踪
        self._model_performance: dict = {}  # {model:task_type -> {latency, cost, success_rate, count}}

        # 压缩效果追踪
        self._compress_quality: list = []  # [{ratio, quality_score}]

        # 速度追踪
        self._latency_history: list = []

        # 加载历史
        if self._file and self._file.exists():
            self._load()

    def record_model_performance(
        self,
        model: str,
        task_type: str,
        latency: float,
        cost: float,
        success: bool = True,
    ):
        """记录模型调用效果"""
        key = f"{model}:{task_type}"
        if key not in self._model_performance:
            self._model_performance[key] = {
                "latencies": [],
                "costs": [],
                "successes": 0,
                "failures": 0,
            }

        perf = self._model_performance[key]
        perf["latencies"].append(latency)
        perf["costs"].append(cost)
        if success:
            perf["successes"] += 1
        else:
            perf["failures"] += 1

        # 只保留最近100条
        perf["latencies"] = perf["latencies"][-100:]
        perf["costs"] = perf["costs"][-100:]

        self._latency_history.append(latency)

    def record_compression(self, original_size: int, compressed_size: int, quality: float = 0.0):
        """记录压缩效果"""
        ratio = compressed_size / max(original_size, 1)
        self._compress_quality.append({
            "ratio": ratio,
            "quality": quality,
            "saved": original_size - compressed_size,
        })

    def evolve(self) -> list[EvolutionEvent]:
        """
        触发进化检查

        分析所有追踪数据，生成进化建议。
        返回本次发现的进化事件列表。
        """
        events = []

        # 1. 路由进化
        events.extend(self._evolve_routing())

        # 2. 压缩进化
        events.extend(self._evolve_compression())

        # 3. 速度进化
        events.extend(self._evolve_speed())

        self._events.extend(events)
        self._save()

        return events

    def get_best_model_for_task(self, task_type: str) -> Optional[str]:
        """
        根据历史数据推荐最佳模型

        进化的核心输出：不再依赖静态路由表，用数据说话
        """
        best_model = None
        best_score = -1

        for key, perf in self._model_performance.items():
            parts = key.rsplit(":", 1)
            if len(parts) != 2:
                continue
            model, t_type = parts
            if t_type != task_type:
                continue

            total = perf["successes"] + perf["failures"]
            if total < 3:
                continue  # 样本太少

            success_rate = perf["successes"] / total
            avg_latency = sum(perf["latencies"]) / len(perf["latencies"]) if perf["latencies"] else 999
            avg_cost = sum(perf["costs"]) / len(perf["costs"]) if perf["costs"] else 999

            # 评分公式：成功率权重60% + 速度权重20% + 成本权重20%
            latency_score = max(0, 1 - avg_latency / 10)  # 10秒内线性评分
            cost_score = max(0, 1 - avg_cost / 0.1)       # $0.1内线性评分
            score = success_rate * 0.6 + latency_score * 0.2 + cost_score * 0.2

            if score > best_score:
                best_score = score
                best_model = model

        return best_model

    def get_report(self) -> dict:
        """获取进化报告"""
        # 路由效果
        routing_summary = {}
        for key, perf in self._model_performance.items():
            total = perf["successes"] + perf["failures"]
            if total > 0:
                routing_summary[key] = {
                    "calls": total,
                    "success_rate": f"{perf['successes'] / total * 100:.0f}%",
                    "avg_latency": f"{sum(perf['latencies']) / len(perf['latencies']):.2f}s" if perf["latencies"] else "N/A",
                    "avg_cost": f"${sum(perf['costs']) / len(perf['costs']):.4f}" if perf["costs"] else "N/A",
                }

        # 压缩效果
        compress_avg_ratio = 0.0
        compress_total_saved = 0
        if self._compress_quality:
            compress_avg_ratio = sum(c["ratio"] for c in self._compress_quality) / len(self._compress_quality)
            compress_total_saved = sum(c["saved"] for c in self._compress_quality)

        # 速度效果
        avg_latency = 0.0
        if self._latency_history:
            avg_latency = sum(self._latency_history) / len(self._latency_history)

        return {
            "evolution_events": len(self._events),
            "routing_performance": routing_summary,
            "compression": {
                "avg_ratio": f"{compress_avg_ratio:.1%}",
                "total_saved_chars": compress_total_saved,
            },
            "speed": {
                "avg_latency": f"{avg_latency:.2f}s",
                "samples": len(self._latency_history),
            },
            "recent_events": [
                e.to_dict() for e in self._events[-5:]
            ] if self._events else [],
        }

    # ===== 内部进化逻辑 =====

    def _evolve_routing(self) -> list[EvolutionEvent]:
        """路由进化：找出更好的模型分配"""
        events = []

        # 检查每个任务类型的模型表现
        task_models: dict = {}
        for key, perf in self._model_performance.items():
            parts = key.rsplit(":", 1)
            if len(parts) != 2:
                continue
            model, task_type = parts
            total = perf["successes"] + perf["failures"]
            if total < 5:
                continue
            if task_type not in task_models:
                task_models[task_type] = []
            task_models[task_type].append((model, perf, total))

        for task_type, models in task_models.items():
            # 按成功率排序
            models.sort(key=lambda x: x[1]["successes"] / max(x[2], 1), reverse=True)
            if len(models) >= 2:
                best = models[0]
                worst = models[-1]
                best_rate = best[1]["successes"] / best[2]
                worst_rate = worst[1]["successes"] / worst[2]

                if best_rate - worst_rate > 0.2:  # 差距超过20%
                    events.append(EvolutionEvent(
                        dimension="routing",
                        description=f"任务'{task_type}'：{best[0]}比{worst[0]}成功率高{(best_rate - worst_rate) * 100:.0f}%，建议切换",
                        before={"model": worst[0], "success_rate": f"{worst_rate:.0%}"},
                        after={"model": best[0], "success_rate": f"{best_rate:.0%}"},
                        impact=best_rate - worst_rate,
                    ))

        return events

    def _evolve_compression(self) -> list[EvolutionEvent]:
        """压缩进化：调整压缩策略"""
        events = []

        if len(self._compress_quality) < 10:
            return events

        avg_ratio = sum(c["ratio"] for c in self._compress_quality) / len(self._compress_quality)

        if avg_ratio > 0.5:
            events.append(EvolutionEvent(
                dimension="compression",
                description=f"压缩比{avg_ratio:.0%}偏高，建议降低max_lines或提高compress_threshold",
                before={"avg_ratio": f"{avg_ratio:.0%}"},
                after={"suggestion": "tighten thresholds"},
                impact=0.3,
            ))

        return events

    def _evolve_speed(self) -> list[EvolutionEvent]:
        """速度进化：识别并优化慢操作"""
        events = []

        if len(self._latency_history) < 20:
            return events

        recent = self._latency_history[-20:]
        avg = sum(recent) / len(recent)
        slow_count = sum(1 for l in recent if l > avg * 2)

        if slow_count > 5:
            events.append(EvolutionEvent(
                dimension="speed",
                description=f"最近20次调用中有{slow_count}次超过平均延迟2倍，建议检查慢模型",
                before={"avg_latency": f"{avg:.2f}s", "slow_count": slow_count},
                after={"suggestion": "check_slow_models"},
                impact=0.4,
            ))

        return events

    def _save(self):
        """持久化"""
        if not self._file:
            return
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "events": [e.to_dict() for e in self._events[-50:]],  # 只保留最近50条
                "model_performance": self._model_performance,
                "compress_quality": self._compress_quality[-100:],
                "latency_history": self._latency_history[-100:],
            }
            self._file.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        except Exception:
            return

    def _load(self):
        """加载"""
        try:
            data = json.loads(self._file.read_text())
            self._events = [EvolutionEvent(**e) for e in data.get("events", [])]
            self._model_performance = data.get("model_performance", {})
            self._compress_quality = data.get("compress_quality", [])
            self._latency_history = data.get("latency_history", [])
        except Exception:
            return
