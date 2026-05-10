# Phoenix V8 初心回归版

定位：手动升档 + 自动托底 + 自动安装验收。

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

## 文档入口
- START_HERE.md：第一次打开先看
- INSTALL_GUIDE.md：安装说明
- USER_GUIDE.md：使用说明
- DELIVERY_GUIDE.md：交付人员话术和验收
