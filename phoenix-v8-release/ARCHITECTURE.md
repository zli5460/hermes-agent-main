# 🦅 不死鸟 Phoenix V8 — 完整架构

## 七大模块

```
┌─────────────────────────────────────────────────────────────┐
│                    不死鸟 Phoenix V8                        │
├─────────┬─────────┬─────────┬─────────┬─────────┬──────────┤
│ ① Core  │ ② Router│③ Executor│ ④ Memory│⑤ SelfHeal│⑥ Integrate│
│ 配置中心 │ 路由引擎 │ 执行管道  │ 记忆系统 │ 自愈进化  │ 集成桥梁  │
└────┬────┴────┬────┴────┬────┴────┬────┴────┬────┴─────┬────┘
     │         │         │         │         │          │
     └─────────┴─────────┴────⑦ Security────────────────┘
                           安全防护层
```

### ① Core — 配置中心
- `core/config.py` — 统一配置管理（dot-path访问、深度合并）
- `core/state.py` — 应用状态管理（事件驱动）
- `core/task.py` — 任务管理（创建、追踪、清理）

### ② Router — 手动升档与兜底链路
- `router/engine.py` — 保留路由决策结构与兼容测试
- V8 默认关闭 daily/medium 自动升档
- 高档只认精确斜杠口令：`/深度`、`/大神`、`/真神`
- 决策流：识别斜杠口令 → 弹确认框 → 用户确认后由插件调用 Hermes `AIAgent.switch_model()` 真切换 → 执行后切回默认
- 模型失败时按当前档位的 `primary → fallback → emergency` 兜底链路处理

### ③ Executor — 执行管道
- `executor/pipeline.py` — 完整执行管道（提取→路由→压缩→存储）
- `executor/micro_compact.py` — 微压缩（tool结果>500字符自动压缩）
- `executor/deep_compact.py` — 深度压缩（上下文超限时）
- `executor/circuit_breaker.py` — 熔断器（模型失败自动切换）
- `executor/skill_loader.py` — 技能懒加载

### ④ Memory — 记忆系统
- `memory/auto_extract.py` — 自动提取（从对话中提取事实/偏好/修正）
- `memory/session.py` — 会话记忆（当前对话上下文）
- `memory/knowledge_graph.py` — 知识图谱（实体+关系）
- `memory/diary.py` — 日记系统（事件记录）
- `memory/sync.py` — 长期同步（session → long_term_memory.json）

### ⑤ Self-heal — 自愈进化
- `self_heal/antibody.py` — 抗体库（错误模式→自动修复）
- `self_heal/evolution.py` — 进化引擎（延迟追踪、性能优化）

### ⑥ Integration — 集成桥梁
- `integration/gateway_api.py` — Gateway统一接口（单例）
- `integration/hermes_bridge.py` — Hermes完整桥接
- `integration/hooks.py` — 生命周期钩子
- `integration/cron_sync.py` — 定时同步
- `integration/startup.py` — 启动初始化

### ⑦ Security — 安全防护（在config中）
- API Key保护（绝不明文输出）
- 频率限制（每日消息上限）
- 预算控制（月度/日度额度）
- 敏感操作审批

---

## 模型矩阵（4家供应商）

### 供应商
| 代号 | 厂商 | 特点 |
|------|------|------|
| MIMO | 小米 | 便宜、快速、中文好 |
| Claude | Anthropic | 推理最强、代码最好 |
| GPT | OpenAI | 全能、稳定 |
| Gemini | Google | 视觉最强、多模态 |

### 五档模型结构
| 档位 | 触发方式 | 执行口径 | 说明 |
|------|---------|---------|------|
| **daily** | 普通消息 | 当前默认模型执行 | 不自动升档 |
| **medium** | 预留 | 默认不自动执行 | 保留配置槽位，避免旧逻辑误触发 |
| **deep** | `/深度 任务` | 确认后主模型执行，失败走 fallback/emergency | 深度分析/代码审计 |
| **god** | `/大神 任务` | 确认后主模型执行，失败走 fallback/emergency | 架构/复杂执行 |
| **super_god** | `/真神 任务` | 确认后主模型执行，secondary 预留不默认并行 | 最高档方案推演 |

