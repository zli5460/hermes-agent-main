#!/usr/bin/env bash
# Phoenix — 一键安装脚本（macOS / Linux）
# 用法：解压发布包后执行 bash install.sh
# 原则：自动化能自动化的一切；API Key只由用户现场输入，不内置、不回显、不写入日志。

set -euo pipefail
shopt -s extglob

OS="$(uname -s)"
case "$OS" in
  Darwin) PLATFORM="macOS" ;;
  Linux) PLATFORM="Linux" ;;
  *) echo "❌ 不支持的平台: $OS。Windows 请用 PowerShell 执行 install.ps1"; exit 1 ;;
esac

PKG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
PHOENIX_HOME="$HERMES_HOME/phoenix"
HERMES_AGENT_DIR="${HERMES_AGENT_DIR:-$HERMES_HOME/hermes-agent}"
BUNDLED_PLUGIN_DIR=""
USER_PLUGIN_DIR="$HERMES_HOME/plugins/phoenix_full"
SKINS_DIR="$HERMES_HOME/skins"
ENV_FILE="$HERMES_HOME/.env"
CONFIG_FILE="$HERMES_HOME/config.yaml"
BACKUP_DIR="$HERMES_HOME/backups/phoenix_preinstall_$(date +%Y%m%d_%H%M%S)"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "❌ 缺少命令: $1"; exit 1; }
}

