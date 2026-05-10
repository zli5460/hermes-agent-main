"""
不死鸟 Phoenix V8 — 第八板块：Hermes自动适配

核心理念：Hermes升级，Phoenix自动跟上，不需要人工干预。

工作流程：
1. Hermes升级后，自动扫描新架构
2. 对比旧版本，找出变化点
3. 分析哪些变化影响Phoenix集成
4. 自动适配（更新hook、路由、配置）
5. 生成适配报告
"""

from .scanner import HermesScanner
from .adapter import HermesAdapter
from .compat_report import CompatReport

__all__ = ["HermesScanner", "HermesAdapter", "CompatReport"]
