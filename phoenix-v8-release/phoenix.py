"""
🦅 不死鸟 Phoenix V8 — 主入口

一个文件启动整个不死鸟系统。

用法:
    from phoenix.phoenix import Phoenix
    phoenix = Phoenix()
    response = phoenix.chat("你好")
"""

import sys
import time
import json
import re
import threading
from pathlib import Path
from typing import Optional

# 添加phoenix目录到路径
PHOENIX_DIR = Path(__file__).parent
sys.path.insert(0, str(PHOENIX_DIR))

from core.state import AppStateManager, PhoenixState, SystemMode
from core.task import TaskManager, TaskType, TaskStatus
from core.config import PhoenixConfig
from memory.memory_system import MemorySystem
from router.router import Router as V45Router, TaskSignature
from executor.task_decomposer import decompose_task
from executor.task_pre_approval import TaskPreApprovalSystem
from core.cost_monitor import CostMonitor
from core.god_mode import GodMode
from core.golden_principles import GoldenPrinciples
from router.engine import RouterEngine, RouteDecision
from executor.micro_compact import MicroCompactor
from executor.deep_compact import DeepCompactor
from executor.circuit_breaker import CircuitBreakerManager
from executor.skill_loader import SkillLoader
from memory.sync import PhoenixRecover
from self_heal.antibody import AntibodyLibrary
from self_heal.error_processor import ErrorProcessor
from self_heal.evolution import EvolutionEngine
from self_heal.failure_tracker import FailureTracker
from self_heal.skill_crystallizer import SkillCrystallizer
from self_heal.fault_playbook import FaultPlaybook
from self_heal.unified_maintenance import GarbageCollector, HealthChecker
from security.approval import ApprovalSystem
from security.permission_system import PermissionSystem
from security.token_tracker import TokenTracker
from sandbox.manager import SandboxManager
from workflow.engine import WorkflowEngine
from github.client import GitHubClient
from desktop.controller import DesktopController
from datetime import datetime


