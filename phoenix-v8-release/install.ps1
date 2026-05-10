# Phoenix — Windows 一键安装脚本
# 用法：解压发布包后，在 PowerShell 中执行：powershell -ExecutionPolicy Bypass -File .\install.ps1
# 原则：自动化能自动化的一切；API Key只由用户现场输入，不内置、不回显、不写入日志。
#
# 画像 local-deepseek（Ollama + DeepSeek）：请在 WSL 或 Git Bash 中执行
#   bash install.sh --profile=local-deepseek -y

param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$PkgDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$HermesHome = if ($env:HERMES_HOME) { $env:HERMES_HOME } else { Join-Path $env:USERPROFILE ".hermes" }
$PhoenixHome = Join-Path $HermesHome "phoenix"
$HermesAgentDir = Join-Path $HermesHome "hermes-agent"
$BundledPluginDir = Join-Path $HermesAgentDir "plugins\phoenix_full"
$UserPluginDir = Join-Path $HermesHome "plugins\phoenix_full"
$SkinsDir = Join-Path $HermesHome "skins"
$EnvFile = Join-Path $HermesHome ".env"
$ConfigFile = Join-Path $HermesHome "config.yaml"
$BackupDir = Join-Path $HermesHome ("backups\phoenix_preinstall_" + (Get-Date -Format "yyyyMMdd_HHmmss"))

function Validate-ModelName([string]$name) {
    return ($name -match '^[a-zA-Z0-9/_.:+-]+$')
}

function Validate-Url([string]$url) {
    return ($url -match '^https?://')
}

function Write-ModelModeConfig([string]$path, [string]$jsonText) {
    Set-Content -Path $path -Value $jsonText -Encoding UTF8
}

function Read-JsonFile([string]$path) {
    if (!(Test-Path $path)) { return $null }
    try { return (Get-Content -Raw $path | ConvertFrom-Json) } catch { return $null }
}

function Update-ModelModeConfig([string]$path) {
    $cfg = Read-JsonFile $path
    if (!$cfg) { return }
    if ($cfg.phoenix_open -and $cfg.phoenix_open.model_tiers) {
        $tiers = $cfg.phoenix_open.model_tiers
        foreach ($tierName in @('daily','medium','deep','god','super_god')) {
            if (!$tiers.$tierName) { continue }
            $tier = $tiers.$tierName
            if ($tier.api_mode -and $tier.api_mode -ne 'chat_completions') {
                $tier.api_mode = 'chat_completions'
            }
            if ($tier.models -and $tier.models.primary -and ($tier.models.primary.api_mode -ne $null)) {
                $tier.models.primary.api_mode = 'chat_completions'
            }
        }
        $json = $cfg | ConvertTo-Json -Depth 40
        Set-Content -Path $path -Value $json -Encoding UTF8
    }
}

function Mask-Key([string]$k) {
    if ([string]::IsNullOrEmpty($k)) { return "********" }
    if ($k.Length -le 8) { return "********" }
    return $k.Substring(0,4) + "****" + $k.Substring($k.Length-4)
}

function Ensure-Dir([string]$p) {
    if (!(Test-Path $p)) { New-Item -ItemType Directory -Path $p -Force | Out-Null }
}

function Upsert-Env([string]$key, [string]$value) {
    Ensure-Dir $HermesHome
    if (!(Test-Path $EnvFile)) { New-Item -ItemType File -Path $EnvFile -Force | Out-Null }
    $lines = Get-Content $EnvFile -ErrorAction SilentlyContinue
    $found = $false
    $out = @()
    foreach ($line in $lines) {
        if ($line.StartsWith($key + "=")) {
            $out += "$key=$value"
            $found = $true
        } else {
            $out += $line
        }
    }
    if (!$found) { $out += "$key=$value" }
    Set-Content -Path $EnvFile -Value $out -Encoding UTF8
    try {
        $acl = Get-Acl $EnvFile
        $acl.SetAccessRuleProtection($true, $false)
        $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($env:USERNAME, "FullControl", "Allow")
        $acl.SetAccessRule($rule)
        Set-Acl -Path $EnvFile -AclObject $acl
    } catch {}
}

