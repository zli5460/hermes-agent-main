"""不死鸟 Phoenix V5.1 — 统一子agent路由器

用户的要求：两条路同时打通
- 方式1: Nous Portal API（ClaudeExecutor）- 纯文本任务
- 方式2: Claude Code CLI（ClaudeCodeExecutor）- 代码/文件任务

自动根据任务类型选择最合适的执行方式。
"""

import logging
from typing import Optional, Dict

logger = logging.getLogger("phoenix.router.unified_subagent")


# 任务类型 → 执行器映射
TASK_EXECUTOR_MAP = {
    # 代码相关任务 → Claude Code CLI（能读写文件、跑命令）
    "code_scan": "claude_code_cli",      # 扫描代码库
    "code_review": "claude_code_cli",    # 代码审查
    "code_write": "claude_code_cli",     # 写代码
    "code_refactor": "claude_code_cli",  # 重构
    "file_ops": "claude_code_cli",       # 文件操作

    # 纯推理/分析 → Nous Portal API（快，便宜）
    "reasoning": "nous_api",
    "analysis": "nous_api",
    "chat": "nous_api",
    "summarize": "nous_api",
    "translate": "nous_api",
}

# 任务类型 → 模型映射
TASK_MODEL_MAP = {
    "code_scan": {"cli": "sonnet", "api": "anthropic/claude-sonnet-4.6"},
    "code_review": {"cli": "opus", "api": "anthropic/claude-opus-4.7"},
    "code_write": {"cli": "sonnet", "api": "anthropic/claude-sonnet-4.6"},
    "code_refactor": {"cli": "opus", "api": "anthropic/claude-opus-4.7"},
    "file_ops": {"cli": "sonnet", "api": "anthropic/claude-sonnet-4.6"},
    "reasoning": {"cli": "opus", "api": "anthropic/claude-opus-4.7"},
    "analysis": {"cli": "sonnet", "api": "anthropic/claude-sonnet-4.6"},
    "chat": {"cli": "haiku", "api": "xiaomi/mimo-v2.5"},
    "summarize": {"cli": "haiku", "api": "xiaomi/mimo-v2.5"},
    "translate": {"cli": "haiku", "api": "xiaomi/mimo-v2.5"},
}


def classify_task(task: str) -> str:
    """
    分类任务类型

    规则：
    - 扫描/检查/review → code_scan/code_review
    - 写/修改/重构 → code_write/code_refactor
    - 分析/推理 → reasoning/analysis
    - 其他 → chat
    """
    task_lower = task.lower()

    # 代码扫描/检查类
    if any(kw in task_lower for kw in ["扫描", "检查", "scan", "审计", "找bug", "找问题"]):
        return "code_scan"

    # 代码审查类
    if any(kw in task_lower for kw in ["review", "审查", "评审", "code review"]):
        return "code_review"

    # 代码写作类
    if any(kw in task_lower for kw in ["写代码", "实现", "写个", "创建", "生成代码", "帮我写", "写一个"]):
        if any(kw in task_lower for kw in ["函数", "程序", "脚本", "爬虫", "API", "接口"]):
            return "code_write"

    # 重构类
    if any(kw in task_lower for kw in ["重构", "refactor", "优化代码", "改代码"]):
        return "code_refactor"

    # 文件操作类
    if any(kw in task_lower for kw in ["读文件", "改文件", "修改文件", "文件操作"]):
        return "file_ops"

    # 推理类
    if any(kw in task_lower for kw in ["深度分析", "推理", "论证", "为什么"]):
        return "reasoning"

    # 分析类
    if any(kw in task_lower for kw in ["分析", "对比", "比较"]):
        return "analysis"

    # 翻译类
    if any(kw in task_lower for kw in ["翻译", "translate"]):
        return "translate"

    # 汇总类
    if any(kw in task_lower for kw in ["总结", "汇总", "summarize"]):
        return "summarize"

    return "chat"


def route_subagent_unified(task: str, force_executor: str = None,
                            workdir: str = None) -> Dict:
    """
    统一子agent路由（V4.7）

    Args:
        task: 任务描述
        force_executor: 强制指定执行器（"claude_code_cli"或"nous_api"）
        workdir: 工作目录（CLI模式使用）

    Returns:
        {
            "executor": "claude_code_cli" | "nous_api",
            "model": str,
            "task_type": str,
            "reason": str,
            "result": dict,  # 实际执行结果
        }
    """
    task_type = classify_task(task)
    executor_type = force_executor or TASK_EXECUTOR_MAP.get(task_type, "nous_api")
    model_cfg = TASK_MODEL_MAP.get(task_type, {"cli": "sonnet", "api": "xiaomi/mimo-v2.5"})

    logger.info("路由: task_type=%s → executor=%s", task_type, executor_type)

    result = None
    model = None

    if executor_type == "claude_code_cli":
        # 方式2：Claude Code CLI
        try:
            from executor.claude_code_executor import claude_code_executor
            if not claude_code_executor.is_available():
                logger.warning("Claude Code CLI不可用，降级到Nous API")
                executor_type = "nous_api"
            else:
                model = model_cfg["cli"]
                if task_type == "code_scan":
                    result = claude_code_executor.scan_codebase(task, workdir)
                elif task_type == "code_review":
                    result = claude_code_executor.review_code(task, workdir)
                elif task_type in ["code_write", "code_refactor", "file_ops"]:
                    result = claude_code_executor.write_code(task, workdir, model)
                else:
                    result = claude_code_executor.run_print(task, model, workdir)
        except Exception as e:
            logger.error("Claude Code执行失败: %s，降级到Nous API", e)
            executor_type = "nous_api"

    if executor_type == "nous_api" or result is None:
        # 方式1：Nous Portal API
        try:
            from executor.claude_executor import claude_executor
            model = model_cfg["api"]
            result = claude_executor.run(task, model=model)
        except Exception as e:
            logger.error("Nous API执行失败: %s", e)
            result = {"success": False, "output": str(e), "model": model}

    return {
        "executor": executor_type,
        "model": model,
        "task_type": task_type,
        "reason": f"任务类型={task_type}，选择{executor_type}（模型={model}）",
        "result": result,
    }
