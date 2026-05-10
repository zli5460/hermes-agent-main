"""
不死鸟 Phoenix V8 — 自动化管道

一句话进去 → 全链路自动跑完 → 结果出来
全程无人工干预，出错自动接上。

流程：
用户消息 → 分类 → 路由 → 调模型 → 处理结果 → 压缩 → 返回
         ↓ 出错 ↓
       重试 → 换模型 → 抗体匹配 → 自动修复 → 继续跑
"""

import time
from dataclasses import dataclass


@dataclass
class PipelineResult:
    """管道执行结果"""
    success: bool                       # 是否成功
    response: str = ""                  # 最终回复
    model_used: str = ""                # 实际使用的模型
    task_type: str = ""                 # 任务类型
    fallback_used: bool = False         # 是否用了降级
    retries: int = 0                    # 重试次数
    errors: list = None                 # 错误列表
    latency: float = 0.0               # 总耗时
    cost: float = 0.0                  # 总花费
    tokens_saved: int = 0              # 节省的token
    steps: list = None                 # 执行步骤日志

    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.steps is None:
            self.steps = []

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "response": self.response[:200],
            "model_used": self.model_used,
            "task_type": self.task_type,
            "fallback_used": self.fallback_used,
            "retries": self.retries,
            "errors": self.errors,
            "latency": f"{self.latency:.2f}s",
            "cost": f"${self.cost:.4f}",
            "tokens_saved": self.tokens_saved,
            "steps": self.steps,
        }