mask_key() {
  local k="${1:-}"
  if [ ${#k} -le 8 ]; then echo "********"; else echo "${k:0:4}****${k: -4}"; fi
}

validate_model_name() {
  local name="$1"
  [[ "$name" =~ ^[a-zA-Z0-9/_.:+-]+$ ]]
}

validate_url() {
  local url="$1"
  case "$url" in
    http://*|https://*) return 0 ;;
    *) return 1 ;;
  esac
}


detect_hermes_agent_dir() {
  local candidates=(
    "${HERMES_AGENT_DIR:-}"
    "$HERMES_HOME/hermes-agent"
    "$HOME/.hermes/hermes-agent"
    "/mnt/projects/hermes-agent"
    "$HOME/projects/hermes-agent"
    "$HOME/Desktop/hermes-agent"
  )
  local candidate
  for candidate in "${candidates[@]}"; do
    if [ -n "${candidate:-}" ] && [ -d "$candidate" ]; then
      printf '%s' "$candidate"
      return 0
    fi
  done
  printf '%s' "$HERMES_HOME/hermes-agent"
  return 0
}

upsert_env() {
  local key="$1"
  local value="$2"
  mkdir -p "$HERMES_HOME"
  touch "$ENV_FILE"
  chmod 600 "$ENV_FILE" 2>/dev/null || true
  if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
    python3 - "$ENV_FILE" "$key" "$value" <<'PY'
from pathlib import Path
import sys
path, key, value = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
lines = path.read_text().splitlines() if path.exists() else []
out = []
for line in lines:
    if line.startswith(key + '='):
        out.append(f'{key}={value}')
    else:
        out.append(line)
path.write_text('\n'.join(out).rstrip() + '\n')
PY
  else
    printf "%s=%s\n" "$key" "$value" >> "$ENV_FILE"
  fi
}

set_config_yaml() {
  local dotted_key="$1"
  local value="$2"
  python3 - "$CONFIG_FILE" "$dotted_key" "$value" <<'PY'
from pathlib import Path
import sys
try:
    import yaml
except Exception:
    yaml = None
path = Path(sys.argv[1]); dotted = sys.argv[2]; raw = sys.argv[3]
if yaml is None:
    raise SystemExit(0)
path.parent.mkdir(parents=True, exist_ok=True)
data = yaml.safe_load(path.read_text()) if path.exists() and path.read_text().strip() else {}
if not isinstance(data, dict): data = {}
cur = data
parts = dotted.split('.')
for p in parts[:-1]:
    if not isinstance(cur.get(p), dict): cur[p] = {}
    cur = cur[p]
if raw.lower() == 'true': val = True
elif raw.lower() == 'false': val = False
elif raw.startswith('[') and raw.endswith(']'):
    val = [x.strip().strip('"\'') for x in raw[1:-1].split(',') if x.strip()]
else:
    try:
        val = int(raw)
    except Exception:
        try: val = float(raw)
        except Exception: val = raw
cur[parts[-1]] = val
path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
PY
}

restart_gateway() {
  echo ""
  echo "🔄 正在自动重启 Hermes Gateway..."
  if command -v hermes >/dev/null 2>&1; then
    hermes gateway restart >/dev/null 2>&1 || hermes gateway start >/dev/null 2>&1 || true
    echo "  ✅ 已发送 Gateway 重启/启动命令"
  else
    echo "  ⚠️ 未检测到 hermes 命令，请安装 Hermes 后执行: hermes gateway restart"
  fi
}

check_hermes_entrypoint() {
  local phase="${1:-检查}"
  python3 - "$phase" "$PHOENIX_HOME" <<'PY'
import shutil, subprocess, sys
from pathlib import Path
phase, phoenix_home = sys.argv[1], Path(sys.argv[2]).expanduser().resolve()
markers = ["不死鸟 Phoenix", "python -m phoenix.cli", "Phoenix V8", "CLI入口"]
cmd = shutil.which("hermes")
if not cmd:
    print(f"  ❌ {phase}: 未检测到 hermes 命令。Phoenix 是插件，不是 Hermes 本体；请先安装 Hermes Agent，再运行本安装器。")
    raise SystemExit(43)
path = Path(cmd)
try:
    resolved = path.resolve()
except Exception:
    resolved = path
try:
    if phoenix_home in resolved.parents or resolved == phoenix_home:
        print(f"  ❌ {phase}: hermes 命令指向 Phoenix 目录: {resolved}")
        print("     正确边界：hermes 必须是 Hermes Agent 原生命令；Phoenix 只能作为插件加载。")
        raise SystemExit(42)
except SystemExit:
    raise
except Exception:
    pass
blob = ""
try:
    if path.is_file():
        blob += path.read_text(encoding="utf-8", errors="ignore")[:12000]
except Exception:
    pass
try:
    proc = subprocess.run([cmd, "--help"], capture_output=True, text=True, timeout=8)
    blob += "\n" + (proc.stdout or "")[:12000] + "\n" + (proc.stderr or "")[:4000]
except Exception as exc:
    blob += f"\nHERME_HELP_ERROR={exc}"
if any(m in blob for m in markers):
    print(f"  ❌ {phase}: hermes 命令已被 Phoenix CLI 覆盖/劫持。")
    print(f"     当前 hermes: {cmd}")
    print("     现象：输入 hermes 出现 '不死鸟 Phoenix V8 — CLI入口'，学员会进不了 Hermes。")
    print("     修复：删除错误 alias/function/shim，恢复 Hermes Agent 原生 hermes；不要把 Phoenix cli.py 链接成 hermes。")
    raise SystemExit(42)
print(f"  ✅ {phase}: hermes 入口正常，Phoenix 未接管 hermes 命令 ({cmd})")
PY
}


patch_hermes_cli_verbose_compat() {
  local main_py="$HERMES_AGENT_DIR/hermes_cli/main.py"
  if [ ! -f "$main_py" ]; then
    echo "  ⚠️ 未找到 Hermes CLI main.py，跳过 WSL verbose 兼容补丁"
    return 0
  fi
  python3 - "$main_py" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
text = path.read_text(encoding='utf-8')
if 'inspect.signature(cli_main)' in text and 'Phoenix V8 compatibility' in text:
    print('  ✅ WSL verbose 兼容补丁已存在')
    raise SystemExit(0)
old = """    # Filter out None values
    kwargs = {k: v for k, v in kwargs.items() if v is not None}

    try:
        cli_main(**kwargs)"""
new = """    # Filter out None values
    kwargs = {k: v for k, v in kwargs.items() if v is not None}

    # Phoenix V8 compatibility: some WSL/student Hermes installs carry an
    # older cli.main() signature. Filter kwargs by the live callable signature
    # before dispatching instead of crashing with unexpected keyword arguments
    # such as 'verbose'.
    try:
        import inspect
        sig = inspect.signature(cli_main)
        if not any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
            kwargs = {k: v for k, v in kwargs.items() if k in sig.parameters}
    except Exception:
        pass

    try:
        cli_main(**kwargs)"""
if old not in text:
    print('  ⚠️ Hermes CLI 结构不同，未应用 WSL verbose 兼容补丁')
    raise SystemExit(0)
path.write_text(text.replace(old, new, 1), encoding='utf-8')
print('  ✅ 已应用 WSL verbose 兼容补丁')
PY
}

need_cmd python3

HERMES_AGENT_DIR="$(detect_hermes_agent_dir)"
BUNDLED_PLUGIN_DIR="$HERMES_AGENT_DIR/plugins/phoenix_full"

echo ""
echo "========================================"
echo "  Phoenix 一键安装程序"
echo "  平台: $PLATFORM"
echo "========================================"
echo ""
echo "📘 如果你不知道现在该干什么："
echo "  - 先看: START_HERE.md"
echo "  - 交付总说明: DELIVERY_GUIDE.md"
echo "  - 安装细节: INSTALL_GUIDE.md"
echo "  - 使用说明: USER_GUIDE.md"
echo ""
echo "⚠️ 这个脚本不会自动弹网页。它会在终端里一步步引导你输入配置。"
echo ""
echo "本安装器将自动完成："
echo "  ✅ 安装/更新 Phoenix 到 $PHOENIX_HOME"
echo "  ✅ 同步 phoenix_full 插件到 Hermes bundled + 用户插件双路径"
echo "  ✅ 安装 Phoenix 皮肤（不写死版本号）"
echo "  ✅ 开启记忆、压缩、检查点、自动恢复"
echo "  ✅ 引导填写用户自己的默认模型、兜底模型、Key 和 Base URL"
echo "  ✅ 配置五档模型映射"
echo "  ✅ 自动重启 Gateway 让配置生效"
echo "  ❌ 不内置、不输出、不上传任何我们的 API Key"
echo "  ❌ 不覆盖用户现有记忆/会话数据"
echo ""
read -r -p "确认开始安装？(y/N): " CONFIRM
case "$CONFIRM" in [Yy]*) ;; *) echo "已取消"; exit 0 ;; esac

