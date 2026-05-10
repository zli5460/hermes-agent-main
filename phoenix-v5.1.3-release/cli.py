"""
不死鸟 Phoenix V5.1 — CLI入口

用法：
  python -m phoenix.cli status    # 查看状态
  python -m phoenix.cli evolve    # 触发进化
  python -m phoenix.cli sync      # 同步记忆
  python -m phoenix.cli test      # 运行测试
  python -m phoenix.cli recover   # 启动恢复
  python -m phoenix.cli doctor    # 安装后验收闭环
  python -m phoenix.cli chat "消息" # 测试对话
"""

import sys
import json
from pathlib import Path

PHOENIX_DIR = Path(__file__).parent
if str(PHOENIX_DIR) not in sys.path:
    sys.path.insert(0, str(PHOENIX_DIR))


def cmd_status():
    """查看不死鸟状态"""
    from phoenix import Phoenix
    p = Phoenix()
    health = p.health_check()
    print(json.dumps(health, indent=2, ensure_ascii=False))


def cmd_evolve():
    """触发进化检查"""
    from phoenix import Phoenix
    p = Phoenix()
    events = p.evolve()
    print(f"⚡ 发现 {len(events)} 个进化事件")
    for e in events:
        print(f"  [{e.dimension}] {e.description}")


def cmd_sync():
    """同步记忆"""
    from integration.cron_sync import cron_sync
    cron_sync()


def cmd_recover():
    """启动恢复"""
    from integration.startup import startup_recover
    startup_recover()


def cmd_test():
    """运行测试"""
    from integration.hermes_bridge import test
    test()


def cmd_doctor():
    """运行安装医生闭环"""
    from doctor import main as doctor_main
    raise SystemExit(doctor_main(["--fix"]))


def cmd_chat(message: str):
    """测试对话"""
    from integration.hermes_bridge import HermesPhoenixBridge
    bridge = HermesPhoenixBridge()
    result = bridge.chat(message)
    print(f"\n📡 模型: {result.model_used}")
    print(f"📋 类型: {result.task_type}")
    print(f"✅ 成功: {result.success}")
    print(f"⏱️ 耗时: {result.latency:.2f}s")
    print(f"\n📝 执行步骤:")
    for step in result.steps:
        print(f"  {step}")
    print(f"\n💬 回复:\n{result.response}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]

    if cmd == "status":
        cmd_status()
    elif cmd == "evolve":
        cmd_evolve()
    elif cmd == "sync":
        cmd_sync()
    elif cmd == "recover":
        cmd_recover()
    elif cmd == "test":
        cmd_test()
    elif cmd == "doctor":
        cmd_doctor()
    elif cmd == "chat":
        if len(sys.argv) < 3:
            print("用法: python cli.py chat '你的消息'")
            return
        cmd_chat(" ".join(sys.argv[2:]))
    else:
        print(f"未知命令: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