class AutoPipeline:
    """
    自动化管道

    一句话进去，全链路自动跑完。

    用法：
        pipeline = AutoPipeline(phoenix_instance)
        result = pipeline.run("帮我写个Python爬虫")
        print(result.response)
    """

    def __init__(self, phoenix):
        """
        Args:
            phoenix: Phoenix 实例
        """
        self._phoenix = phoenix
        self._max_retries = 3

    def run(self, message: str, has_image: bool = False,
            model_callback=None) -> PipelineResult:
        """
        执行全链路自动化

        Args:
            message: 用户消息
            has_image: 是否包含图片
            model_callback: 实际调用模型的回调函数
                签名: callback(model, provider, messages) -> str

        Returns:
            PipelineResult
        """
        start_time = time.time()
        steps = []
        errors = []
        retries = 0
        fallback_used = False
        cost = 0.0
        tokens_saved = 0

        # ===== 第1步：自动提取记忆 =====
        step_start = time.time()
        memories = self._phoenix.extract_memory(message)
        if memories:
            steps.append(f"①记忆提取: 提取了{len(memories)}条 ({time.time()-step_start:.1f}s)")
        else:
            steps.append(f"①记忆提取: 无新记忆 ({time.time()-step_start:.1f}s)")

        # ===== 第2步：自动路由 =====
        step_start = time.time()
        decision = self._phoenix.route(message, has_image)
        steps.append(f"②路由决策: {decision.model} / {decision.task_type} ({time.time()-step_start:.1f}s)")

        # ===== 第3步：检查缓存 =====
        step_start = time.time()
        cached = None
        try:
            from phoenix.executor.response_cache import response_cache
            cached = response_cache.get(message)
        except Exception as exc:
            _ = exc
        if cached:
            steps.append(f"③缓存命中: {len(cached)}字符 ({time.time()-step_start:.1f}s)")
            total_latency = time.time() - start_time
            return PipelineResult(
                success=True, response=cached, model_used="cache",
                task_type=decision.task_type, latency=total_latency,
                steps=steps,
            )
        context = self._phoenix.get_context_for_prompt()
        steps.append(f"③上下文组装: {len(context)}字符 ({time.time()-step_start:.1f}s)")

        # ===== 第4步：调用模型（带自动重试+降级）=====
        # 信用检查：三方欠费时自动切换到主模型
        credit_monitor = CreditMonitor(self._phoenix.config._config)
        if credit_monitor.should_fallback():
            primary_config = credit_monitor.get_primary_model_config()
            if primary_config and primary_config.get("model"):
                notification = credit_monitor.get_notification()
                steps.append(f"④信用检查: {notification[:50]}")
                model = primary_config["model"]
                provider = primary_config.get("provider", "")
                fallback_used = True
                # 标记使用兜底模型
                credit_monitor._status.using_fallback = True
                credit_monitor._save_status()
            else:
                model = decision.model
                provider = decision.provider
        else:
            model = decision.model
            provider = decision.provider
        task_type = decision.task_type
        response = ""
        success = False

        for attempt in range(self._max_retries + 1):
            try:
                step_start = time.time()

                # 检查熔断器（带防死循环保护）
                if not self._phoenix.circuit_manager.is_available(model):
                    steps.append(f"④调用模型: {model} 已熔断，自动降级")
                    fb_model, fb_provider = self._get_fallback(decision, exclude=[model])
                    if fb_model is None:
                        raise RuntimeError(f"所有候选模型均已熔断，无可用 fallback（原模型={model}）")
                    model, provider = fb_model, fb_provider
                    fallback_used = True

                # Step 1: 验证
                verify_note = f"验证模型 {model} / {task_type}"
                steps.append(f"④-1 验证: {verify_note}")

                # 调用模型
                if model_callback:
                    response = model_callback(model, provider, message)
                else:
                    response = f"[模拟回复] 使用{model}处理了: {message[:30]}..."

                # 404 不是普通失败：它代表坏目标，必须立即识别并封禁
                if isinstance(response, str) and response.startswith("[API错误 404]"):
                    raise RuntimeError(response)

                latency = time.time() - step_start

                # Step 4: 报告成功
                self._phoenix.report_model_result(model, task_type, latency, cost, True)

                # Token追踪 + 进化数据写入
                try:
                    from phoenix.security.token_tracker import token_tracker
                    input_tokens = len(message) // 4
                    output_tokens = len(response) // 4 if isinstance(response, str) else 0
                    rec = token_tracker.record(model, input_tokens, output_tokens)
                    cost = rec.get("cost_usd", 0.0)

                    # 写入 state（预算同步）
                    st = self._phoenix.state.get_state()
                    if hasattr(st, "budget"):
                        self._phoenix.state.dispatch("update_budget", {
                            "spent_today": st.budget.spent_today + cost,
                            "spent_month": st.budget.spent_month + cost,
                        })

                    # 写入 evolution（成本进化维度）
                    self._phoenix.evolution.record_model_performance(
                        model=model, task_type=task_type,
                        latency=latency, cost=cost, success=True,
                    )
                except Exception as e:
                    import logging
                    logging.getLogger("phoenix.pipeline").debug("token tracking failed: %s", e)

                steps.append(f"④调用模型: {model} 成功 ({latency:.1f}s, ${cost:.4f})")
                success = True
                break

            except Exception as e:
                retries += 1
                error_msg = str(e)
                errors.append(f"尝试{attempt+1}: {error_msg}")
                steps.append(f"④调用模型: {model} 失败 - {error_msg[:50]}")

                # 报告失败
                self._phoenix.report_model_result(
                    model,
                    task_type,
                    0,
                    0,
                    False,
                    error_message=error_msg,
                    error_status_code=404 if "404" in error_msg else None,
                )

                # 自动处理错误（验证→修复→替代→报告）
                heal_result = self._phoenix.check_and_handle_error(
                    error_msg,
                    context={"model": model, "provider": provider, "task_type": task_type},
                )
                if heal_result["handled"]:
                    steps.append(f"  🛡️ 抗体生效: {heal_result['antibody']}")

                # 自动降级
                if attempt < self._max_retries:
                    model, provider = self._get_fallback(decision)
                    fallback_used = True
                    steps.append(f"  🔄 自动降级到: {model}")
                    continue
                else:
                    response = f"抱歉，所有模型都不可用。错误: {errors[-1]}"
                    steps.append(f"  ❌ 所有重试失败")
                    break

        # ===== 第5步：自动压缩回复 =====
        step_start = time.time()
        original_len = len(response)
        if self._phoenix.micro_compactor.should_compress(response):
            response = self._phoenix.compress_tool_result(response, "auto_response")
            tokens_saved = (original_len - len(response)) // 4
            steps.append(f"⑤回复压缩: {original_len}→{len(response)}字符 ({time.time()-step_start:.1f}s)")
        else:
            steps.append(f"⑤回复压缩: 无需压缩 ({time.time()-step_start:.1f}s)")

        # ===== 第6步：自动存储会话记忆 =====
        step_start = time.time()
        self._phoenix.session_memory.set(
            key=f"last_response_{int(time.time())}",
            value=response[:200],
            category="conversation",
            importance=2,
        )
        steps.append(f"⑥记忆存储: 完成 ({time.time()-step_start:.1f}s)")

        # ===== 汇总 =====
        total_latency = time.time() - start_time

        # 存入缓存
        if success and response:
            try:
                from phoenix.executor.response_cache import response_cache
                response_cache.set(message, response)
            except Exception as exc:
                _ = exc

        return PipelineResult(
            success=success,
            response=response,
            model_used=model,
            task_type=task_type,
            fallback_used=fallback_used,
            retries=retries,
            errors=errors,
            latency=total_latency,
            cost=cost,
            tokens_saved=tokens_saved,
            steps=steps,
        )

    def _get_fallback(self, decision, exclude=None) -> tuple:
        """获取降级模型（三层fallback）带防死循环保护"""
        exclude = set(exclude or [])
        model_config = self._phoenix.config.get_model_for_task(decision.task_type)
        provider = model_config.get("provider", "nous")

        # 第2层：fallback
        fallback = model_config.get("fallback")
        if fallback and fallback not in exclude and self._phoenix.circuit_manager.is_available(fallback):
            return fallback, provider

        # 第3层：emergency
        emergency = model_config.get("emergency")
        if emergency and emergency not in exclude and self._phoenix.circuit_manager.is_available(emergency):
            return emergency, provider

        # 全部熔断 → 返回全局兜底（不回退到已熔断的原模型）
        global_fallback = "google/gemini-2.5-flash"
        if global_fallback not in exclude and self._phoenix.circuit_manager.is_available(global_fallback):
            return global_fallback, provider

        # 真的全挂了
        return None, provider
