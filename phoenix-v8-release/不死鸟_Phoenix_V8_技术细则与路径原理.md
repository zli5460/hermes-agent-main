# 不死鸟 Phoenix V8 — 技术细则与路径原理（完整版）

**读者**：实施 / 二次开发 / 深度客户  
**约定**：下文路径均以 **`$HERMES_HOME`**（默认 **`~/.hermes`**）与 **`$PHOENIX_HOME`**（默认 **`~/.hermes/phoenix`**）表述，不写死某台机器用户名。

---

## 目录

1. [目录树速查](#1-目录树速查)  
2. [一次请求的粗略路径](#2-一次请求的粗略路径)  
3. [配置权威与优先级](#3-配置权威与优先级)  
4. [路由（V8 手动挡）原理](#4-路由v8-手动挡原理)  
5. [真切换与 api_mode](#5-真切换与-api_mode)  
6. [记忆系统：落盘与原理](#6-记忆系统落盘与原理)  
7. [自愈系统 Self-heal](#7-自愈系统-self-heal)  
8. [插件加载位置](#8-插件加载位置)  
9. [与 Hermes 升级融合](#9-与-hermes-升级融合)  
10. [安全与密钥流向](#10-安全与密钥流向)

---

## 1. 目录树速查

```text
~/.hermes/
├── config.yaml              # Hermes 全局；含 model.*、phoenix.router.*、插件列表等
├── .env                     # 客户 Key：PHOENIX_DAILY_API_KEY 等（chmod 建议 600）
├── plugins/phoenix_full/    # 用户插件副本（安装器同步）
├── hermes-agent/            # Hermes 源码/venv（若存在）；bundled 插件路径可能在其中
├── skins/phoenix.yaml       # 皮肤（安装器写入）
└── phoenix/                 # === Phoenix 运行时根目录（PHOENIX_HOME）===
    ├── config.json          # 含 phoenix_open.model_tiers / providers（档位权威之一）
    ├── feature_registry.json
    ├── doctor.py
    ├── auto_fusion.py       # Hermes 升级后扫描融合
    ├── post_upgrade_hook.sh
    ├── plugins/phoenix_full/# 包内带来的插件源（与 Hermes 侧同步）
    ├── core/ router/ executor/ memory/ self_heal/ integration/ ...
    ├── memory/              # 代码模块；运行时 JSON 多在 persistent 配置所指路径
    └── data/                # 融合日志、适配记录等（若启用）
```

---

## 2. 一次请求的粗略路径

```text
用户消息（任意 Hermes 通道）
    → Hermes 会话层
    → 加载插件 phoenix_full（Hermes 插件机制）
    → 插件内 Monkey-patch / run_conversation 拦截
    → 判断是否精确匹配 /深度 | /大神 | /真神
         ├─ 否：不改高档路由，交给当前默认模型继续
         └─ 是：进入确认状态机 → 用户确认后
                ProviderResolver 解析目标档位绑定
                → AIAgent.switch_model(..., api_mode="chat_completions", ...)
                → 执行任务 → 失败则按档内 candidate 依次 fallback
                → 任务结束回到默认模型策略
```

**要点**：「脑」在插件与 `phoenix_open`；「手」仍是 Hermes 的执行栈与 API 客户端。

---

## 3. 配置权威与优先级

| 层级 | 内容 | 备注 |
|------|------|------|
| **Hermes `config.yaml` 顶层 `model.*`** | 全局默认连哪家模型 | 与 Phoenix daily **应对齐**，否则易出现「界面默认 vs Phoenix 认知」不一致 |
| **`config.yaml` 内 `phoenix.router.*` / `phoenix.providers.*`** | 安装脚本写入的路由摘要 | 便于运维检索 |
| **`phoenix/config.json` → `phoenix_open`** | 档位、providers、`fallback/emergency` | **Phoenix 运行时解析档位的主权威之一** |
| **环境变量 `PHOENIX_*_API_KEY`** | 实际密钥 | 只在 `.env`，不进仓库 |

安装脚本末尾会用 Python 段 **重写 `phoenix_open`**，与客户在安装访谈里输入的 daily/fallback/premium 对齐。

---

## 4. 路由（V8 手动挡）原理

- **触发**：仅 **前缀口令**（实现以插件为准），避免自然语言误触。  
- **auto_execute**：高档档位为 **false**；**daily** 亦不自动升高档。  
- **确认**：高档 **`requires_approval: true`**（配置侧），由插件实现确认 UI。  
- **medium**：默认可 **enabled: false**（预留），防止旧「中等自动跑出来」逻辑复活。

---

## 5. 真切换与 api_mode

必须调用 Hermes **`switch_model`**，并传入与网关一致的 **`api_mode`**（如 **`chat_completions`**），以便 **client / base_url / key** 一并切换。  
禁止仅返回字符串形式的 model id 当作「已切换」。

---

## 6. 记忆系统：落盘与原理

**模块代码**：`phoenix/memory/`（如 `memory_system.py`、`unified_memory.py`、`auto_extract.py`、`sync.py`、`diary.py`、`knowledge_graph.py` 等）。

**配置指向**：在根目录 **`config.json`** 的 `memory.persistence` 等段定义 **`user_profile`、`projects`、`conversations`** 等路径（常为 **`~/.hermes/phoenix/...`** 或扩展名 `.json`）。

**原理分层（简述）**：

| 能力 | 作用 |
|------|------|
| **会话上下文** | 当前对话窗口内的短期记忆 |
| **自动抽取** | 从对话中抽取可重用事实/偏好（策略由配置约束） |
| **同步 / 长期** | 将会话沉淀到更持久结构（具体文件名以配置为准） |
| **日记 / 图谱** | 事件型记录与实体关系（启用时） |

**注意**：记忆 **不负责**「替你自动升模型」；它与 **路由手动挡** 解耦——记忆管「记住什么」，路由管「这一轮用多少钱的模型」。

---

## 7. 自愈系统 Self-heal

**目录**：`phoenix/self_heal/`（`antibody.py`、`evolution.py`、`error_processor.py` 等）。

**思路**：把常见故障模式沉淀为 **抗体 /  playbook**，出错时优先 **按策略修复或降级**，并与 **档位 fallback** 区分——前者偏「系统健康」，后者偏「单次请求模型链路」。

---

## 8. 插件加载位置

安装器会把 **`phoenix_full`** 同步到：

- **`~/.hermes/plugins/phoenix_full/`**（用户插件目录）  
- 若存在 Hermes 源码目录：**`…/hermes-agent/plugins/phoenix_full/`**（bundled）

Hermes 实际加载顺序以 **Hermes 版本**为准；两地强行一致可减少「改了旧副本」问题。

---

## 9. 与 Hermes 升级融合

详见 **`HERMES_融合与随版本升级.md`**。要点：**`auto_fusion.py`**、`post_upgrade_hook`、`adapt/` 报告；**不**与 Hermes 原生 CLI 对抗。

---

## 10. 安全与密钥流向

```text
用户在一键安装终端输入 Key
    → 写入 ~/.hermes/.env（变量名 PHOENIX_*）
    → config / phoenix_open 只保存 api_key_env 名称引用
    → 运行时由 Hermes/插件从环境解析真实 Key
```

日志与对外报告应对 Key **脱敏**。

---

## 附录：与简版文档关系

| 文档 | 侧重 |
|------|------|
| **本文** | 路径、原理、模块边界 |
| **不死鸟_Phoenix_V8_使用说明书.md** | 终端用户操作 |
| **ARCHITECTURE.md** | 七大模块鸟瞰 |
| **INSTALL_安装说明_完整版.md** | 安装步骤 |

---

*修订说明：随 Phoenix 版本迭代同步更新 `VERSION.md` 与本文档版本句。*