function Set-ConfigYaml([string]$dottedKey, [string]$value) {
    $py = @'
from pathlib import Path
import sys
try:
    import yaml
except Exception:
    yaml = None
path = Path(sys.argv[1]); dotted = sys.argv[2]; raw = sys.argv[3]
path.parent.mkdir(parents=True, exist_ok=True)
if yaml is None:
    raise SystemExit(0)
data = yaml.safe_load(path.read_text(encoding='utf-8')) if path.exists() and path.read_text(encoding='utf-8').strip() else {}
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
    try: val = int(raw)
    except Exception:
        try: val = float(raw)
        except Exception: val = raw
cur[parts[-1]] = val
path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding='utf-8')
'@
    $tmp = Join-Path $env:TEMP "phoenix_set_config.py"
    Set-Content -Path $tmp -Value $py -Encoding UTF8
    python $tmp $ConfigFile $dottedKey $value
    Remove-Item $tmp -Force -ErrorAction SilentlyContinue
}

function Restart-Gateway() {
    Write-Host ""
    Write-Host "🔄 正在自动重启 Hermes Gateway..." -ForegroundColor Cyan
    $hermes = Get-Command hermes -ErrorAction SilentlyContinue
    if ($hermes) {
        try { hermes gateway restart | Out-Null }
        catch { try { hermes gateway start | Out-Null } catch {} }
        Write-Host "  ✅ 已发送 Gateway 重启/启动命令" -ForegroundColor Green
    } else {
        Write-Host "  ⚠️ 未检测到 hermes 命令，请安装 Hermes 后执行: hermes gateway restart" -ForegroundColor Yellow
    }
}

function Test-HermesEntrypoint([string]$Phase) {
    $hermes = Get-Command hermes -ErrorAction SilentlyContinue
    if (!$hermes) {
        Write-Host "  ❌ ${Phase}: 未检测到 hermes 命令。Phoenix 是插件，不是 Hermes 本体；请先安装 Hermes Agent。" -ForegroundColor Red
        exit 43
    }
    $cmdPath = $hermes.Source
    $markers = @("不死鸟 Phoenix", "python -m phoenix.cli", "Phoenix V8", "CLI入口")
    try {
        $resolved = [System.IO.Path]::GetFullPath($cmdPath)
        $phoenixResolved = [System.IO.Path]::GetFullPath($PhoenixHome)
        if ($resolved.StartsWith($phoenixResolved, [System.StringComparison]::OrdinalIgnoreCase)) {
            Write-Host "  ❌ ${Phase}: hermes 命令指向 Phoenix 目录: $resolved" -ForegroundColor Red
            Write-Host "     正确边界：hermes 必须是 Hermes Agent 原生命令；Phoenix 只能作为插件加载。" -ForegroundColor Yellow
            exit 42
        }
    } catch {}
    $blob = ""
    try {
        if (Test-Path $cmdPath) { $blob += (Get-Content -Raw $cmdPath -ErrorAction SilentlyContinue) }
    } catch {}
    try {
        $help = & $cmdPath --help 2>&1 | Out-String
        $blob += "`n" + $help
    } catch {}
    foreach ($m in $markers) {
        if ($blob.Contains($m)) {
            Write-Host "  ❌ ${Phase}: hermes 命令已被 Phoenix CLI 覆盖/劫持。" -ForegroundColor Red
            Write-Host "     当前 hermes: $cmdPath" -ForegroundColor Yellow
            Write-Host "     现象：输入 hermes 出现 '不死鸟 Phoenix V8 — CLI入口'，学员会进不了 Hermes。" -ForegroundColor Yellow
            Write-Host "     修复：删除错误 alias/function/shim，恢复 Hermes Agent 原生 hermes；不要把 Phoenix cli.py 链接成 hermes。" -ForegroundColor Yellow
            exit 42
        }
    }
    Write-Host "  ✅ ${Phase}: hermes 入口正常，Phoenix 未接管 hermes 命令 ($cmdPath)" -ForegroundColor Green
}


