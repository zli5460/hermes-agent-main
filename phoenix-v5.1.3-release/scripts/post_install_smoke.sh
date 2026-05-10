#!/usr/bin/env bash
# Phoenix V5.1.3 — 安装完成后快速自检（不替代 sim_verify / 真机全链路）
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
PHOENIX_HOME="${PHOENIX_HOME:-$HERMES_HOME/phoenix}"
HERMES_AGENT_DIR="${HERMES_AGENT_DIR:-$HERMES_HOME/hermes-agent}"

if [[ ! -d "$PHOENIX_HOME" ]]; then
  echo "❌ 未找到 Phoenix 目录: $PHOENIX_HOME（请先运行 install.sh）"
  exit 1
fi

echo "== 1/4 Hermes 命令 =="
if ! command -v hermes >/dev/null 2>&1; then
  echo "❌ 未找到 hermes，请先安装 Hermes Agent 并确保 PATH 包含 pipx/bin"
  exit 1
fi
echo "   $(command -v hermes)"

echo "== 2/4 hermes --help（前 5 行）==="
hermes --help 2>&1 | head -n 5

echo "== 3/4 Gateway 状态（失败仅警告）==="
hermes gateway status 2>&1 || echo "   ⚠️ gateway status 非零，可稍后手动: hermes gateway restart"

echo "== 4/4 Phoenix doctor --verify =="
if [[ ! -f "$PHOENIX_HOME/doctor.py" ]]; then
  echo "❌ 缺少 $PHOENIX_HOME/doctor.py"
  exit 1
fi
python3 "$PHOENIX_HOME/doctor.py" --verify \
  --home "$HERMES_HOME" \
  --phoenix-home "$PHOENIX_HOME" \
  --hermes-agent-dir "$HERMES_AGENT_DIR"

echo ""
echo "✅ post_install_smoke 通过。下一步：对话里测「你好 / 深度学习是什么？/ /深度 …」"
