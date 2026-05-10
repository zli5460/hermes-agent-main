"""
不死鸟 Phoenix V8 — 技能按需加载器

最小实现：
- 不预载全部技能
- 按 message / task_type 进行懒加载
- 只返回命中的技能摘要，供 prompt 注入

技能文件约定：
- skills/**/SKILL.md
- 也兼容 skills/*.md
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


_STOPWORDS = {
    "README", "readme", "DESCRIPTION", "description", "inputs", "optimization",
    "colors", "image", "data", "analysis", "report", "template", "guide",
}


def _parse_frontmatter(text: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return meta
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        meta[k.strip().lower()] = v.strip().strip('"').strip("'")
    return meta


@dataclass
class LoadedSkill:
    name: str
    path: str
    summary: str


class SkillLoader:
    _SPECIAL_HINTS = {
        "phoenix-v2-architecture": {"phoenix", "不死鸟", "v2", "v3", "架构", "完整", "质检", "验收", "升级", "模块推进"},
        "phoenix-v2-memory-loop": {"记忆", "闭环", "长期记忆", "prompt注入", "失忆", "自动记忆"},
        "phoenix-v2-state-event": {"状态", "event_stream", "appstate", "gc", "健康摘要", "事件流"},
        "phoenix-v2-self-heal": {"自愈", "抗体", "熔断", "fallback", "恢复", "降级", "进化"},
        "phoenix-v2-routing": {"路由", "模型分发", "模型矩阵", "意图", "分类", "视觉"},
        "phoenix-v2-skill-system": {"技能", "skill", "skills", "按需加载", "prompt注入", "命中"},
    }

    def __init__(self, directory: str, enabled: bool = True, lazy_load: bool = True):
        self._dir = Path(directory).expanduser()
        self._enabled = enabled
        self._lazy_load = lazy_load

    def load_for_message(self, message: str, task_type: str = "", limit: int = 3) -> list[LoadedSkill]:
        if not self._enabled:
            return []
        if not self._dir.exists():
            return []

        candidates = self._discover_skill_files()
        if not candidates:
            return []

        keywords = self._keywords(message, task_type)
        message_l = message.lower()
        phoenix_mode = any(k in {"phoenix", "不死鸟", "v2", "v3"} for k in keywords) or "phoenix" in message_l or "不死鸟" in message
        special_mode = any(token in message_l for token in ["记忆", "闭环", "自愈", "抗体", "状态", "事件流", "gc", "健康摘要", "技能", "skill", "skills", "按需加载"])
        scored: list[tuple[int, Path]] = []
        for path in candidates:
            if phoenix_mode or special_mode:
                path_hint = f"{path.name} {path.parent.name} {' '.join(path.parts)}".lower()
                try:
                    content_hint = path.read_text(encoding="utf-8", errors="ignore")[:1200].lower()
                except Exception:
                    content_hint = ""
                skill_mode = any(k in message_l for k in ["技能", "skill", "skills", "按需加载", "prompt注入", "命中"])
                if "phoenix" not in path_hint and "不死鸟" not in content_hint and not (skill_mode and ("skill" in path_hint or "skills" in path_hint or "skill" in content_hint)):
                    continue
            score = self._score(path, keywords)
            if score > 0:
                scored.append((score, path))

        scored.sort(key=lambda x: x[0], reverse=True)
        loaded: list[LoadedSkill] = []
        for _, path in scored[:limit]:
            loaded.append(self._load_skill(path))
        return loaded

    def to_prompt(self, message: str, task_type: str = "", limit: int = 3) -> str:
        skills = self.load_for_message(message, task_type, limit=limit)
        if not skills:
            return ""

        lines = ["## 命中的技能"]
        for skill in skills:
            lines.append(f"- {skill.name}: {skill.summary[:180]}")
        return "\n".join(lines)

    def _discover_skill_files(self) -> list[Path]:
        paths = list(self._dir.rglob("SKILL.md"))
        paths.extend(p for p in self._dir.rglob("*.md") if p.name != "SKILL.md")
        uniq = []
        seen = set()
        for path in sorted(paths):
            if path not in seen:
                uniq.append(path)
                seen.add(path)
        return uniq

    def _score(self, path: Path, keywords: list[str]) -> int:
        meta = {}
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            content = ""
        meta = _parse_frontmatter(content)
        name = meta.get("name", path.parent.name if path.name == "SKILL.md" else path.stem)
        desc = meta.get("description", "")
        haystack = f"{name} {path.name} {path.parent.name} {path.stem} {desc} {content[:2000]}".lower()
        score = 0
        for kw in keywords:
            if kw and kw.lower() in _STOPWORDS:
                continue
            if kw and kw in haystack:
                score += 1
        if "phoenix" in haystack or "不死鸟" in haystack:
            score += 2
        if path.parent.parts and any("phoenix" in part.lower() for part in path.parent.parts):
            score += 1
        if "phoenix-v2-architecture" in str(path).lower():
            score += 3
        if any(kw in {"完整", "结构", "架构", "质检", "验收", "升级"} for kw in keywords):
            if "phoenix-v2-architecture" in str(path).lower():
                score += 2

        stem = str(path).lower()
        for skill_name, hints in self._SPECIAL_HINTS.items():
            if skill_name in stem:
                if any(kw in hints for kw in keywords):
                    score += 4
        return score

    def _keywords(self, message: str, task_type: str) -> list[str]:
        text = f"{task_type} {message}".lower()
        kws = []
        tokens = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]{2,}", text)
        seed_terms = [
            "记忆", "闭环", "自愈", "抗体", "状态", "事件流", "健康摘要", "技能", "按需加载",
            "路由", "熔断", "降级", "恢复", "进化", "prompt注入", "长期记忆", "知识图谱",
        ]
        for term in seed_terms:
            if term in text and term not in kws:
                kws.append(term)
        for token in tokens:
            token = token.strip()
            if not token:
                continue
            if token in {
                "继续", "补全", "检查", "请", "帮我", "整个", "结构", "目录", "模块", "技能", "任务", "完成", "看看", "一下", "这个", "那个", "怎么做", "如何", "什么", "板块"
            }:
                continue
            if token not in kws:
                kws.append(token)
        return kws[:20]

    def _load_skill(self, path: Path) -> LoadedSkill:
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            content = ""

        summary = self._summarize(content)
        name = path.parent.name if path.name == "SKILL.md" else path.stem
        return LoadedSkill(name=name, path=str(path), summary=summary)

    def _summarize(self, content: str) -> str:
        if not content:
            return ""
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        if not lines:
            return ""
        if lines[0].startswith("---"):
            for line in lines:
                if line.startswith("description:"):
                    return line.split(":", 1)[-1].strip()
        return lines[0][:200]
