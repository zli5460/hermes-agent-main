# 不死鸟 Phoenix V8

**产品标识**：Phoenix V8（初心回归版）  
**配置 / 插件 semver**：`8.0.0`（见 `config.json`、`plugins/phoenix_full/plugin.yaml`）

## 能力摘要

手动升档 + 自动托底 + 安装验收；路由口令 `/深度`、`/大神`、`/真神`；记忆与自愈模块见 `不死鸟_Phoenix_V8_技术细则与路径原理.md`。

## 与 Hermes 的兼容基线

| 项目 | 版本 / 说明 |
|------|-------------|
| Hermes Agent（本仓库 `pyproject.toml`） | **0.13.0** |
| Python | **≥ 3.11**（与 Hermes 一致） |
| Phoenix 运行时目录 `$PHOENIX_HOME` | 默认 **`~/.hermes/phoenix`** |

上游 Hermes：<https://github.com/NousResearch/hermes-agent>

## 相关文件

- 变更明细：`CHANGELOG.md`
- 仓库级记录（根目录）：`REPOSITORY_RECORD.md`
