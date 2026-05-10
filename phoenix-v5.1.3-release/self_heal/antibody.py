"""
不死鸟 Phoenix V5.1 — 抗体库

核心理念：错误不是成本，是疫苗。
每次出错 → 生成抗体 → 下次自动免疫 → 系统变强

抗体类型：
- 错误抗体：API失败/超时 → 自动重试+降级策略
- 误判抗体：路由选错模型 → 记录修正
- 效率抗体：某操作找到了更快方式 → 记录优化
- 用户抗体：用户纠错 → 记录正确做法
"""

import json
import time
import hashlib
import logging
from pathlib import Path
from dataclasses import dataclass, field, fields, asdict
from typing import Optional

_log = logging.getLogger("phoenix.antibody")


@dataclass
class Antibody:
    """抗体"""
    id: str = ""                        # 唯一标识
    trigger: str = ""                   # 触发条件（错误信息/模式）
    trigger_type: str = ""              # 类型: error/misjudge/efficiency/user_correction
    action: str = ""                    # 抗体动作（遇到时怎么做）
    description: str = ""               # 人类可读描述
    created_at: float = 0.0
    applied_count: int = 0              # 被应用次数
    success_count: int = 0              # 成功次数
    last_applied: float = 0.0
    active: bool = True

    def __post_init__(self):
        if not self.id:
            self.id = hashlib.md5(
                f"{self.trigger_type}:{self.trigger}".encode()
            ).hexdigest()[:12]
        if not self.created_at:
            self.created_at = time.time()

    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.applied_count == 0:
            return 0.0
        return self.success_count / self.applied_count

    @property
    def is_reliable(self) -> bool:
        """是否可靠（应用3次以上且成功率>50%）"""
        return self.applied_count >= 3 and self.success_rate > 0.5

    def to_dict(self) -> dict:
        return asdict(self)