function Patch-HermesCliVerboseCompat() {
    $mainPy = Join-Path $HermesAgentDir "hermes_cli\main.py"
    if (!(Test-Path $mainPy)) {
        Write-Host "  ⚠️ 未找到 Hermes CLI main.py，跳过 WSL verbose 兼容补丁" -ForegroundColor Yellow
        return
    }
    $patchPy = @'
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
'@
    $tmpPatch = Join-Path $env:TEMP "phoenix_verbose_compat.py"
    Set-Content -Path $tmpPatch -Value $patchPy -Encoding UTF8
    python $tmpPatch $mainPy
    Remove-Item $tmpPatch -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Yellow
Write-Host "  Phoenix 一键安装程序" -ForegroundColor Yellow
Write-Host "  平台: Windows" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow
Write-Host ""
Write-Host "本安装器将自动完成："
Write-Host "  ✅ 安装/更新 Phoenix 到 $PhoenixHome"
Write-Host "  ✅ 同步 phoenix_full 插件到 Hermes bundled + 用户插件双路径"
Write-Host "  ✅ 安装 Phoenix 皮肤（不写死版本号）"
Write-Host "  ✅ 开启记忆、压缩、检查点、自动恢复"
Write-Host "  ✅ 引导填写用户自己的默认模型、兜底模型、Key 和 Base URL"
Write-Host "  ✅ 配置五档模型映射"
Write-Host "  ✅ 自动重启 Gateway 让配置生效"
Write-Host "  ❌ 不内置、不输出、不上传任何开发者 API Key"
Write-Host "  ❌ 不覆盖用户现有记忆/会话数据"
Write-Host "  ❌ 不接管 hermes 命令；hermes 永远必须打开 Hermes Agent 原生入口"
Write-Host ""
if (!$Force) {
    $confirm = Read-Host "确认开始安装？(y/N)"
    if ($confirm -notmatch '^[Yy]') { Write-Host "已取消"; exit 0 }
}

Test-HermesEntrypoint "安装前入口检查"

Write-Host ""
Write-Host "📦 [1/7] 备份现有配置..." -ForegroundColor Cyan
Ensure-Dir $BackupDir
if (Test-Path $ConfigFile) { Copy-Item $ConfigFile (Join-Path $BackupDir "config.yaml") -Force }
if (Test-Path $EnvFile) { Copy-Item $EnvFile (Join-Path $BackupDir ".env") -Force }
if (Test-Path $PhoenixHome) { Copy-Item $PhoenixHome (Join-Path $BackupDir "phoenix") -Recurse -Force }
Write-Host "  ✅ 备份目录: $BackupDir" -ForegroundColor Green

Write-Host ""
Write-Host "📁 [2/7] 安装 Phoenix 文件..." -ForegroundColor Cyan
Ensure-Dir $PhoenixHome
$dirs = @("core","router","executor","memory","self_heal","integration","security","adapt","sandbox","workflow","github","desktop","plugins","config","skills","tests")
foreach ($d in $dirs) {
    $src = Join-Path $PkgDir $d
    $dst = Join-Path $PhoenixHome $d
    if (Test-Path $src) {
        if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
        Copy-Item $src $dst -Recurse -Force
    }
}
$files = @(
    "phoenix.py","__init__.py","cli.py","doctor.py","config.json","auto_save.py","auto_fusion.py","post_upgrade_hook.sh","install.sh","install.ps1",
    "sim_verify_v8.py","VERSION.md","CHANGELOG.md","CLAUDE.md","README.md","START_HERE.md","DELIVERY_GUIDE.md","INSTALL_GUIDE.md","USER_GUIDE.md","ARCHITECTURE.md","phoenix.yaml",
    "不死鸟_Phoenix_V8_使用说明书.md","不死鸟_Phoenix_V8_技术细则与路径原理.md",
    "INSTALL_安装说明_完整版.md","INSTALL_平台选择_macOS_Windows_WSL_Linux.md","INSTALL_CUSTOMER_一页纸.md","INSTALL_装前装后对比_Hermes与不死鸟.md",
    "RELEASE_交付流程与验收.md","HERMES_融合与随版本升级.md","HERMES_TUI_与不死鸟斜杠指令.md","PHOENIX_V8_CORE_DELIVERY.md","Phoenix_V8_初心回归_架构蓝图.md"
)
foreach ($f in $files) {
    $src = Join-Path $PkgDir $f
    if (Test-Path $src) { Copy-Item $src (Join-Path $PhoenixHome $f) -Force }
}
Get-ChildItem $PhoenixHome -Recurse -Include "__pycache__","*.pyc" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "  ✅ Phoenix 文件安装完成" -ForegroundColor Green

Write-Host ""
Write-Host "🔌 [3/7] 同步 Hermes 插件（双路径强制覆盖）..." -ForegroundColor Cyan
$srcPlugin = Join-Path $PhoenixHome "plugins\phoenix_full"
if (!(Test-Path $srcPlugin)) { Write-Host "  ❌ Phoenix 插件源目录不存在: $srcPlugin" -ForegroundColor Red; exit 1 }
function Sync-PluginDir([string]$dst, [string]$label) {
    if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
    Ensure-Dir $dst
    Copy-Item (Join-Path $srcPlugin "*") $dst -Recurse -Force
    Get-ChildItem $dst -Recurse -Include "__pycache__","*.pyc" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "  ✅ 插件已同步($label): $dst" -ForegroundColor Green
}
if (Test-Path $HermesAgentDir) {
    Sync-PluginDir $BundledPluginDir "bundled"
} else {
    Write-Host "  ⚠️ 未找到 Hermes 源码目录: $HermesAgentDir，跳过 bundled 同步" -ForegroundColor Yellow
}
Sync-PluginDir $UserPluginDir "user"
Patch-HermesCliVerboseCompat

Write-Host ""
Write-Host "🎨 [4/7] 安装 Phoenix 皮肤..." -ForegroundColor Cyan
Ensure-Dir $SkinsDir
$skinSource = Join-Path $PkgDir "_package_skins\phoenix.yaml"
if (!(Test-Path $skinSource)) { $skinSource = Join-Path $PkgDir "phoenix.yaml" }
if (Test-Path $skinSource) { Copy-Item $skinSource (Join-Path $SkinsDir "phoenix.yaml") -Force }
else {
@'
name: phoenix
description: "不死鸟 Phoenix — 浴火不灭，迭代永生"
branding:
  agent_name: "Hermes × Phoenix"
  welcome: "🔥 Hermes × Phoenix — 浴火不灭，迭代永生"
  goodbye: "🔥 不死鸟浴火，下次重生再见！"
  response_label: " 🔥 Phoenix "
'@ | Set-Content -Path (Join-Path $SkinsDir "phoenix.yaml") -Encoding UTF8
}
Write-Host "  ✅ 皮肤已安装: $(Join-Path $SkinsDir 'phoenix.yaml')" -ForegroundColor Green

Write-Host ""
Write-Host "⚙️ [5/7] 写入 Hermes 基础配置..." -ForegroundColor Cyan
Set-ConfigYaml "display.skin" "phoenix"
Set-ConfigYaml "display.resume_display" "full"
Set-ConfigYaml "display.tui_auto_resume_recent" "true"
Set-ConfigYaml "display.streaming" "true"
Set-ConfigYaml "compression.enabled" "true"
Set-ConfigYaml "compression.threshold" "0.5"
Set-ConfigYaml "compression.target_ratio" "0.2"
Set-ConfigYaml "checkpoints.enabled" "true"
Set-ConfigYaml "checkpoints.max_snapshots" "50"
Set-ConfigYaml "memory.memory_enabled" "true"
Set-ConfigYaml "memory.user_profile_enabled" "true"
Set-ConfigYaml "privacy.redact_pii" "true"
Set-ConfigYaml "plugins.enabled" "[phoenix-full,disk-cleanup]"
Write-Host "  ✅ 基础配置完成" -ForegroundColor Green

Write-Host ""
Write-Host "🤖 [6/7] 引导配置模型与 Key" -ForegroundColor Cyan
Write-Host "说明：这里填的是用户自己的 Key。安装包没有内置任何开发者 Key。"

Write-Host "模型链路说明：primary 是默认入口；fallback 是欠费/超时/失败时的救场模型。"
Write-Host "本地模型也可以做 fallback，例如 Ollama/LM Studio/vLLM 的 OpenAI 兼容地址。"
Write-Host ""

$dailyModel = Read-Host "日常默认模型 primary [xiaomi/mimo-v2.5]"
if (!$dailyModel) { $dailyModel = "xiaomi/mimo-v2.5" }
if (!(Validate-ModelName $dailyModel)) { Write-Host "❌ 模型名格式不合法: $dailyModel" -ForegroundColor Red; exit 1 }

$dailyFallbackModel = Read-Host "日常兜底模型 fallback [xiaomi/mimo-v2-flash]"
if (!$dailyFallbackModel) { $dailyFallbackModel = "xiaomi/mimo-v2-flash" }
if (!(Validate-ModelName $dailyFallbackModel)) { Write-Host "❌ 兜底模型名格式不合法: $dailyFallbackModel" -ForegroundColor Red; exit 1 }

$dailyUrl = Read-Host "日常默认模型 Base URL [https://inference-api.nousresearch.com/v1]"
if (!$dailyUrl) { $dailyUrl = "https://inference-api.nousresearch.com/v1" }
if (!(Validate-Url $dailyUrl)) { Write-Host "❌ Base URL 格式不合法: $dailyUrl" -ForegroundColor Red; exit 1 }

$dailyProvider = Read-Host "日常默认模型 Provider 名称 [nous-api]"
if (!$dailyProvider) { $dailyProvider = "nous-api" }

$dailyKeySecure = Read-Host "请输入日常默认模型 API Key（不回显，可回车跳过）" -AsSecureString
$dailyKey = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($dailyKeySecure))
if ($dailyKey) {
    Upsert-Env "PHOENIX_DAILY_API_KEY" $dailyKey
    Write-Host "  ✅ 日常默认模型 Key 已写入本机 .env: $(Mask-Key $dailyKey)" -ForegroundColor Green
} else { Write-Host "  ⚠️ 未填写日常默认模型 Key，后续需手动配置" -ForegroundColor Yellow }