每个档位配置 `primary/fallback/emergency`。安装器只写模型名、Provider、Base URL 和 Key 环境变量名；报告不输出真实 Key。

### 任务分类规则

```
用户消息进来
  ↓
Phoenix 插件先判断是否精确以 `/深度`、`/大神`、`/真神` 开头
  ├─ 否 → 不切模型，交给当前 Hermes 主模型正常执行
  └─ 是
      ↓
      返回确认框（此时不调用高档模型）
      ↓
      用户回复
        ├─ 确认 → AIAgent.switch_model 真切换 → 执行任务 → 自动切回默认
        ├─ 降级 → 不切高档，用默认模型执行
        └─ 取消 → 不执行
```

普通句子如“深度学习是什么”“帮我认真分析”不会触发高档。

### 熔断机制

```
模型调用失败
  ↓
当前档位 primary 失败
  ↓
fallback 可用？
  ├─ 是 → 切 fallback 重试
  └─ 否
      ↓
      emergency 可用？
        ├─ 是 → 切 emergency 重试
        └─ 否 → 返回明确失败原因
```

兜底是同一档位内的救援链路，不是关键词自动升档。

### 预算控制

```
月度限额: $50
日度限额: $5
单次限额: $5
  ↓
超限/欠费/超时
  ↓
先走当前档位 fallback
  ↓
fallback 失败再走 emergency
  ↓
三层都失败 → 返回明确错误，不冒充成功
```

---

## 数据流

```
用户消息
  ↓
Hermes CLI/TUI/Gateway 接收
  ↓
Phoenix 插件 hook / run_conversation monkey-patch 检查三条手动口令
  ├─ 普通消息：不干预，Hermes 当前主模型执行
  └─ `/深度`/`/大神`/`/真神`：先弹确认框
      ↓
      用户确认后调用 AIAgent.switch_model() 真切换
      ↓
      Hermes 原生 agent 执行任务
      ↓
      TokenLedger 脱敏记录：档位/模型/env Key 名/动作/成本估算
      ↓
      自动切回默认模型并返回用户
```

---

## 文件结构

```
~/.hermes/phoenix/
├── __init__.py              # 包入口
├── phoenix.py               # 主类（统一入口）
├── config.json              # 路由配置
├── cli.py                   # CLI工具
├── core/                    # ① 配置中心
│   ├── config.py
│   ├── state.py
│   └── task.py
├── router/                  # ② 路由引擎
│   └── engine.py
├── executor/                # ③ 执行管道
│   ├── pipeline.py
│   ├── micro_compact.py
│   ├── deep_compact.py
│   ├── circuit_breaker.py
│   └── skill_loader.py
├── memory/                  # ④ 记忆系统
│   ├── auto_extract.py
│   ├── session.py
│   ├── knowledge_graph.py
│   ├── diary.py
│   └── sync.py
├── self_heal/               # ⑤ 自愈进化
│   ├── antibody.py
│   └── evolution.py
├── integration/             # ⑥ 集成桥梁
│   ├── gateway_api.py
│   ├── hermes_bridge.py
│   ├── hooks.py
│   ├── cron_sync.py
│   └── startup.py
├── skills/                  # 技能系统
│   └── phoenix_skills.py
├── runtime/                 # 客户本机运行时目录，发布包不内置
│   └── token_ledger.jsonl   # 安装后运行时生成，Key只记 env 名
├── reports/                 # 报告
│   └── phoenix_route_map.md
└── tests/                   # 测试
    ├── test_phoenix_v2_smoke.py
    ├── test_session_memory.py
    ├── test_skill_system.py
    └── test_state_event.py
```