class AntibodyLibrary:
    """
    抗体库

    用法:
        lib = AntibodyLibrary()

        # 生成抗体
        lib.generate(
            trigger="Connection timeout to inference-api.nousresearch.com",
            trigger_type="error",
            action="fallback_to_backup_model",
            description="Nous API超时时降级到备用模型",
        )

        # 检查是否有抗体
        antibody = lib.match("Connection timeout to inference-api.nousresearch.com")
        if antibody:
            print(f"有抗体！执行: {antibody.action}")

        # 报告效果
        lib.report_result(antibody.id, success=True)
    """

    # 内置抗体（不死鸟出厂自带的免疫力）
    BUILTIN_ANTIBODIES = [
        {
            "trigger": "rate limit",
            "trigger_type": "error",
            "action": "wait_and_retry:30s",
            "description": "API限流 → 等30秒重试",
        },
        {
            "trigger": "timeout",
            "trigger_type": "error",
            "action": "validate_then_retry_then_fallback_then_report",
            "description": "超时 → 验证 → 重试1次 → 降级到备选模型 → 报告",
        },
        {
            "trigger": "invalid_api_key",
            "trigger_type": "error",
            "action": "switch_provider",
            "description": "API Key无效 → 切换提供商",
        },
        {
            "trigger": "404",
            "trigger_type": "error",
            "action": "ban_bad_target_then_fallback",
            "description": "404 / Not Found → 封禁坏目标并降级",
        },
        {
            "trigger": "model_overloaded",
            "trigger_type": "error",
            "action": "fallback_to_free",
            "description": "模型过载 → 降级到免费模型",
        },
        {
            "trigger": "context_length_exceeded",
            "trigger_type": "error",
            "action": "deep_compress_then_retry",
            "description": "上下文超长 → 深压缩后重试",
        },
    ]

    def __init__(self, antibody_file: Optional[str] = None):
        self._antibodies: dict[str, Antibody] = {}
        self._file = Path(antibody_file) if antibody_file else None

        # 加载内置抗体
        for builtin in self.BUILTIN_ANTIBODIES:
            ab = Antibody(**builtin)
            self._antibodies[ab.id] = ab

        # 加载持久化抗体
        if self._file and self._file.exists():
            self._load()

    def generate(
        self,
        trigger: str,
        trigger_type: str,
        action: str,
        description: str = "",
    ) -> Antibody:
        """
        生成新抗体

        Args:
            trigger: 触发条件（错误信息关键词/模式）
            trigger_type: 类型
            action: 遇到时的处理方式
            description: 描述
        """
        ab = Antibody(
            trigger=trigger,
            trigger_type=trigger_type,
            action=action,
            description=description or f"{trigger_type}: {trigger[:30]}",
        )

        # 去重：相同trigger不重复创建
        for existing in self._antibodies.values():
            if existing.trigger == trigger and existing.trigger_type == trigger_type:
                # 更新已有抗体
                existing.action = action
                existing.description = description
                self._save()
                return existing

        self._antibodies[ab.id] = ab
        self._save()
        return ab

    def match(self, error_message: str) -> Optional[Antibody]:
        """
        匹配抗体

        在错误信息中查找是否有对应抗体
        """
        error_lower = error_message.lower()
        best_match = None
        best_score = 0

        for ab in self._antibodies.values():
            if not ab.active:
                continue
            trigger_lower = ab.trigger.lower()
            if trigger_lower in error_lower:
                # 简单评分：匹配长度 × 成功率
                score = len(trigger_lower) * (ab.success_rate + 0.1)
                if score > best_score:
                    best_score = score
                    best_match = ab

        return best_match

    def report_result(self, antibody_id: str, success: bool):
        """报告抗体应用结果"""
        ab = self._antibodies.get(antibody_id)
        if ab:
            ab.applied_count += 1
            if success:
                ab.success_count += 1
            ab.last_applied = time.time()

            # 连续失败太多 → 停用
            if ab.applied_count >= 5 and ab.success_rate < 0.2:
                ab.active = False

            self._save()

    def get_active(self) -> list[Antibody]:
        """获取所有活跃抗体"""
        return [ab for ab in self._antibodies.values() if ab.active]

    def get_reliable(self) -> list[Antibody]:
        """获取可靠抗体"""
        return [ab for ab in self._antibodies.values() if ab.is_reliable]

    def get_stats(self) -> dict:
        """获取统计"""
        active = self.get_active()
        reliable = self.get_reliable()
        by_type = {}
        for ab in active:
            by_type[ab.trigger_type] = by_type.get(ab.trigger_type, 0) + 1
        return {
            "total": len(self._antibodies),
            "active": len(active),
            "reliable": len(reliable),
            "by_type": by_type,
            "avg_success_rate": f"{sum(ab.success_rate for ab in active) / max(len(active), 1) * 100:.0f}%",
        }

    def _save(self):
        """持久化"""
        if not self._file:
            return
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            data = [ab.to_dict() for ab in self._antibodies.values()]
            self._file.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        except Exception:
            return

    def _load(self):
        """加载 — 逐条加载，跳过无效条目"""
        try:
            data = json.loads(self._file.read_text())
        except Exception as e:
            _log.warning("Failed to read antibody file %s: %s", self._file, e)
            return

        # Dynamically get valid field names from the Antibody dataclass
        valid_fields = {f.name for f in fields(Antibody)}

        loaded = 0
        skipped = 0
        for item in data:
            try:
                # Filter to only known fields — protects against schema drift
                # and Python version differences in dataclass handling
                filtered = {k: v for k, v in item.items() if k in valid_fields}
                ab = Antibody(**filtered)
                self._antibodies[ab.id] = ab
                loaded += 1
            except Exception as e:
                skipped += 1
                _log.warning(
                    "Skipping invalid antibody entry (trigger=%r): %s",
                    item.get("trigger", "?"), e,
                )

        if skipped:
            _log.info("Antibody load complete: %d loaded, %d skipped", loaded, skipped)
