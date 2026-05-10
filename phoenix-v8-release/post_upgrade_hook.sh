#!/bin/bash
# Phoenix V8 Post-Upgrade Fusion Hook
# ======================================
# Hermes升级后自动执行，扫描并融合新功能
#
# 安装方式：加入Hermes hooks系统
# hermes hooks add post_upgrade ~/.hermes/phoenix/post_upgrade_hook.sh

set -euo pipefail

PHOENIX_DIR="$HOME/.hermes/phoenix"
LOG_FILE="$PHOENIX_DIR/fusion.log"
AUTO_FUSION="$PHOENIX_DIR/auto_fusion.py"

echo "" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"
echo "🔥 Phoenix Auto-Fusion triggered at $(date)" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

# 运行自动融合脚本（--apply模式）
if [ -f "$AUTO_FUSION" ]; then
    python3 "$AUTO_FUSION" --apply >> "$LOG_FILE" 2>&1
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 0 ]; then
        echo "✅ Fusion completed successfully" >> "$LOG_FILE"
    else
        echo "❌ Fusion failed with exit code $EXIT_CODE" >> "$LOG_FILE"
    fi
else
    echo "❌ Auto-fusion script not found: $AUTO_FUSION" >> "$LOG_FILE"
fi

echo "========================================" >> "$LOG_FILE"
