# Phoenix V8 核心交付说明（审稿版）

**版本**：V8「初心回归版」  
**文档用途**：给交付方 / 客户对接人一份**口径统一**的说明，对应发布包内代码与 `install.sh` 的真实行为。  
**约定**：下文「Hermes」指 Nous Hermes Agent；「不死鸟 / Phoenix」指本安装包提供的插件与 `~/.hermes/phoenix` 运行时。

---

## 0. 跟 Hermes 原生能力的关系：**叠加，不是替换**

### 0.1 你们熟悉的 Hermes 用法还在不在？

- **终端里敲 `hermes`**：打开的是 **Hermes Agent 本体 CLI**。Phoenix 的定位是 **插件 + `~/.hermes/phoenix` 里的逻辑**，**不应该、也不能**把自己伪装成 `hermes` 命令。
- **会话里用斜杠切模型**（例如某些界面下 `/` + 模型名）：这是 **Hermes / 各前端自带的能力**，用来改**全局默认模型**或会话模型。  
- **不死鸟 V8 做的事**：在**同一条对话管线**里，额外识别 **`/深度`、`/大神`、`/真神`** 三条**业务口令**，走「确认 → 真 `switch_model` → fallback/emergency」——这是 **加一层「档位任务」**，**不是**取消 Hermes 自带的模型切换。

一句话：**底层仍是 Hermes；Phoenix 是在上面挂插件与配置，而不是 forks 掉 Hermes。**

### 0.2 「在此基础上改」到底改哪？

| 层次 | 谁负责 | V8 的态度 |
|------|--------|----------------|
| Hermes 安装、`hermes` 命令、Gateway | Nous / 用户环境 | **不劫持**：`install.sh` / `install.ps1` 里有 **`check_hermes_entrypoint`**，若检测到 `hermes` 指向 Phoenix 目录或 Phoenix CLI 文案，**安装会失败并提示**。 |
| 用户换默认模型 | Hermes 自带 UI 或改 `config.yaml` | **保留**；客户日常用什么模型，仍以 Hermes 配置为准。 |
| 高档任务 / 成本敏感档位 | Phoenix `phoenix_open` + 插件 | **只做三条口令 + 确认托底**，与「手动输入模型名切换默认模型」是**两类操作**，并行存在。 |

### 0.3 终端输入 `hermes` 没反应 / 进了不死鸟 —— **这不是交付目标**

官方安装脚本**明确禁止**「把 Phoenix 的 cli 链接成 `hermes`」。若现场仍出现：

1. **先区分**：`command not found`（没装 Hermes 或 PATH 里没有 pipx 链） vs **能运行但是不死鸟文案**（被 alias/shim 劫持）。  
2. **自检命令**（给客户或运维）：`which hermes`、`type hermes`（fish/bash）、`hermes --help` 前几行是否 Hermes 官方帮助。  
3. **常见修复**：  
   - `pipx ensurepath` 后重开终端；  
   - 删掉 shell 里错误的 `alias hermes=...`、`function hermes`、以及把 Phoenix `cli.py` 链到 PATH 里名叫 `hermes` 的脚本；  
   - **不要用旧教程**把 Phoenix 设成系统里的 `hermes`。

**结论**：「连入口都改了」属于 **错误部署或旧文档害人**，不是 V8 设计目标；交付时应把 **`check_hermes_entrypoint` 必须通过** 当作硬门槛。

### 0.4 为何外面仍会觉得版本多、bug 多？

- **Hermes 上游常升级**，插件必须跟着测 Gateway / CLI。  
- **三方 API**（模型名、502、413）不是 Phoenix 单方能消灭的。  
- **边界若不写清**（Hermes 全局 vs Phoenix 档位、`hermes` 不能被劫持），现场就会像你现在看到的这样混在一起骂。

本交付说明 §0 就是为减少这类混乱；**真要「正儿八经」**：安装验收里加一条 **`hermes --help` 正常 + `check_hermes_entrypoint` 绿**，再交付。

---

## 1. 这一版到底要交付什么？

### 1.1 产品一句话

**默认日常对话不偷偷升档；只有用户显式输入 `/深度`、`/大神`、`/真神` 时才进入高档流程；高档必须先确认（确认 / 降级 / 取消）；主模型失败时按档内配置自动走 fallback / emergency（托底），任务结束后回到日常默认。**