$fallbackUrl = Read-Host "兜底模型 Base URL（回车复用日常；本地可填 http://localhost:11434/v1）[$dailyUrl]"
if (!$fallbackUrl) { $fallbackUrl = $dailyUrl }
if (!(Validate-Url $fallbackUrl)) { Write-Host "❌ 兜底 Base URL 格式不合法: $fallbackUrl" -ForegroundColor Red; exit 1 }

$fallbackProvider = Read-Host "兜底模型 Provider 名称 [$dailyProvider]"
if (!$fallbackProvider) { $fallbackProvider = $dailyProvider }

$fallbackKeySecure = Read-Host "请输入兜底模型 API Key（不回显，可回车复用日常Key/本地模型可跳过）" -AsSecureString
$fallbackKey = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($fallbackKeySecure))
if ($fallbackKey) {
    Upsert-Env "PHOENIX_FALLBACK_API_KEY" $fallbackKey
    $fallbackKeyEnv = "PHOENIX_FALLBACK_API_KEY"
    Write-Host "  ✅ 兜底模型 Key 已写入本机 .env: $(Mask-Key $fallbackKey)" -ForegroundColor Green
} else {
    $fallbackKeyEnv = "PHOENIX_DAILY_API_KEY"
    Write-Host "  ℹ️ 兜底模型默认复用日常 Key；本地模型无 Key 也可后续手动调整" -ForegroundColor Yellow
}

