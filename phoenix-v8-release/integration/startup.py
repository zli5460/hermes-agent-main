"""
不死鸟 Phoenix V8 — 启动恢复

hermes启动时调用，自动恢复不死鸟状态。
"""

import sys
import json
from pathlib import Path

PHOENIX_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PHOENIX_DIR))

from memory.sync import PhoenixRecover


def startup_recover():
    """
    启动恢复

    做的事：
    1. 检查数据目录
    2. 加载长期记忆
    3. 恢复系统状态
    4. 加载抗体库
    5. 输出恢复报告
    """
    recover = PhoenixRecover()
    report = recover.recover()

    print("🔄 不死鸟启动恢复")
    if report["recovered"]:
        for r in report["recovered"]:
            print(f"  ✅ {r}")
    if report["failed"]:
        for f in report["failed"]:
            print(f"  ⚠️ {f}")

    return report


if __name__ == "__main__":
    startup_recover()
