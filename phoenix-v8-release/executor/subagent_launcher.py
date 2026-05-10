"""不死鸟 Phoenix V8 — 子agent启动器（已统一到 subagent_router）

保留此文件仅为向后兼容。新代码请直接使用：
    from router.subagent_router import route_subagent
"""

from router.subagent_router import route_subagent


class SubagentLauncher:
    """委托给 subagent_router.route_subagent"""

    def launch(self, task: str) -> dict:
        route = route_subagent(task)
        primary = route["model"]
        use_claude = "claude" in primary.lower()

        if use_claude:
            try:
                from executor.claude_executor import claude_executor
                result = claude_executor.run(task, model=primary)
                return {"model": primary, "result": result, "source": "claude_executor"}
            except Exception as e:
                return {"model": primary, "error": str(e), "source": "claude_executor_failed"}
        else:
            return {"model": primary, "task": task, "source": "subagent_router"}