check_hermes_entrypoint "安装前入口检查"

echo ""
echo "📦 [1/7] 备份现有配置..."
mkdir -p "$BACKUP_DIR"
[ -f "$CONFIG_FILE" ] && cp "$CONFIG_FILE" "$BACKUP_DIR/config.yaml" || true
[ -f "$ENV_FILE" ] && cp "$ENV_FILE" "$BACKUP_DIR/.env" || true
[ -d "$PHOENIX_HOME" ] && cp -R "$PHOENIX_HOME" "$BACKUP_DIR/phoenix" || true
echo "  ✅ 备份目录: $BACKUP_DIR"

echo ""
echo "📁 [2/7] 安装 Phoenix 文件..."
mkdir -p "$PHOENIX_HOME"
for item in core router executor memory self_heal integration security adapt sandbox workflow github desktop plugins config skills tests; do
  [ -e "$PKG_DIR/$item" ] && rsync -a --delete --exclude='__pycache__' "$PKG_DIR/$item/" "$PHOENIX_HOME/$item/"
done
for f in phoenix.py __init__.py cli.py doctor.py config.json auto_save.py auto_fusion.py post_upgrade_hook.sh install.sh install.ps1 sim_verify_v8.py VERSION.md CHANGELOG.md CLAUDE.md README.md START_HERE.md DELIVERY_GUIDE.md INSTALL_GUIDE.md USER_GUIDE.md ARCHITECTURE.md phoenix.yaml; do
  [ -f "$PKG_DIR/$f" ] && cp -f "$PKG_DIR/$f" "$PHOENIX_HOME/$f"