class Phoenix:
    """
    不死鸟 Phoenix V8

    五大板块 + 自我进化，一键启动。

    用法:
        # 初始化
        phoenix = Phoenix()

        # 普通对话
        decision = phoenix.route("帮我写个Python爬虫")
        print(f"路由到: {decision.model}")

        # 自动提取记忆
        memories = phoenix.extract_memory("记住：我叫用户")

        # 微压缩
        compressed = phoenix.compress_tool_result(
            "很多行输出...",
            tool_name="terminal"
        )

        # 检查系统健康
        health = phoenix.health_check()
        print(health)

        # 进化报告
        report = phoenix.evolution_report()
    """

    def __init__(self, config_path: str = None):
        # 数据目录
        self._data_dir = Path.home() / ".hermes" / "phoenix" / "data"
        self._data_dir.mkdir(parents=True, exist_ok=True)

        # ① 核心
        self.config = PhoenixConfig(config_path)
        self.state = AppStateManager(str(self._data_dir / "state.json"))
        self.tasks = TaskManager(
            max_concurrent=5,
            task_dir=str(self._data_dir / "tasks"),
        )

        # ② 记忆（V4.6 人脑级三层记忆）
        self.memory_system = MemorySystem(
            base_dir=str(self._data_dir / "memory")
        )

        # ④ 执行（先建熔断器，路由依赖它）
        self.circuit_manager = CircuitBreakerManager(
            self.config.get("executor.circuit_breaker", {})
        )

        # ⑤ 自我净化 + 进化（路由依赖进化引擎）
        self.antibodies = AntibodyLibrary(
            antibody_file=str(self._data_dir / "antibodies.json")
        )
        self.error_processor = ErrorProcessor(
            antibody_library=self.antibodies,
            circuit_breaker=self.circuit_manager,
        )
        self.evolution = EvolutionEngine(
            config=self.config,
            evolution_file=str(self._data_dir / "evolution.json"),
        )
        self.failure_tracker = FailureTracker(threshold=3)
        self.skill_crystallizer = SkillCrystallizer()
        self.fault_playbook = FaultPlaybook(root=str(Path.home()))
        self.garbage_collector = GarbageCollector()
        self.health_checker = HealthChecker()

        # ③ 路由（注入熔断器+进化引擎）
        self.router = RouterEngine(self.config, self.state, self.circuit_manager, self.evolution)

        self.micro_compactor = MicroCompactor(
            max_lines=self.config.get("executor.micro_compact.max_tool_result_lines", 5),
            compress_threshold=self.config.get("executor.micro_compact.compress_threshold", 500),
        )
        self.skill_loader = SkillLoader(
            directory=self.config.get("skills.directory", "~/.hermes/skills"),
            enabled=self.config.get("skills.enabled", True),
            lazy_load=self.config.get("skills.lazy_load", True),
        )

        # ===== V4.6 新增模块 =====
        # V4.6双维度路由器
        try:
            self.v45_router = V45Router()
        except ImportError as e:
            self._log(f"⚠️ V4.6路由器模块未找到: {e}")
            self.v45_router = None
        except Exception as e:
            self._log(f"❌ V4.6路由器初始化异常: {e}")
            self.v45_router = None

        # 成本监控
        try:
            self.cost_monitor = CostMonitor(self._data_dir)
        except Exception as e:
            self._log(f"⚠️ 成本监控初始化失败: {e}")
            self.cost_monitor = None

        # 大神模式（依赖cost_monitor）
        try:
            self.god_mode = GodMode(self.cost_monitor) if self.cost_monitor else None
        except Exception as e:
            self._log(f"⚠️ 大神模式初始化失败: {e}")
            self.god_mode = None

        # 黄金原则
        try:
            self.principles = GoldenPrinciples()
        except Exception as e:
            self._log(f"⚠️ 黄金原则初始化失败: {e}")
            self.principles = None

        # 崩溃恢复
        try:
            self.recovery = PhoenixRecover(data_dir=str(self._data_dir))
        except Exception as e:
            self._log(f"⚠️ 崩溃恢复初始化失败: {e}")
            self.recovery = None

        # 深度压缩
        try:
            self.deep_compactor = DeepCompactor(
                context_threshold_tokens=self.config.get("executor.deep_compact.threshold", 4000),
                keep_last_n=self.config.get("executor.deep_compact.keep_last_n", 3),
                summary_max_tokens=self.config.get("executor.deep_compact.summary_max", 500),
            )
        except Exception as e:
            self._log(f"⚠️ 深度压缩初始化失败: {e}")
            self.deep_compactor = None

        # 任务预审批
        try:
            self.pre_approval = TaskPreApprovalSystem()
        except Exception as e:
            self._log(f"⚠️ 预审批初始化失败: {e}")
            self.pre_approval = None

        # ⑥ 安全板块
        try:
            self.approval = ApprovalSystem()
        except Exception:
            self.approval = None
        try:
            self.permissions = PermissionSystem()
        except Exception:
            self.permissions = None
        try:
            self.token_tracker = TokenTracker()
        except Exception:
            self.token_tracker = None

        # ⑦ 沙箱/工作流/GitHub/桌面（可选板块）
        try:
            self.sandbox_manager = SandboxManager()
        except Exception:
            self.sandbox_manager = None
        try:
            self.workflow_engine = WorkflowEngine()
        except Exception:
            self.workflow_engine = None
        try:
            self.github = GitHubClient()
        except Exception:
            self.github = None
        try:
            self.desktop = DesktopController()
        except Exception:
            self.desktop = None

        # 启动日志
        self._log("🦅 不死鸟 Phoenix V8 启动")
        self._log(f"   数据目录: {self._data_dir}")
        self._log(f"   抗体数量: {self.antibodies.get_stats()['total']}")
        self._log(f"   配置验证: {self.config.validate() or '✅ 通过'}")
        _ms = self.memory_system.get_stats()
        self._log(f"   记忆: 事实{_ms['facts']}条 纠正{_ms['corrections']}条 项目{_ms['projects']}个")

        # V4: 交互计数器+自动进化+适配器
        self._interaction_count = 0
        self._evolve_lock = threading.Lock()
        self._auto_run_adapter()

        # 启动后台定时任务（自动进化）
        self._auto_evolve_enabled = self.config.get("evolution.auto_evolve_enabled", True)
        self._auto_evolve_interval = self.config.get("evolution.auto_evolve_interval", 3600)  # 默认1小时
        if self._auto_evolve_enabled:
            self._start_auto_evolve_task()
            self._log(f"   自动进化: 已启动 (间隔{self._auto_evolve_interval}秒)")

    # ===== 核心接口 =====

    def route(self, message: str, has_image: bool = False,
              force_model: str = None, prompt_fn=None) -> RouteDecision:
        """路由决策（含大神/真神确认流程）"""
        decision = self.router.route(message, has_image, force_model)

        # 深度/大神/真神模式确认流程
        if decision.task_type in ("deep", "god", "super_god") and self.god_mode:
            # 预估成本
            estimated_cost = 5.0 if decision.task_type == "god" else 10.0
            complexity = 9 if decision.task_type == "god" else 10
            
            if self.god_mode.should_trigger(estimated_cost, complexity):
                from core.god_mode import GodModeRequest
                request = GodModeRequest(
                    task_description=message[:100],
                    model=decision.model,
                    estimated_input_tokens=2000,
                    estimated_output_tokens=4000,
                    estimated_cost=estimated_cost,
                    estimated_time_minutes=2 if decision.task_type == "god" else 5,
                    reason=f"{'大神' if decision.task_type == 'god' else '真神'}模式：{decision.reason}",
                )
                
                # 请求用户确认
                approval = self.god_mode.request_approval(request, prompt_fn)
                
                if approval == "cancelled":
                    # 用户取消，降级到日常模式
                    self._log("⚠️ 用户取消大神/真神模式，降级到日常模式")
                    decision = self.router.route(message, has_image, force_model)
                    decision.reason = "用户取消，降级到日常模式"
                
                elif approval == "downgrade":
                    # 用户选择降级
                    downgrade_model = self.god_mode.get_downgrade_model(decision.model)
                    self._log(f"⚠️ 用户选择降级到 {downgrade_model}")
                    decision.model = downgrade_model
                    decision.reason = f"用户选择降级到 {downgrade_model}"
        
        # 记录路由任务
        task = self.tasks.create(
            TaskType.ROUTING,
            description=f"路由: {message[:30]}",
            input_data={"message": message[:100], "has_image": has_image},
        )
        self.tasks.start(task.id, model=decision.model, provider=decision.provider)
        self.tasks.complete(task.id, output={"model": decision.model, "task_type": decision.task_type})

        # 更新状态
        self.state.dispatch("update_model", {
            "model": decision.model,
            "provider": decision.provider,
        })

        return decision

    def extract_memory(self, message: str, role: str = "user"):
        """自动提取记忆（V4.6 MemorySystem）"""
        try:
            result = self.memory_system.process_message(role, message)
            if result:
                self._log(f"🧠 记忆提取: {result}")
            return result
        except Exception as e:
            self._log(f"⚠️ 记忆提取失败: {e}")
            return None

    def compress_tool_result(self, content: str, tool_name: str = "") -> str:
        """微压缩工具结果"""
        if not self.micro_compactor.should_compress(content):
            return content

        compressed = self.micro_compactor.compress(content, tool_name)
        stats = self.micro_compactor.get_stats(content, compressed)

        # 更新压缩统计
        self.state.dispatch("update_compress", {
            "total_compressions": self.state.get_state().compress_stats.total_compressions + 1,
            "tokens_saved": self.state.get_state().compress_stats.tokens_saved + stats["chars_saved"] // 4,
            "micro_compact_count": self.state.get_state().compress_stats.micro_compact_count + 1,
        })

        # 记录压缩效果到进化引擎
        self.evolution.record_compression(
            original_size=len(content),
            compressed_size=len(compressed),
        )

        return compressed

    def report_model_result(self, model: str, task_type: str, latency: float,
                            cost: float, success: bool, error_message: str = "",
                            error_status_code: Optional[int] = None):
        """报告模型调用结果（供外部集成调用）"""
        # 404 / model not found = 坏目标，直接封禁，避免反复撞墙
        if not success and self._is_bad_target(error_message, error_status_code):
            self.state.dispatch("circuit_trip", {"model": model})
            self.state.dispatch("emit_event", {
                "kind": "model_error",
                "source": "phoenix",
                "action": "circuit_trip_404",
                "payload": {"model": model, "task_type": task_type, "error": error_message[:200], "status_code": error_status_code},
                "level": "warning",
            })

        # 熔断器
        self.circuit_manager.report(model, success)

        # 预算
        state = self.state.get_state()
        self.state.dispatch("update_budget", {
            "spent_today": state.budget.spent_today + cost,
            "spent_month": state.budget.spent_month + cost,
        })

        # 进化引擎
        self.evolution.record_model_performance(
            model=model,
            task_type=task_type,
            latency=latency,
            cost=cost,
            success=success,
        )

        # 如果成功 → 技能结晶（记住成功路径）
        if success:
            try:
                self.skill_crystallizer.crystallize(
                    task=f"{task_type}:{model}",
                    steps=[f"model={model}", f"task={task_type}", f"latency={latency:.1f}s"],
                    result=f"success, cost=${cost:.4f}",
                    success=True,
                )
            except Exception as exc:
                _ = exc

        # 如果失败 → 检查是否有抗体
        if not success:
            self._try_antibody(model, task_type, error_message)

        # 统一事件流记录
        self.state.dispatch("event_stream", {
            "type": "model_result",
            "content": {
                "model": model,
                "task_type": task_type,
                "latency": latency,
                "cost": cost,
                "success": success,
            },
            "max_len": self.config.get("gc.event_history_max", 200),
        })

        # 路由统计更新
        route_state = self.state.get_state()
        self.state.dispatch("update_route", {
            "total_requests": route_state.route_stats.total_requests + 1,
        })

    def check_and_handle_error(self, error_message: str, context: dict = None) -> dict:
        """
        检查错误并自动处理

        返回: {"handled": bool, "action": str, "antibody": str}
        """
        context = context or {}

        # ★ 失败追踪：同一错误出现3次→升级处理
        ft_result = self.failure_tracker.record_failure(error_message)
        if ft_result.get("should_ask_user"):
            self._log(f"⚠️ 同一错误已失败{ft_result['count']}次，建议向用户求助")

        # 404 / model not found：坏目标，先封禁再谈修复
        if self._is_bad_target(error_message, context.get("status_code")):
            model = context.get("model", "")
            if model:
                self.state.dispatch("circuit_trip", {"model": model})
            self.state.dispatch("evolution_event", {"type": "bad_target_banned"})
            return {
                "handled": True,
                "action": "ban_bad_target_then_fallback",
                "antibody": f"404坏目标已封禁: {model or 'unknown'}",
            }

        # ★ 走 ErrorProcessor 4步法（验证→重试→替代→抗体）
        proc_result = self.error_processor.process_error(error_message, context)

        # 记录步骤到事件流
        self.state.dispatch("event_stream", {
            "type": "error_processed",
            "content": {"steps": proc_result["steps"], "action": proc_result["action"]},
            "max_len": self.config.get("gc.event_history_max", 200),
        })

        if proc_result["handled"]:
            self.failure_tracker.record_success(error_message)  # 成功修复→重置计数
            self.state.dispatch("evolution_event", {"type": "error_auto_healed"})
            return {
                "handled": True,
                "action": proc_result["action"],
                "antibody": f"4步法修复: {proc_result['action']}",
            }

        # Step4已在 ErrorProcessor 内部生成抗体，这里只做事件记录
        self.state.dispatch("evolution_event", {"type": "antibodies_generated"})
        last_step = proc_result["steps"][-1] if proc_result["steps"] else {}
        return {
            "handled": False,
            "action": proc_result["action"],
            "antibody": f"抗体ID: {last_step.get('antibody_id', 'n/a')}",
        }

    def evolve(self) -> list:
        """触发进化检查"""
        events = self.evolution.evolve()
        for event in events:
            self.state.dispatch("evolution_event", {"type": "optimizations_applied"})
            self._log(f"⚡ 进化: {event.description}")
        return events

    def garbage_collect(self) -> dict:
        """执行垃圾回收"""
        result = self.garbage_collector.collect()
        self._log(f"🧹 垃圾回收: 清理{result['memories_cleaned']}条过期记忆, "
                  f"{result['antibodies_cleaned']}个无效抗体, "
                  f"{result['tasks_cleaned']}个过期任务")
        return result

    def _start_auto_evolve_task(self):
        """启动后台自动进化任务"""
        def auto_evolve_loop():
            while self._auto_evolve_enabled:
                time.sleep(self._auto_evolve_interval)
                try:
                    events = self.evolve()
                    if events:
                        self._log(f"🔄 自动进化: 发现{len(events)}个优化点")
                    # 每次进化后执行垃圾回收
                    gc_result = self.garbage_collect()
                    total_cleaned = gc_result['memories_cleaned'] + gc_result['antibodies_cleaned'] + gc_result['tasks_cleaned']
                    if total_cleaned > 0:
                        self._log(f"🧹 自动清理: 回收{total_cleaned}项")
                except Exception as e:
                    self._log(f"⚠️ 自动进化失败: {e}")

        thread = threading.Thread(target=auto_evolve_loop, daemon=True, name="PhoenixAutoEvolve")
        thread.start()
        self._log("✅ 后台自动进化任务已启动")

    def stop_auto_evolve(self):
        """停止自动进化任务"""
        self._auto_evolve_enabled = False
        self._log("⏹️ 后台自动进化任务已停止")

    # ===== 信息接口 =====

    def shutdown(self):
        """会话结束时调用，保存记忆并进化"""
        try:
            # 1. 先垃圾回收
            self.garbage_collect()
            # 2. 保存会话摘要（自动持久化关键工作）
            self.memory_system.save_session_summary(
                key_work=[f"会话结束，共处理{self.state.get_state().route_stats.total_requests}个请求"],
                context="auto_shutdown"
            )
            # 3. 保存记忆
            self.memory_system.clear_short_term()
            self.memory_system.evolve()
            self._log("🦅 不死鸟会话结束，摘要已保存，记忆已进化")
        except Exception as e:
            self._log(f"⚠️ 记忆保存失败: {e}")

    def health_check(self) -> dict:
        """系统健康检查"""
        state_health = self.state.get_health_summary()
        task_stats = self.tasks.get_stats()
        antibody_stats = self.antibodies.get_stats()
        evolution_report = self.evolution.get_report()
        memory_stats = self.memory_system.get_stats()
        maintenance_report = self.health_checker.check()

        return {
            "system": state_health,
            "tasks": task_stats,
            "antibodies": antibody_stats,
            "evolution": evolution_report,
            "memory": memory_stats,
            "maintenance": maintenance_report,
        }

    def evolution_report(self) -> dict:
        """获取进化报告"""
        return self.evolution.get_report()

    def get_context_for_prompt(self, message: str = "") -> str:
        """
        获取应注入到系统prompt的上下文
        
        包括：最近工作记录 + 会话记忆 + 技能上下文
        V4.6: 自动加载最近3天的工作摘要，防止重启后失忆
        """
        parts = []

        # V4.6: 最近工作记录（自动持久化，重启后可恢复）
        recent = self.memory_system.get_recent_summaries(days=3)
        if recent:
            parts.append(recent)

        # V4.6记忆上下文
        mem_ctx = self.memory_system.retrieve_relevant_memory(message) if message else ""
        if mem_ctx:
            parts.append(mem_ctx)

        # 技能按需加载
        current_state = self.state.get_state()
        skill_ctx = self.skill_loader.to_prompt(
            message=message or "",
            task_type=getattr(current_state, "current_task_type", "") or current_state.current_model or "",
            limit=3,
        )
        if skill_ctx:
            parts.append(skill_ctx)

        # V4.6记忆上下文已通过retrieve_relevant_memory获取
        # （无需额外处理unapplied记忆）

        return "\n".join(parts)

    # ===== 内部方法 =====

    def _is_bad_target(self, error_message: str = "", status_code: Optional[int] = None) -> bool:
        """识别坏目标：明确 404 / Not Found / status=404。"""
        if status_code == 404:
            return True
        if not error_message:
            return False
        if "404" in error_message or "Not Found" in error_message:
            return True
        return bool(re.search(r"status\s*=\s*404", error_message, re.IGNORECASE))

    def _try_antibody(self, model: str, task_type: str, actual_error: str = ""):
        """尝试使用抗体处理失败"""
        # Build a combined error string: actual error + synthetic context
        # This ensures built-in antibodies match the real error pattern
        # (e.g. "timeout", "rate limit") while also preserving model context
        error_msg = f"{actual_error} model_failure:{model}:{task_type}"
        result = self.check_and_handle_error(error_msg)
        if result["handled"]:
            self._log(f"🛡️ 抗体生效: {result['antibody']}")

    def _auto_run_adapter(self):
        """启动时自动适配Hermes"""
        try:
            from adapt.scanner import HermesScanner
            from adapt.adapter import HermesAdapter
            scanner = HermesScanner()
            report = scanner.scan()
            adapter = HermesAdapter()
            result = adapter.adapt(report)
            if result.get("adapted"):
                self._log(f"   适配器: 修复 {len(result.get('fixes', []))} 项")
        except Exception as e:
            self._log(f"   适配器: 跳过")

    def trigger_evolve(self, reason="manual"):
        """线程安全触发进化"""
        with self._evolve_lock:
            try:
                if hasattr(self, "evolution") and self.evolution:
                    if hasattr(self.evolution, "evolve"):
                        self.evolution.evolve()
                        return {"ok": True, "reason": reason}
                return {"ok": False, "error": "no evolution engine"}
            except Exception as e:
                return {"ok": False, "error": str(e)}

    def on_interaction(self):
        """每10次触发进化"""
        self._interaction_count += 1
        if self._interaction_count % 10 == 0:
            self.trigger_evolve(reason=f"every_10({self._interaction_count})")

    def _log(self, msg: str):
        """日志"""
        print(f"[Phoenix {time.strftime('%H:%M:%S')}] {msg}")


# ===== 入口 =====

def main():
    """CLI入口"""
    phoenix = Phoenix()
    print("\n🦅 不死鸟 Phoenix V8 已启动")
    print("输入消息开始对话，输入 'health' 查看健康状态")
    print("输入 'evolve' 触发进化检查")
    print("输入 'quit' 退出\n")

    while True:
        try:
            user_input = input("你: ").strip()
            if not user_input:
                continue
            if user_input == "quit":
                break
            if user_input == "health":
                health = phoenix.health_check()
                print(json.dumps(health, indent=2, ensure_ascii=False))
                continue
            if user_input == "evolve":
                events = phoenix.evolve()
                print(f"发现 {len(events)} 个进化事件")
                continue

            # 路由
            decision = phoenix.route(user_input)
            print(f"📡 路由: {decision.model} ({decision.reason})")

            # 自动提取记忆
            memories = phoenix.extract_memory(user_input)
            if memories:
                print(f"🧠 提取了 {len(memories)} 条记忆")

            # 获取上下文
            ctx = phoenix.get_context_for_prompt()
            if ctx:
                print(f"📋 上下文:\n{ctx}")

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"❌ 错误: {e}")

    print("\n🦅 不死鸟结束本次会话")


if __name__ == "__main__":
    main()