### 1.2 刻意**不做**的事（与旧版「智能路由乱切模型」划界）

| 行为 | V8 口径 |
|------|-------------|
| 聊天里一句话自动切到贵模型 | **不允许**（日常不自动升档；高档只靠斜杠口令 + 确认） |
| Hook 里「假切换」只改显示不改 client | **禁止**（插件侧要求走真实 `switch_model`） |
| 把 API Key 打进仓库 / 安装包 | **禁止**（Key 仅客户本机 `.env`，安装脚本不回显） |
| OpenAI 兼容网关协议混乱 | **统一**为 `chat_completions`（与 Hermes transport 注册一致） |

---

## 2. V8 **相对此前 Phoenix 路线**改了什么？

以下为**架构/产品层**变更摘要（细节以 `HOTFIX_NOTES.md`、`plugins/phoenix_full/__init__.py`、`config.json` 的 `phoenix_open` 为准）。

1. **手动挡三口令**：只认 **`/深度`**、**`/大神`**、**`/真神`** 作为高档入口（普通句子不会触发）。
2. **取消「自动升档」叙事**：`phoenix_open.model_tiers` 内 **`auto_execute` 为 false**；medium 档默认 **enabled: false**（预留，不自动跑出来）。
3. **确认后再执行**：高档对应 **`requires_approval: true`**，由插件侧确认流实现（CLI/Gateway 等通道需能展示确认语义）。
4. **真切换模型**：通过 **`AIAgent.switch_model(..., api_mode="chat_completions", ...)`** 完整切换，而不是只改字符串。
5. **每档三层兜底**：primary → fallback → emergency；失败自动尝试下一层（插件与 ProviderResolver 协同）。
6. **密钥与 endpoint**：包内**不包含**客户 Key；安装过程在**终端**询问 Base URL / Key，写入 **`~/.hermes/.env`**（变量名如 `PHOENIX_DAILY_API_KEY` 等），并在 `config.yaml` 的 `phoenix.*` 与 `phoenix_home/config.json` 中绑定引用。
7. **安装边界**：`install.sh` 含 **`check_hermes_entrypoint`**，防止 Phoenix CLI **劫持**系统里的 `hermes` 命令（会与 Hermes Agent 冲突）。

---

## 3. 客户反馈的几个问题 —— 交付口径怎么解释？

### 3.1 「安装后不能在聊天页面输入 API」

**正确口径**：**API / Key / Base URL 本来就不应在「聊天窗口」里配置。**

- **官方路径**：解压包后运行 **`bash install.sh`（macOS/Linux）或 `install.ps1`（Windows）**。脚本第 **[6/7] 步**在**终端交互**里收集默认模型、兜底模型、各 URL 与 Key（Key **不回显**）。
- Hermes / Telegram / TUI 的聊天界面**不是** Phoenix 的配置台；若旧文档让客户在聊天里「粘贴 Key」，属于**错误流程**，应以本版安装脚本为准。

### 3.2 「会乱换模型、自己切模型」

**设计口径**：

- **日常**：始终用安装时约定的 **daily 默认模型**（及失败时的 fallback/emergency），**不会因为闲聊内容自动升到 Claude/GPT 高价档**。
- **高档**：只有 **`/深度` / `/大神` / `/真神`** 才会进入高档逻辑，且需要用户 **`确认`**；**`降级`** 表示仍用默认档执行。
- 若客户仍观察到「无端换模型」，优先排查：
  1. **`~/.Hermes/config.yaml` 顶层 `model.default`** 是否与三方控制台一致（见 §4）；
  2. 是否混用了 **旧版 Phoenix / 旧插件**，或存在 **其它插件**改模型；
  3. **三方网关**是否在服务端擅自改路由（需换节点或向供应商反馈）。

### 3.3 「模型应自由、不要写死」——和本包的关系

需分清两层：

| 层级 | 作用 | 客户如何「自由」 |
|------|------|------------------|
| **Hermes 全局** | `~/.Hermes/config.yaml` 里 **`model.default`**、**`model.base_url`**、**`model.api_key`**（或 env） | 决定 **TUI/CLI 默认连哪个模型**。客户可用 **`hermes model`**（若当前 Hermes 版本支持）或**直接编辑 config.yaml** 修改。 |
| **Phoenix 档位** | `~/.../phoenix/config.json` → **`phoenix_open.model_tiers`** | 决定 **`/深度` 等三档**各自用哪个模型、fallback、emergency。**安装脚本会把用户在终端里填的 daily/deep/god 等写进来**。 |