$deepModel = Read-Host "深度模型名 [/深度，默认 anthropic/claude-sonnet-4.6]"
if (!$deepModel) { $deepModel = "anthropic/claude-sonnet-4.6" }
if (!(Validate-ModelName $deepModel)) { Write-Host "❌ 模型名格式不合法: $deepModel" -ForegroundColor Red; exit 1 }

$godModel = Read-Host "大神模型名 [/大神，默认 anthropic/claude-opus-4.7]"
if (!$godModel) { $godModel = "anthropic/claude-opus-4.7" }
if (!(Validate-ModelName $godModel)) { Write-Host "❌ 模型名格式不合法: $godModel" -ForegroundColor Red; exit 1 }

$superSecondaryModel = Read-Host "真神第二模型名 [/真神，默认 openai/gpt-5.5]"
if (!$superSecondaryModel) { $superSecondaryModel = "openai/gpt-5.5" }
if (!(Validate-ModelName $superSecondaryModel)) { Write-Host "❌ 模型名格式不合法: $superSecondaryModel" -ForegroundColor Red; exit 1 }

$premiumUrl = Read-Host "高档模型 Base URL（Claude/OpenAI聚合端点）[$dailyUrl]"
if (!$premiumUrl) { $premiumUrl = $dailyUrl }
if (!(Validate-Url $premiumUrl)) { Write-Host "❌ 高档 Base URL 格式不合法: $premiumUrl" -ForegroundColor Red; exit 1 }

