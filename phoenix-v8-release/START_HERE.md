# Phoenix V8 初心回归版

定位：手动升档 + 自动托底 + 自动安装验收。

**核心交付总览（给老板/客户对口径）**：见同目录 **[PHOENIX_V8_CORE_DELIVERY.md](./PHOENIX_V8_CORE_DELIVERY.md)**（含 V8 变更点、安装与模型「写死」争议、验收话术）。

**完整架构蓝图（与 FreeRoute 蓝图同级篇幅）**：[Phoenix_V8_初心回归_架构蓝图.md](./Phoenix_V8_初心回归_架构蓝图.md) — 手动挡 vs 自动路由、自愈/记忆、hermes 入口铁律、路线图。

**⭐ 完整安装说明（交付首选）**：[INSTALL_安装说明_完整版.md](./INSTALL_安装说明_完整版.md) — 终端交互≠网页、每一步问答对照表、Key 落盘位置、装完怎么改、验收话术。

**⭐ 装前 vs 装后（详细对比 · 可做信息图）**：[INSTALL_装前装后对比_Hermes与不死鸟.md](./INSTALL_装前装后对比_Hermes与不死鸟.md) — 未装/已装 Hermes 差异点清单、密钥当时接/事后接、单模型与多模型两形态、手动档原因、做图分镜建议。

**⭐ 使用说明书（操作细节、每一步该怎么理解）**：[不死鸟_Phoenix_V8_使用说明书.md](./不死鸟_Phoenix_V8_使用说明书.md)

**⭐ 技术细则（路径怎么走、记忆原理、模块如何串联）**：[不死鸟_Phoenix_V8_技术细则与路径原理.md](./不死鸟_Phoenix_V8_技术细则与路径原理.md)

**内部：打包 / 验收顺序 / 要不要重装 Hermes**：[RELEASE_交付流程与验收.md](./RELEASE_交付流程与验收.md) — 装完跑 `scripts/post_install_smoke.sh`；Mac/Win/WSL 矩阵。

**Hermes 升级后如何与不死鸟融合**：[`HERMES_融合与随版本升级.md`](./HERMES_融合与随版本升级.md) — `auto_fusion.py`、`post_upgrade_hook`、与原生架构的关系。

**TUI 里 `/深度` 报 Unknown command（必须对齐 Hermes 补丁）**：[HERMES_TUI_与不死鸟斜杠指令.md](./HERMES_TUI_与不死鸟斜杠指令.md)

**新人安装防晕（一页纸）**：[INSTALL_CUSTOMER_一页纸.md](./INSTALL_CUSTOMER_一页纸.md) — 算不算一键、默认/兜底/高档三层、网关自动重启、最短复制命令。

**Mac / Windows / WSL / Linux 用哪个脚本**：[INSTALL_平台选择_macOS_Windows_WSL_Linux.md](./INSTALL_平台选择_macOS_Windows_WSL_Linux.md)

## 一句话讲给客户
普通聊天不用管；只有要更强能力时，手动输入 `/深度`、`/大神`、`/真神`。系统会先弹确认，确认后才切高档；主模型失败自动走备用/紧急模型，执行完自动回默认。

## 路由启动命令

| 场景 | 输入方式 | 是否自动切高档 |
|---|---|---|
| 普通聊天 | 直接发消息 | 否 |
| 深度分析 | `/深度 你的任务` | 弹确认后切 |
| 架构/复杂执行 | `/大神 你的任务` | 弹确认后切 |
| 最高档 | `/真神 你的任务` | 弹确认后切 |

普通句子如“深度学习是什么”“认真分析一下”不会触发高档。必须有斜杠命令。

## 确认框怎么用

客户看到确认框后回复：

```text
确认  → 使用该档主模型执行；失败自动 fallback/emergency；执行完切回默认
降级  → 不切高档，用默认模型执行
取消  → 不执行
```

## 五档结构

- daily：默认入口，不需要触发，不自动升档
- medium：预留档，默认关闭自动触发
- deep：`/深度`
- god：`/大神`
- super_god：`/真神`

每档都有 primary/fallback/emergency；super_god 额外预留 secondary，但第一版不默认并行。

## 验收口径

安装后执行：

```bash
python3 ~/.hermes/phoenix/doctor.py --fix
hermes gateway restart || hermes gateway start
python3 ~/.hermes/phoenix/doctor.py --verify
hermes gateway status
```

测试消息：

```text
你好
深度学习是什么？
/深度 帮我分析这个项目
/大神 帮我设计系统架构
/真神 帮我做最终方案
```

期望：第二条不弹高档确认；后三条弹确认。

## 安全边界

- 不内置 API Key
- Key 只写入客户本机 `.env`
- 日志和报告只显示 env 变量名或 `[REDACTED]`
- OpenAI 兼容端点统一使用 `chat_completions`

## 第一次怎么做
1. 解压发布包。
2. 运行 `bash install.sh`。
3. 按提示填写模型、Provider、Base URL、API Key。
4. 安装器会自动 doctor、Gateway restart/status。
5. 用上面的五条测试消息验收。