done
for f in \
  "不死鸟_Phoenix_V8_使用说明书.md" \
  "不死鸟_Phoenix_V8_技术细则与路径原理.md" \
  INSTALL_安装说明_完整版.md \
  INSTALL_平台选择_macOS_Windows_WSL_Linux.md \
  INSTALL_CUSTOMER_一页纸.md \
  INSTALL_装前装后对比_Hermes与不死鸟.md \
  RELEASE_交付流程与验收.md \
  HERMES_融合与随版本升级.md \
  HERMES_TUI_与不死鸟斜杠指令.md \
  PHOENIX_V8_CORE_DELIVERY.md \
  Phoenix_V8_初心回归_架构蓝图.md; do
  [ -f "$PKG_DIR/$f" ] && cp -f "$PKG_DIR/$f" "$PHOENIX_HOME/$f"
done
if [ -f "$PKG_DIR/feature_registry.json" ]; then
  cp -f "$PKG_DIR/feature_registry.json" "$PHOENIX_HOME/feature_registry.json"
fi
chmod +x "$PHOENIX_HOME/install.sh" "$PHOENIX_HOME/post_upgrade_hook.sh" 2>/dev/null || true
echo "  ✅ Phoenix 文件安装完成"

echo ""
echo "🔌 [3/7] 同步 Hermes 插件（双路径强制覆盖）..."
SRC_PLUGIN_DIR="$PHOENIX_HOME/plugins/phoenix_full"
if [ ! -d "$SRC_PLUGIN_DIR" ]; then
  echo "  ❌ Phoenix 插件源目录不存在: $SRC_PLUGIN_DIR"
  exit 1
fi

sync_plugin_dir() {
  local dst="$1"
  local label="$2"
  rm -rf "$dst"
  mkdir -p "$dst"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete --exclude='__pycache__' "$SRC_PLUGIN_DIR/" "$dst/"
  else
    cp -R "$SRC_PLUGIN_DIR/." "$dst/"
  fi
  find "$dst" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
  find "$dst" -name '*.pyc' -delete 2>/dev/null || true
  echo "  ✅ 插件已同步($label): $dst"
}

if [ -d "$HERMES_AGENT_DIR" ]; then
  sync_plugin_dir "$BUNDLED_PLUGIN_DIR" "bundled"
else
  echo "  ⚠️ 未找到 Hermes 源码目录: $HERMES_AGENT_DIR，跳过 bundled 同步"
fi
sync_plugin_dir "$USER_PLUGIN_DIR" "user"
patch_hermes_cli_verbose_compat

echo ""
echo "🎨 [4/7] 安装 Phoenix 皮肤..."
mkdir -p "$SKINS_DIR"
if [ -f "$PKG_DIR/_package_skins/phoenix.yaml" ]; then
  cp -f "$PKG_DIR/_package_skins/phoenix.yaml" "$SKINS_DIR/phoenix.yaml"
elif [ -f "$PKG_DIR/phoenix.yaml" ]; then
  cp -f "$PKG_DIR/phoenix.yaml" "$SKINS_DIR/phoenix.yaml"
else
  cat > "$SKINS_DIR/phoenix.yaml" <<'YAML'
name: phoenix
description: "不死鸟 Phoenix — 浴火不灭，迭代永生"
branding:
  agent_name: "Hermes × Phoenix"
  welcome: "🔥 Hermes × Phoenix — 浴火不灭，迭代永生"
  goodbye: "🔥 不死鸟浴火，下次重生再见！"
  response_label: " 🔥 Phoenix "
YAML
fi
echo "  ✅ 皮肤已安装: $SKINS_DIR/phoenix.yaml"

echo ""
echo "⚙️ [5/7] 写入 Hermes 基础配置..."
set_config_yaml display.skin phoenix
set_config_yaml display.resume_display full
set_config_yaml display.tui_auto_resume_recent true
set_config_yaml display.streaming true
set_config_yaml compression.enabled true
set_config_yaml compression.threshold 0.5
set_config_yaml compression.target_ratio 0.2
set_config_yaml checkpoints.enabled true
set_config_yaml checkpoints.max_snapshots 50
set_config_yaml memory.memory_enabled true
set_config_yaml memory.user_profile_enabled true
set_config_yaml privacy.redact_pii true
set_config_yaml plugins.enabled '[phoenix-full,disk-cleanup]'
echo "  ✅ 基础配置完成"

