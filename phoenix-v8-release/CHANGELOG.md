# Phoenix V8 变更记录

本文档记录 **不死鸟 Phoenix** 发行包（`phoenix-v8-release/`）相对前一对外标识（V5.1.3）的可见变更。

## [8.0.0] — 2026-05-10

### 安装器

- **`bash install.sh --profile=local-deepseek -y`**：Ollama 本地日常 + DeepSeek 高档口令，无需逐项问答；详见 `PHOENIX_V8_CORE_DELIVERY.md` §0.6。  
- 辅助脚本 **`scripts/apply_profile_local_deepseek.py`**；`doctor` / 语法自检优先使用 Hermes 源码目录下 **`venv/bin/python3`**（若存在）。

### 命名与目录

- 发行目录由 `phoenix-v5.1.3-release` 更名为 **`phoenix-v8-release`**；对外版本标识统一为 **Phoenix V8**（不死鸟）。
- 中文主文档文件名统一为 **`不死鸟_Phoenix_V8_*`**；交付说明 `PHOENIX_V8_CORE_DELIVERY.md`、验证报告 `PHOENIX_V8_VERIFY_REPORT.md`、架构蓝图 `Phoenix_V8_初心回归_架构蓝图.md`。
- 配置与插件 **semver** 使用 **`8.0.0`**（`config.json`、`plugins/phoenix_full/plugin.yaml`、`feature_registry.json` 等）。

### 文档

- 使用说明书中「记忆目录」表述与 **`~/.hermes/phoenix`（`$PHOENIX_HOME`）** 对齐，避免与 `~/phoenix` 混淆。
- 仓库内提供 **`sim_verify_v8.py`**：包完整性、敏感信息粗扫、install 标记、插件口令、`doctor.py --verify` 隔离跑通；可选生成 **`phoenix-v8-release.zip`** 与 **`CHECKSUMS.txt`**。

### 兼容基线

- **Hermes Agent**：与本仓库根目录 `pyproject.toml` 中的 **hermes-agent 版本**（当前 **0.13.0**）一并验证；上游：<https://github.com/NousResearch/hermes-agent>。