$premiumKeySecure = Read-Host "请输入高档模型 API Key（不回显，可回车复用日常Key/后续手动配）" -AsSecureString
$premiumKey = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($premiumKeySecure))
if ($premiumKey) {
    Upsert-Env "PHOENIX_PREMIUM_API_KEY" $premiumKey
    Write-Host "  ✅ 高档模型 Key 已写入本机 .env: $(Mask-Key $premiumKey)" -ForegroundColor Green
}

Set-ConfigYaml "phoenix.router.daily_model" $dailyModel
Set-ConfigYaml "phoenix.router.daily_provider" $dailyProvider
Set-ConfigYaml "phoenix.router.daily_base_url" $dailyUrl
Set-ConfigYaml "phoenix.router.daily_key_env" "PHOENIX_DAILY_API_KEY"
Set-ConfigYaml "phoenix.router.daily_fallback_model" $dailyFallbackModel
Set-ConfigYaml "phoenix.router.daily_fallback_provider" $fallbackProvider
Set-ConfigYaml "phoenix.router.daily_fallback_base_url" $fallbackUrl
Set-ConfigYaml "phoenix.router.daily_fallback_key_env" $fallbackKeyEnv
Set-ConfigYaml "phoenix.router.deep_model" $deepModel
Set-ConfigYaml "phoenix.router.deep_fallback_model" $dailyFallbackModel
Set-ConfigYaml "phoenix.router.god_model" $godModel
Set-ConfigYaml "phoenix.router.god_fallback_model" $deepModel
Set-ConfigYaml "phoenix.router.super_god_primary" $godModel
Set-ConfigYaml "phoenix.router.super_god_secondary" $superSecondaryModel
Set-ConfigYaml "phoenix.router.super_god_fallback_model" $deepModel
Set-ConfigYaml "phoenix.router.premium_base_url" $premiumUrl
Set-ConfigYaml "phoenix.routing.high_tier_trigger" "manual_only"
Set-ConfigYaml "phoenix.fallback.enabled" "true"
Set-ConfigYaml "phoenix.fallback.on_status_codes" "[401,402,403,429,500,502,503,504]"
Set-ConfigYaml "phoenix.fallback.on_errors" "[timeout,connection_error,rate_limit,insufficient_quota]"
Set-ConfigYaml "phoenix.providers.daily.model" $dailyModel
Set-ConfigYaml "phoenix.providers.daily.provider" $dailyProvider
Set-ConfigYaml "phoenix.providers.daily.base_url" $dailyUrl
Set-ConfigYaml "phoenix.providers.daily.key_env" "PHOENIX_DAILY_API_KEY"
Set-ConfigYaml "phoenix.providers.daily_fallback.model" $dailyFallbackModel
Set-ConfigYaml "phoenix.providers.daily_fallback.provider" $fallbackProvider
Set-ConfigYaml "phoenix.providers.daily_fallback.base_url" $fallbackUrl
Set-ConfigYaml "phoenix.providers.daily_fallback.key_env" $fallbackKeyEnv