echo ""
echo "🤖 [6/7] 引导配置模型与 Key"
echo "说明：这里填的是用户自己的 Key。安装包没有内置任何开发者 Key。"
echo ""

echo "模型链路说明：primary 是默认入口；fallback 是欠费/超时/失败时的救场模型。"
echo "本地模型也可以做 fallback，例如 Ollama/LM Studio/vLLM 的 OpenAI 兼容地址。"
echo ""

read -r -p "日常默认模型 primary [xiaomi/mimo-v2.5]: " DAILY_MODEL
DAILY_MODEL=${DAILY_MODEL:-xiaomi/mimo-v2.5}
validate_model_name "$DAILY_MODEL" || { echo "❌ 模型名格式不合法: $DAILY_MODEL"; exit 1; }

read -r -p "日常兜底模型 fallback [xiaomi/mimo-v2-flash]: " DAILY_FALLBACK_MODEL
DAILY_FALLBACK_MODEL=${DAILY_FALLBACK_MODEL:-xiaomi/mimo-v2-flash}
validate_model_name "$DAILY_FALLBACK_MODEL" || { echo "❌ 兜底模型名格式不合法: $DAILY_FALLBACK_MODEL"; exit 1; }

read -r -p "日常默认模型 Base URL [https://inference-api.nousresearch.com/v1]: " DAILY_URL
DAILY_URL=${DAILY_URL:-https://inference-api.nousresearch.com/v1}
validate_url "$DAILY_URL" || { echo "❌ Base URL 格式不合法: $DAILY_URL"; exit 1; }

read -r -p "日常默认模型 Provider 名称 [nous-api]: " DAILY_PROVIDER
DAILY_PROVIDER=${DAILY_PROVIDER:-nous-api}

read -r -s -p "请输入日常默认模型 API Key（不回显，可回车跳过）: " DAILY_KEY
echo ""
if [ -n "$DAILY_KEY" ]; then
  upsert_env "PHOENIX_DAILY_API_KEY" "$DAILY_KEY"
  echo "  ✅ 日常默认模型 Key 已写入本机 .env: $(mask_key "$DAILY_KEY")"
else
  echo "  ⚠️ 未填写日常默认模型 Key，后续需手动配置"
fi

read -r -p "兜底模型 Base URL（回车复用日常；本地可填 http://localhost:11434/v1）[$DAILY_URL]: " FALLBACK_URL
FALLBACK_URL=${FALLBACK_URL:-$DAILY_URL}
validate_url "$FALLBACK_URL" || { echo "❌ 兜底 Base URL 格式不合法: $FALLBACK_URL"; exit 1; }

read -r -p "兜底模型 Provider 名称 [$DAILY_PROVIDER]: " FALLBACK_PROVIDER
FALLBACK_PROVIDER=${FALLBACK_PROVIDER:-$DAILY_PROVIDER}

read -r -s -p "请输入兜底模型 API Key（不回显，可回车复用日常Key/本地模型可跳过）: " FALLBACK_KEY
echo ""
if [ -n "$FALLBACK_KEY" ]; then
  upsert_env "PHOENIX_FALLBACK_API_KEY" "$FALLBACK_KEY"
  FALLBACK_KEY_ENV="PHOENIX_FALLBACK_API_KEY"
  echo "  ✅ 兜底模型 Key 已写入本机 .env: $(mask_key "$FALLBACK_KEY")"
else
  FALLBACK_KEY_ENV="PHOENIX_DAILY_API_KEY"
  echo "  ℹ️ 兜底模型默认复用日常 Key；本地模型无 Key 也可后续手动调整"
fi

read -r -p "深度模型名 [/深度，默认 anthropic/claude-sonnet-4.6]: " DEEP_MODEL
DEEP_MODEL=${DEEP_MODEL:-anthropic/claude-sonnet-4.6}
validate_model_name "$DEEP_MODEL" || { echo "❌ 模型名格式不合法: $DEEP_MODEL"; exit 1; }

read -r -p "大神模型名 [/大神，默认 anthropic/claude-opus-4.7]: " GOD_MODEL
GOD_MODEL=${GOD_MODEL:-anthropic/claude-opus-4.7}
validate_model_name "$GOD_MODEL" || { echo "❌ 模型名格式不合法: $GOD_MODEL"; exit 1; }

read -r -p "真神第二模型名 [/真神，默认 openai/gpt-5.5]: " SUPER_SECONDARY_MODEL
SUPER_SECONDARY_MODEL=${SUPER_SECONDARY_MODEL:-openai/gpt-5.5}
validate_model_name "$SUPER_SECONDARY_MODEL" || { echo "❌ 模型名格式不合法: $SUPER_SECONDARY_MODEL"; exit 1; }

read -r -p "高档模型 Base URL（Claude/OpenAI聚合端点）[$DAILY_URL]: " PREMIUM_URL
PREMIUM_URL=${PREMIUM_URL:-$DAILY_URL}
validate_url "$PREMIUM_URL" || { echo "❌ 高档 Base URL 格式不合法: $PREMIUM_URL"; exit 1; }

read -r -s -p "请输入高档模型 API Key（不回显，可回车复用日常Key/后续手动配）: " PREMIUM_KEY
echo ""
if [ -n "$PREMIUM_KEY" ]; then
  upsert_env "PHOENIX_PREMIUM_API_KEY" "$PREMIUM_KEY"
  echo "  ✅ 高档模型 Key 已写入本机 .env: $(mask_key "$PREMIUM_KEY")"
fi

set_config_yaml phoenix.router.daily_model "$DAILY_MODEL"
set_config_yaml phoenix.router.daily_provider "$DAILY_PROVIDER"
set_config_yaml phoenix.router.daily_base_url "$DAILY_URL"
set_config_yaml phoenix.router.daily_key_env PHOENIX_DAILY_API_KEY
set_config_yaml phoenix.router.daily_fallback_model "$DAILY_FALLBACK_MODEL"
set_config_yaml phoenix.router.daily_fallback_provider "$FALLBACK_PROVIDER"
set_config_yaml phoenix.router.daily_fallback_base_url "$FALLBACK_URL"
set_config_yaml phoenix.router.daily_fallback_key_env "$FALLBACK_KEY_ENV"
set_config_yaml phoenix.router.deep_model "$DEEP_MODEL"
set_config_yaml phoenix.router.deep_fallback_model "$DAILY_FALLBACK_MODEL"
set_config_yaml phoenix.router.god_model "$GOD_MODEL"
set_config_yaml phoenix.router.god_fallback_model "$DEEP_MODEL"
set_config_yaml phoenix.router.super_god_primary "$GOD_MODEL"
set_config_yaml phoenix.router.super_god_secondary "$SUPER_SECONDARY_MODEL"
set_config_yaml phoenix.router.super_god_fallback_model "$DEEP_MODEL"
set_config_yaml phoenix.router.premium_base_url "$PREMIUM_URL"
set_config_yaml phoenix.routing.high_tier_trigger manual_only
set_config_yaml phoenix.fallback.enabled true
set_config_yaml phoenix.fallback.on_status_codes '[401,402,403,429,500,502,503,504]'
set_config_yaml phoenix.fallback.on_errors '[timeout,connection_error,rate_limit,insufficient_quota]'
set_config_yaml phoenix.providers.daily.model "$DAILY_MODEL"
set_config_yaml phoenix.providers.daily.provider "$DAILY_PROVIDER"
set_config_yaml phoenix.providers.daily.base_url "$DAILY_URL"
set_config_yaml phoenix.providers.daily.key_env PHOENIX_DAILY_API_KEY
set_config_yaml phoenix.providers.daily_fallback.model "$DAILY_FALLBACK_MODEL"
set_config_yaml phoenix.providers.daily_fallback.provider "$FALLBACK_PROVIDER"
set_config_yaml phoenix.providers.daily_fallback.base_url "$FALLBACK_URL"
set_config_yaml phoenix.providers.daily_fallback.key_env "$FALLBACK_KEY_ENV"

echo "  🧭 写入 Phoenix V8 初心回归版手动路由配置..."
python3 - "$PHOENIX_HOME/config.json" "$DAILY_MODEL" "$DAILY_PROVIDER" "$DAILY_URL" "$DAILY_FALLBACK_MODEL" "$FALLBACK_PROVIDER" "$FALLBACK_URL" "$FALLBACK_KEY_ENV" "$DEEP_MODEL" "$GOD_MODEL" "$SUPER_SECONDARY_MODEL" "$PREMIUM_URL" <<'PY'
from pathlib import Path
import json, sys
cfg_path = Path(sys.argv[1])
(daily_model, daily_provider, daily_url, fallback_model, fallback_provider, fallback_url, fallback_key_env, deep_model, god_model, super_secondary_model, premium_url) = sys.argv[2:13]
data = json.loads(cfg_path.read_text(encoding='utf-8')) if cfg_path.exists() and cfg_path.read_text(encoding='utf-8').strip() else {}
open_cfg = data.setdefault('phoenix_open', {})
providers = open_cfg.setdefault('providers', {})
providers[daily_provider] = {'base_url': daily_url, 'api_key_env': 'PHOENIX_DAILY_API_KEY', 'models': [daily_model], 'is_local': daily_url.startswith('http://localhost') or daily_url.startswith('http://127.0.0.1')}
providers[fallback_provider] = {'base_url': fallback_url, 'api_key_env': fallback_key_env, 'models': [fallback_model], 'is_local': fallback_url.startswith('http://localhost') or fallback_url.startswith('http://127.0.0.1')}
providers['premium'] = {'base_url': premium_url, 'api_key_env': 'PHOENIX_PREMIUM_API_KEY', 'models': [deep_model, god_model, super_secondary_model], 'is_local': False}
open_cfg['model_tiers'] = {
  'daily': {'model': daily_model, 'provider': daily_provider, 'base_url': daily_url, 'api_key_env': 'PHOENIX_DAILY_API_KEY', 'requires_approval': False, 'auto_execute': False, 'manual_only': True, 'fallback': {'model': fallback_model, 'provider': fallback_provider, 'base_url': fallback_url, 'api_key_env': fallback_key_env}, 'emergency': {'model': fallback_model, 'provider': fallback_provider, 'base_url': fallback_url, 'api_key_env': fallback_key_env}},
  'medium': {'model': fallback_model, 'provider': fallback_provider, 'base_url': fallback_url, 'api_key_env': fallback_key_env, 'enabled': False, 'requires_approval': True, 'auto_execute': False, 'manual_only': True, 'fallback': {'model': daily_model, 'provider': daily_provider, 'base_url': daily_url, 'api_key_env': 'PHOENIX_DAILY_API_KEY'}, 'emergency': {'model': fallback_model, 'provider': fallback_provider, 'base_url': fallback_url, 'api_key_env': fallback_key_env}},
  'deep': {'model': deep_model, 'provider': 'premium', 'base_url': premium_url, 'api_key_env': 'PHOENIX_PREMIUM_API_KEY', 'requires_approval': True, 'auto_execute': False, 'manual_only': True, 'trigger': '/深度', 'fallback': {'model': fallback_model, 'provider': fallback_provider, 'base_url': fallback_url, 'api_key_env': fallback_key_env}, 'emergency': {'model': fallback_model, 'provider': fallback_provider, 'base_url': fallback_url, 'api_key_env': fallback_key_env}},
  'god': {'model': god_model, 'provider': 'premium', 'base_url': premium_url, 'api_key_env': 'PHOENIX_PREMIUM_API_KEY', 'requires_approval': True, 'auto_execute': False, 'manual_only': True, 'trigger': '/大神', 'fallback': {'model': deep_model, 'provider': 'premium', 'base_url': premium_url, 'api_key_env': 'PHOENIX_PREMIUM_API_KEY'}, 'emergency': {'model': fallback_model, 'provider': fallback_provider, 'base_url': fallback_url, 'api_key_env': fallback_key_env}},
  'super_god': {'model': god_model, 'provider': 'premium', 'base_url': premium_url, 'api_key_env': 'PHOENIX_PREMIUM_API_KEY', 'model_a': god_model, 'provider_a': 'premium', 'base_url_a': premium_url, 'api_key_env_a': 'PHOENIX_PREMIUM_API_KEY', 'model_b': super_secondary_model, 'provider_b': 'premium', 'base_url_b': premium_url, 'api_key_env_b': 'PHOENIX_PREMIUM_API_KEY', 'requires_approval': True, 'auto_execute': False, 'manual_only': True, 'trigger': '/真神', 'secondary_reserved': {'model': super_secondary_model, 'provider': 'premium'}, 'fallback': {'model': deep_model, 'provider': 'premium', 'base_url': premium_url, 'api_key_env': 'PHOENIX_PREMIUM_API_KEY'}, 'emergency': {'model': fallback_model, 'provider': fallback_provider, 'base_url': fallback_url, 'api_key_env': fallback_key_env}},
}
open_cfg['fallback'] = {'model': fallback_model, 'provider': fallback_provider, 'base_url': fallback_url, 'api_key_env': fallback_key_env}
cfg_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
PY
echo "  ✅ 模型映射已写入 config.yaml + config.json：daily不切 / medium不自动切 / 高档手动确认"

echo ""
echo "🧪 [7/7] 本地自检 + doctor 闭环..."
python3 - <<PY
from pathlib import Path
import py_compile
root = Path('$PHOENIX_HOME')
for rel in ['phoenix.py', 'doctor.py', 'router/engine.py', 'plugins/phoenix_full/__init__.py', 'memory/memory_system.py', 'self_heal/antibody.py']:
    py_compile.compile(str(root / rel), doraise=True)
print('  ✅ Python核心文件语法正常')
PY

echo ""
echo "🩺 [7.1/7] 运行 Phoenix Doctor 自动验收..."
python3 "$PHOENIX_HOME/doctor.py" --fix --home "$HERMES_HOME" --phoenix-home "$PHOENIX_HOME" --hermes-agent-dir "$HERMES_AGENT_DIR"

restart_gateway

echo ""
echo "🔁 [7.2/7] 复测 Phoenix Doctor..."
python3 "$PHOENIX_HOME/doctor.py" --verify --home "$HERMES_HOME" --phoenix-home "$PHOENIX_HOME" --hermes-agent-dir "$HERMES_AGENT_DIR"

check_hermes_entrypoint "安装后入口复检"

echo ""
echo "========================================"
echo "  ✅ Phoenix 安装完成"
echo "========================================"
echo "📘 文档已安装到: $PHOENIX_HOME"
echo "  - 先看: $PHOENIX_HOME/START_HERE.md"
echo "  - 交付总说明: $PHOENIX_HOME/DELIVERY_GUIDE.md"
echo "  - 安装说明: $PHOENIX_HOME/INSTALL_GUIDE.md"
echo "  - 使用说明: $PHOENIX_HOME/USER_GUIDE.md"
echo ""
echo "下一步建议："
echo "  1. 打开 Hermes/TUI 或 Telegram 发：你好"
echo "  2. 测试普通模式：深度学习是什么？（不应弹高成本确认）"
echo "  3. 测试高档模式：/深度 帮我分析这个项目（应弹确认）"
echo "  4. 查看 Gateway 状态：hermes gateway status"
echo ""


echo ""
echo "🔥 Phoenix V8 路由启动方式："
echo "  普通聊天：直接发，不会自动切高档"
echo "  深度任务：/深度 你的任务"
echo "  大神任务：/大神 你的任务"
echo "  真神任务：/真神 你的任务"
echo "  回复：确认 / 降级 / 取消"
echo "  主模型失败：自动走 fallback / emergency；执行完回默认"
echo ""