**交付要说清楚**：

- 「不写死」≠「聊天里随便一句话换全局模型」。**全局默认**靠改 Hermes 配置或官方 CLI；**高档**靠三条口令 + 确认。
- 发布 zip 里的 **`config.json`（含大量示例厂商名）** 是**结构模板**；客户真实机器上的文件会被 **`install.sh` 末尾 Python 段覆写 `phoenix_open`**，以安装时输入为准。

### 3.4 个案：某客户变成 `gpt-5.4-mini` + `nuoapi.com` 一类

这通常**不是** zip 里「偷偷写死」，而是：

1. 客户（或旧脚本）曾**手动改过** `~/.Hermes/config.yaml`；或  
2. 使用了**另一供应商的安装指引**，把 Hermes 全局指到了 nuoapi；或  
3. **custom provider** 下 Hermes 内置模型菜单不可用，只能靠改配置文件。

**修复建议（给客户）：**

1. 打开 `~/.Hermes/config.yaml`，检查 **`model.default`**、**`model.base_url`**，改成自己控制台支持的模型名与 URL。  
2. 重新运行 **`bash ~/.hermes/phoenix/install.sh`**（或包内 install），按终端提示**重新绑定** daily / fallback / premium。  
3. **`hermes gateway restart`** 后测试 §5 验收消息。

---

## 4. 安装脚本实际写了哪些位置？（避免「以为只改了 Phoenix」）

`install.sh` 会做包括但不限于：

- **`~/.hermes/.env`**：`PHOENIX_DAILY_API_KEY`、`PHOENIX_FALLBACK_API_KEY`、`PHOENIX_PREMIUM_API_KEY` 等（若用户输入）。  
- **`~/.hermes/config.yaml`**：**`phoenix.router.*`、`phoenix.providers.*`**、显示/压缩/checkpoint 等 **Hermes 侧键**（通过 `set_config_yaml`）。  
- **`~/.hermes/phoenix/config.json`**：重写 **`phoenix_open.model_tiers`** 与 **`phoenix_open.providers`**（安装末尾 Python 段）。

**注意**：当前脚本**重点写 `phoenix.*` 与 `config.json`**；若要让 **Hermes 顶层 `model.default` 与 daily 完全一致**，需要**要么**在安装后手动对齐 **`model.default`**，**要么**在后续迭代里由安装器增加「同步写入 `model.default`」步骤（可作为产品改进项单独排期）。

---

## 5. 交付验收消息（与客户演示脚本）

安装完成后：

```bash
python3 ~/.hermes/phoenix/doctor.py --verify --home ~/.hermes --phoenix-home ~/.hermes/phoenix --hermes-agent-dir <实际 hermes-agent 路径>
hermes gateway status
```

聊天侧建议五条：

```text
你好
深度学习是什么？
/深度 帮我分析这个项目
/大神 帮我设计系统架构
/真神 帮我做最终方案
```

**期望**：第 2 条**不弹**高档确认；第 3–5 条**弹确认**；回复 **`降级`** 时用默认档执行。

---

## 6. 静态交付 vs 真实环境（对客户诚实）

本仓库 **`sim_verify_v8.py`** 已覆盖：包完整性、敏感信息扫描、install 静态链、`phoenix_open` 手动挡语义、插件静态审计、doctor 隔离环境等。

**不等价于**：真实 Windows 全流程安装、Telegram/Gateway 人工全链路、真实计费 Key 跑通所有模型名。

交付话术建议：**「安装包与静态验收已通过；请你方在自己网络与 Key 下按 §5 做一轮冒烟。」**

---

## 7. 修订记录（文档）

| 日期 | 说明 |
|------|------|
| 2026-05-09 | 初稿：合并 HOTFIX / START_HERE / install.sh 行为与客户投诉口径 |

---

**审稿时请重点看**：§3（与客户争议的对应）、§4（Hermes 全局 vs Phoenix 档位）、§4 末尾「是否要在安装器里同步 `model.default`」是否符合你们的产品决策。