Write-Host "  🧭 写入 Phoenix V8 手动升档路由配置..." -ForegroundColor Cyan
$configPy = @'
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
'@
$tmpCfg = Join-Path $env:TEMP "phoenix_open_config.py"
Set-Content -Path $tmpCfg -Value $configPy -Encoding UTF8
python $tmpCfg (Join-Path $PhoenixHome "config.json") $dailyModel $dailyProvider $dailyUrl $dailyFallbackModel $fallbackProvider $fallbackUrl $fallbackKeyEnv $deepModel $godModel $superSecondaryModel $premiumUrl
Remove-Item $tmpCfg -Force -ErrorAction SilentlyContinue
Write-Host "  ✅ 模型映射已写入 config.yaml + config.json：daily不切 / medium不自动切 / 高档手动确认" -ForegroundColor Green

Write-Host ""
Write-Host "🧪 [7/7] 本地自检 + doctor 闭环..." -ForegroundColor Cyan
$testPy = @"
from pathlib import Path
import py_compile
root = Path(r'$PhoenixHome')
for rel in ['phoenix.py', 'doctor.py', 'router/engine.py', 'plugins/phoenix_full/__init__.py', 'memory/memory_system.py', 'self_heal/antibody.py']:
    py_compile.compile(str(root / rel), doraise=True)
print('  ✅ Python核心文件语法正常')
"@
$tmpTest = Join-Path $env:TEMP "phoenix_selfcheck.py"
Set-Content -Path $tmpTest -Value $testPy -Encoding UTF8
python $tmpTest
Remove-Item $tmpTest -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "🩺 [7.1/7] 运行 Phoenix Doctor 自动验收..." -ForegroundColor Cyan
python "$PhoenixHome\doctor.py" --fix --home "$HermesHome" --phoenix-home "$PhoenixHome" --hermes-agent-dir "$HermesAgentDir"

Restart-Gateway

Write-Host ""
Write-Host "🔁 [7.2/7] 复测 Phoenix Doctor..." -ForegroundColor Cyan
python "$PhoenixHome\doctor.py" --verify --home "$HermesHome" --phoenix-home "$PhoenixHome" --hermes-agent-dir "$HermesAgentDir"

Test-HermesEntrypoint "安装后入口复检"

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  ✅ Phoenix 安装完成" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host "下一步建议："
Write-Host "  1. 打开 Hermes/TUI 或 Telegram 发：你好"
Write-Host "  2. 测试日常模式：在吗（不切模型）"
Write-Host "  3. 测试普通模式：深度学习是什么？（不应弹高成本确认）"
Write-Host "  4. 测试高档模式：/深度 帮我分析这个项目（应弹确认）"
Write-Host "  4. 查看 Gateway 状态：hermes gateway status"
Write-Host ""

Write-Host ""
Write-Host "🔥 Phoenix V8 路由启动方式：" -ForegroundColor Cyan
Write-Host "  普通聊天：直接发，不会自动切高档"
Write-Host "  深度任务：/深度 你的任务"
Write-Host "  大神任务：/大神 你的任务"
Write-Host "  真神任务：/真神 你的任务"
Write-Host "  回复：确认 / 降级 / 取消"
Write-Host "  主模型失败：自动走 fallback / emergency；执行完回默认"
