#!/usr/bin/env python3
"""
不死鸟 Phoenix — 第八板块：Hermes自动适配 入口

在Hermes升级后运行，自动扫描并适配。

用法:
    python3 -m phoenix.adapt.run
    或
    python3 phoenix/adapt/run.py
"""

import sys
import json
from pathlib import Path

# 添加phoenix到路径
PHOENIX_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PHOENIX_DIR.parent))

from adapt.scanner import HermesScanner
from adapt.adapter import HermesAdapter
from adapt.compat_report import CompatReport


def main():
    """主入口"""
    print("🦅 不死鸟 Phoenix — 第八板块：Hermes自动适配")
    print("=" * 60)
    print()
    
    # 1. 扫描
    print("📡 扫描Hermes架构...")
    scanner = HermesScanner()
    scan_result = scanner.scan()
    
    print(f"   版本: v{scan_result['version']}")
    print(f"   指纹: {scan_result['fingerprint']}")
    print(f"   升级检测: {'是' if scan_result['is_upgrade'] else '否'}")
    print(f"   变化点: {len(scan_result['changes'])}个")
    print(f"   集成点: {len(scan_result['integration_points'])}个类别")
    print()
    
    # 2. 适配
    if scan_result["is_upgrade"]:
        print("🔧 检测到升级，开始自动适配...")
        adapter = HermesAdapter()
        adapt_result = adapter.adapt(scan_result)
        
        print(f"   适配结果: {'成功' if adapt_result['adapted'] else '需手动处理'}")
        print(f"   已修复: {len(adapt_result['fixes'])}个")
        print(f"   需手动: {len(adapt_result['manual_needed'])}个")
        print()
    else:
        adapt_result = {
            "adapted": True,
            "fixes": ["No upgrade detected"],
            "manual_needed": [],
        }
        print("✅ 无需适配（Phoenix与当前Hermes版本兼容）")
        print()
    
    # 3. 生成报告
    print("📄 生成兼容性报告...")
    reporter = CompatReport()
    report_text = reporter.generate(scan_result, adapt_result)
    
    # 保存报告
    report_path = reporter.save_report(scan_result, adapt_result)
    print(f"   报告已保存: {report_path}")
    print()
    
    # 4. 输出报告
    print(report_text)
    
    # 5. 快速状态
    print()
    print(reporter.generate_quick_status())
    
    return scan_result, adapt_result


if __name__ == "__main__":
    main()
