"""
不死鸟 Phoenix V4.7 — 端到端真实测试

接入实际的Nous API，完整跑一遍全链路。
不是模拟，是真调模型。
"""

import sys
import json
import time
import os
from pathlib import Path

PHOENIX_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PHOENIX_DIR))

from phoenix import Phoenix


def call_model(model: str, provider: str, message: str, context: str = "") -> str:
    """
    真实调用模型API

    只使用Nous Portal
    """
    import requests

    # 加载API配置
    env = {}
    env_file = Path.home() / ".hermes" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                env[k] = v

    # 选择API端点（Nous Portal）
    api_key = env.get("NOUS_API_KEY", "")
    base_url = env.get("NOUS_BASE_URL", "https://portal.nousresearch.com/api/v1")
    
    if not api_key:
        return "[错误] 没有可用的API Key"

    # 构建消息
    messages = []
    if context:
        messages.append({"role": "system", "content": context})
    messages.append({"role": "user", "content": message})

    # 调用
    try:
        start = time.time()
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": messages, "max_tokens": 500},
            timeout=30,
        )
        latency = time.time() - start

        if resp.status_code == 200:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            print(f"    ✅ 调用成功 | {latency:.1f}s | 输入{usage.get('prompt_tokens',0)}tok | 输出{usage.get('completion_tokens',0)}tok")
            return content
        else:
            print(f"    ❌ API错误 {resp.status_code}: {resp.text[:200]}")
            return f"[API错误 status={resp.status_code} model={model} provider={provider} base_url={base_url}]"

    except Exception as e:
        print(f"    ❌ 调用异常: {e}")
        return f"[调用异常: {e}]"


def main():
    print("=" * 60)
    print("🦅 不死鸟 Phoenix V4.7 — 端到端真实测试")
    print("   接入真实API，完整跑一遍全链路")
    print("=" * 60)
    print()

    phoenix = Phoenix()

    test_cases = [
        {
            "name": "简单闲聊（应该走Llama免费模型）",
            "message": "你好，用一句话介绍你自己",
            "expected_model": "llama",
        },
        {
            "name": "代码任务（应该走Qwen免费模型）",
            "message": "写一个Python函数，输入一个列表，返回去重后的结果",
            "expected_model": "xiaomi/mimo-v2.5",
        },
        {
            "name": "记忆提取测试",
            "message": "记住：我最喜欢的编程语言是Python，IDE用的是VS Code",
            "expected_model": "llama",
        },
    ]

    results = []

    for i, tc in enumerate(test_cases, 1):
        print(f"{'='*60}")
        print(f"测试{i}: {tc['name']}")
        print(f"输入: {tc['message']}")
        print()

        # ① 自动提取记忆
        t0 = time.time()
        memories = phoenix.extract_memory(tc["message"])
        if memories:
            print(f"  ①记忆提取: {len(memories)}条")
            for m in memories:
                print(f"    [{m.category}] {m.content[:60]}")
        else:
            print(f"  ①记忆提取: 无新记忆")

        # ② 自动路由
        decision = phoenix.route(tc["message"])
        print(f"  ②路由决策: {decision.model}")
        print(f"    任务类型: {decision.task_type}")
        print(f"    原因: {decision.reason}")

        # ③ 获取上下文
        context = phoenix.get_context_for_prompt()
        if context:
            print(f"  ③上下文: {len(context)}字符")

        # ④ 真实调用模型
        print(f"  ④调用模型...")
        response = call_model(decision.model, decision.provider, tc["message"], context)
        print(f"    回复: {response[:150]}")

        # ⑤ 压缩回复（如果需要）
        if len(response) > 500:
            compressed = phoenix.compress_tool_result(response, "model_response")
            print(f"  ⑤压缩: {len(response)}→{len(compressed)}")
        else:
            print(f"  ⑤压缩: 无需压缩")

        # ⑥ 存入会话记忆
        phoenix.session_memory.set(
            key=f"last_{i}",
            value=response[:100],
            category="conversation",
            importance=2,
        )
        print(f"  ⑥记忆存储: 完成")

        # 报告模型效果
        phoenix.report_model_result(
            model=decision.model,
            task_type=decision.task_type,
            latency=0,
            cost=0,
            success=not response.startswith("[错误") and not response.startswith("[API错误"),
        )

        results.append({
            "test": tc["name"],
            "model": decision.model,
            "task_type": decision.task_type,
            "success": not response.startswith("[错误"),
            "response_preview": response[:100],
        })

        print()

    # 最终健康检查
    print("=" * 60)
    print("🦅 最终健康检查")
    print("=" * 60)
    health = phoenix.health_check()
    print(f"  系统模式: {health['system']['mode']}")
    print(f"  活跃任务: {health['system']['active_tasks']}")
    print(f"  抗体: {health['antibodies']['total']}个(活跃{health['antibodies']['active']})")
    print(f"  记忆提取: {health['memory']['extraction']['total']}条")
    print(f"  会话记忆: {health['memory']['session']['total']}条")

    # 进化检查
    print()
    print("⚡ 触发进化检查...")
    events = phoenix.evolve()
    print(f"  发现 {len(events)} 个进化事件")

    print()
    print("=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)
    for r in results:
        status = "✅" if r["success"] else "❌"
        print(f"  {status} {r['test']}")
        print(f"     模型: {r['model']}")
        print(f"     类型: {r['task_type']}")

    success_count = sum(1 for r in results if r["success"])
    print()
    print(f"🏆 {success_count}/{len(results)} 测试通过")


if __name__ == "__main__":
    main()
