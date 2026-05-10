# 不死鸟 Phoenix V8 — 安装说明（完整版）

> **给终端同事 / 客户 IT**：从解压到能说话，装什么、点哪里、会问什么、Key 落哪里，一篇够用。  
> **相关短文**：[平台选 Mac 还是 Windows](./INSTALL_平台选择_macOS_Windows_WSL_Linux.md) · [一页纸防晕](./INSTALL_CUSTOMER_一页纸.md)

---

## 0. 重要：「交互」在哪里？有没有网页？

| 形式 | 当前 V8 发布包 |
|------|-------------------|
| **安装时的问答** | 在 **终端 / PowerShell 里** 出现，脚本 **一行行问你**，你 **键盘输入** 回车即可。**不是浏览器里的网页安装向导。** |
| **Key 输入** | 在终端里问 **「请输入 API Key」** 时输入；**屏幕上不回显**（防偷看），输完回车。 |
| **若以后要做「真正网页安装器」** | 需单独开发（本地开一个小 Web 或桌面向导），**不在本 zip 默认范围内**。 |

所以交付时跟客户说清：**装不死鸟 = 打开终端，跟着字走，没有弹窗网页。**

---

## 1. 安装前准备（少一步都会懵）

1. **已安装 Hermes Agent**（Nous 官方方式装好），且终端里能执行：
   ```bash
   hermes --help
   ```
   能出帮助，再往下装 Phoenix。
2. 已从供应商控制台拿到：**API 地址（Base URL）**、**模型名**、**API Key**（可多条：日常 / 高档若分开）。
3. 解压本发布包到**任意英文路径**（避免仅中文路径在个别环境踩坑）。

### 1.1 以前装过 5.0 / 5.1 / 4.8 等，怎么「覆盖」成 V8？

**不需要先卸载旧不死鸟。** 与新机器一样执行 **`bash install.sh`**（或 Windows 的 **`install.ps1`**），脚本会：

1. **先备份**到 `~/.hermes/backups/phoenix_preinstall_年月日_时分秒/`，内含当时的 **`config.yaml`**、**`.env`**、以及整个旧 **`phoenix/`** 目录（若有）。
2. **再安装**：把 V8 的文件写入 **`~/.hermes/phoenix`**，并对 **`phoenix_full` 插件目录做强制同步覆盖**（bundled + 用户插件双路径，与旧版插件一致替换）。
3. **声明上不覆盖**：安装器横幅写明 **不覆盖用户现有记忆/会话等业务数据目录**（若你方 Hermes/不死鸟历史版本曾把数据放在单独路径，仍以实际目录为准；冲突时优先从备份目录恢复）。

若只希望「保留 Key、换新版代码」：备份已含 `.env`，你也可以在覆盖安装前后自行再拷一份 `.env` 到外置盘。

### 1.2 全新机器怎么装？

1. 按官方流程先装好 **Hermes**，终端里 **`hermes --help`** 能跑。
2. 解压本 zip，在同一终端会话执行 **`bash install.sh`**，按第 4 节问答填 **自己的** Base URL / 模型名 / Key。
3. 若从未配置过 Phoenix，**备份步骤**里可能没有旧 `phoenix/` 目录，属于正常；仍会写入新的 `~/.hermes/phoenix` 与插件。

### 1.3 「安装提示词」在哪？

- **给客户照着念的**：本文 **第 4 节表格**（顺序、会问什么、写入哪里）。
- **终端里脚本自带的**：运行 `install.sh` 时会有 **`read -p` 提问**与 **`模型链路说明`** 等 echo（第 6/7 步），不是 ChatGPT 那种「提示词」，而是 **安装向导文案**。

---

## 2. 选平台：用哪条命令？

| 你的环境 | 安装命令 |
|----------|----------|
| **Mac** | 打开「终端」，`cd` 到解压目录，执行：`bash install.sh` |
| **Linux / 云服务器** | 同上：`bash install.sh` |
| **Windows 里的 WSL（Ubuntu 等）** | 在 **WSL 终端**里：`bash install.sh`（路径在 WSL 里常是 `/mnt/c/...`） |
| **Windows 本机（不用 WSL）** | 用 **PowerShell** 按包内说明执行 **`install.ps1`**（与 `install.sh` 功能对齐，语法为 PowerShell） |

详细见：[INSTALL_平台选择_macOS_Windows_WSL_Linux.md](./INSTALL_平台选择_macOS_Windows_WSL_Linux.md)

---

## 3. 一键安装时，脚本自动帮你做啥（不用你手抄）

在你说 **y 确认开始** 之后，脚本**自动**完成（节选）：

- 备份现有 `config.yaml`、`.env`、旧 `phoenix` 目录到带时间戳目录  
- 把 Phoenix 文件拷到 `~/.hermes/phoenix`（以 `HERMES_HOME` 为准）  
- **双路径覆盖**同步插件 `phoenix_full`（bundled + 用户目录）  
- 安装皮肤、写 Hermes 侧基础项（皮肤、压缩、检查点、插件开关等）  
- 跑 **Phoenix `doctor.py --fix`**，再 **自动 `hermes gateway restart`（或 start）**  
- 再跑 **doctor `verify`**，并检查 **`hermes` 命令有没有被 Phoenix 错误劫持**  

**客户不用自己记「第几步重启网关」——脚本里已做。**

---

## 4. 安装时「交互」会问什么？（配模型 + 配密钥）

下面与 **`install.sh`** 第 **\[6/7\]** 步 **一一对应**（你填的内容会进 **本机** `~/.hermes/.env` 和 `config.yaml` / `phoenix/config.json`）。

> 提示：方括号 `[默认]` 表示 **直接回车** 就用默认值。

| 顺序 | 终端里大概会显示 | 你填什么 | 写入 / 用途 |
|------|------------------|----------|-------------|
| 1 | 日常默认模型 primary | 三方控制台上 **日常聊天** 用的模型 ID | 默认档 daily |
| 2 | 日常兜底模型 fallback | **主模型失败**（超时/502/欠费）时换谁 | 兜底 |
| 3 | 日常默认模型 Base URL | OpenAI 兼容接口地址，如 `https://xxx/v1` | 日常线路 |
| 4 | 日常默认模型 Provider 名称 | 与 Hermes/解析用，如 `nous-api` 或供应商要求的名字 | 路由解析 |
| 5 | 日常默认模型 API Key | **粘贴 Key，屏幕不回显**；可回车先跳过再手改 | 写入 `PHOENIX_DAILY_API_KEY` |
| 6 | 兜底模型 Base URL | 可与日常相同；本地 Ollama 可填 `http://localhost:11434/v1` | 兜底线路 |
| 7 | 兜底模型 Provider 名称 | 通常可与日常相同或按供应商填写 | 兜底解析 |
| 8 | 兜底模型 API Key | 不回显；可回车 **复用日常 Key** | `PHOENIX_FALLBACK_API_KEY` 或复用 daily |
| 9 | 深度模型名（`/深度`） | 如 Claude Sonnet 等在控制台里的名字 | 高档 deep |
| 10 | 大神模型名（`/大神`） | 如 Opus 等 | 高档 god |
| 11 | 真神第二模型名（`/真神` 预留） | 如某 GPT 型号 | super_god 第二条 |
| 12 | 高档模型 Base URL | 常与日常同一个聚合网关；也可分开 | premium |
| 13 | 高档模型 API Key | 不回显；可回车复用日常 | `PHOENIX_PREMIUM_API_KEY` |

**记不住也没关系**：默认值写在提示 `[xxx]` 里，**先能跑起来**，再按控制台文档微调模型 ID。

---

## 5. Key 存在哪里？装完后怎么改？

| 文件 | 作用 |
|------|------|
| **`~/.hermes/.env`** | 存放 `PHOENIX_DAILY_API_KEY`、`PHOENIX_FALLBACK_API_KEY`、`PHOENIX_PREMIUM_API_KEY` 等（安装脚本写入，**勿发到群里**） |
| **`~/.hermes/phoenix/config.json`** | `phoenix_open`：各档位绑定的 **模型名、provider、URL、api_key_env 变量名** |
| **`~/.hermes/config.yaml`** | Hermes 全局 + `phoenix.router.*` 等 |

**改 Key**：用编辑器打开 **`~/.hermes/.env`** 替换对应变量值 → **`hermes gateway restart`**。  
**改模型名 / URL**：优先改 **`phoenix/config.json`** 里 `phoenix_open`，或 **重新跑一次 `install.sh`**（会先备份）。

**Hermes 顶层默认模型**：若要与「日常模型」完全一致，可在 **`~/.Hermes/config.yaml`** 里核对 **`model.default`**（部分环境需手动对齐，见交付文档）。

---

## 6. 装完后怎么验收？

脚本结束前会跑 doctor；你们仍可让客户自查：

```bash
hermes gateway status
```

**若用 Hermes TUI（终端里的 🔥 Phoenix / Ink 界面）测手动挡**：请先 **`hermes gateway restart`**（或退出 TUI 后重进），确保网关加载的是 **已含 TUI 桥接补丁** 的 `tui_gateway/server.py`；否则可能仍出现 **`Unknown command: /深度`**。补丁说明与合并位置见 **`HERMES_TUI_与不死鸟斜杠指令.md`**（与 zip 同发）。

对话里测四条（任意通道：TUI / Telegram 等）：

```text
你好
深度学习是什么？
/深度 帮我简单看下这个项目
/大神 帮我列个提纲
```

期望：**第 2 条不要弹高档确认**；**第 3、4 条应出现确认/降级/取消**（视通道展示形式而定）。

---

## 7. 常见问题（交付话术）

**Q：为什么没有浏览器安装页面？**  
A：当前版是 **终端向导**；网页向导要单独产品化开发。

**Q：Key 会不会打在聊天记录里？**  
A：**不应在聊天里配置**。只在 **安装终端** 或 **本机 .env** 里配置。

**Q：配置里是不是只能写 `"deep": "claude-sonnet"` 这种？**  
A：**不是。** 学员版权威结构在 **`~/.hermes/phoenix/config.json`** 的 **`phoenix_open.model_tiers` + `phoenix_open.providers`**：每档有 **model / provider / base_url / api_key_env**，fallback、emergency 为嵌套对象；**明文 Key 只应出现在本机 `.env`**，变量名写在配置里（安装器默认 **`PHOENIX_DAILY_API_KEY`**、**`PHOENIX_FALLBACK_API_KEY`**、**`PHOENIX_PREMIUM_API_KEY`**；若你坚持 **`ANTHROPIC_API_KEY`** / **`OPENAI_API_KEY`**，可在 `providers` 里把 **`api_key_env`** 改成对应名字并自己在 `.env` 里提供，**不要**写进公开文档或安装包）。

**Q：我只用一个 GPT‑5.5，多档还有意义吗？**  
A：**有意义，但是「降级版」意义。** 可把 **日常 / 兜底 / 高档** 都指向 **同一 Base URL + 同一模型名**，Key 也可复用；此时 `/深度` 仍会走 **确认框与路由链**（成本与流程上的「手动挡」），但 **不会在能力上切换成另一个厂商模型**。要让「切换」真正体现差异，学员需为 **高档**（或各档）配置 **不同的 model / provider / URL / Key**。

**Q：装完 `hermes` 打不开？**  
A：先 `which hermes`、`hermes --help`。若变成不死鸟 CLI，说明环境被旧教程改坏，按安装脚本出口提示修 PATH/别名。

**Q：在 TUI 里打 `/深度` 显示 `Unknown command`，是不是没装好？**  
A：**多半是 Hermes TUI 层未合入桥接补丁**：TUI 会把 `/` 当系统命令，未补丁时到不了 Phoenix。处理：**合并 `tui_gateway/server.py` 中不死鸟三条口令的逻辑**（见 **`HERMES_TUI_与不死鸟斜杠指令.md`**）→ **`hermes gateway restart`** → 再在 TUI 重试。仅重装 Phoenix zip **不能**单独修复这一条。

**Q：我只在 Mac 上测过，Windows 要不要同样搞？**  
A：**只要客户用同一套 Hermes Agent + 同一 TUI 网关**，补丁在同一文件、同一行为；若客户 **不用 TUI**、只用 IM 通道，通常不受此 bug 影响，但为行为一致仍建议 Hermes 树与对内分支对齐。

**Q：Hermes 本体升级会不会「升级死机」？要不要交给 Cursor / Codex 去升？**  
A：**Hermes 升级走官方安装方式**（与你方渠道一致）；AI 助手只能 **辅助排查日志、对照文档**，不能代替你在机器上的 **备份与回滚**。风险与任何大版本软件相同：**升级前先备份整个 `~/.hermes`**（或至少 `config.yaml` + `.env` + `phoenix`）。升级 Hermes **之后**建议顺序：**`auto_fusion.py --report` →（必要时）`--apply` → `doctor.py --fix` → `doctor.py --verify` → `hermes gateway restart`**。若 Hermes 版本 **没有** `hooks` 子命令，`post_upgrade` 不会自动跑，需 **手动执行一次融合脚本**（见 `HERMES_融合与随版本升级.md`）。

**Q：我们自己要不要先在主力 Hermes 上融合验收？**  
A：**建议先在非生产或单人开发机**跑通同一套：`install.sh` → doctor → 对话验收 → 再升级 Hermes 试一轮融合 + Gateway，最后再给全员/客户推 zip。

---

## 8. 安装脚本自动化链路（一直到 Gateway 重启）

下列与 **`install.sh` [1/7]～[7/7]** 对齐，便于你对客户讲「全自动到哪一步」：

```text
确认开始 (y)
    → [1/7] 备份 config.yaml、.env、旧 phoenix/ → ~/.hermes/backups/phoenix_preinstall_*/
    → [2/7] 释放 ~/.hermes/phoenix（rsync 各子目录 + 顶层脚本与文档）
    → [3/7] 双路径同步插件 phoenix_full（bundled + ~/.hermes/plugins/phoenix_full）
    → [4/7] 安装皮肤 ~/.hermes/skins/phoenix.yaml
    → [5/7] 写入 Hermes config.yaml 基础项（皮肤、压缩、检查点、memory、plugins 等）
    → [6/7] 终端交互：模型名 / URL / Provider / Key → 写入 .env + phoenix_open 映射
    → [7/7] Python 语法冒烟 → doctor.py --fix → hermes gateway restart（或 start）→ doctor.py --verify → 复检 hermes 入口未被劫持
```

客户 **不必手写重启网关**：脚本在 **doctor --fix 之后**会 **`restart_gateway`**，再在 **新 Gateway 进程**下跑 **`doctor --verify`**。

---

## 9. 文档索引

| 文档 | 内容 |
|------|------|
| [START_HERE.md](./START_HERE.md) | 最短入口 |
| [INSTALL_GUIDE.md](./INSTALL_GUIDE.md) | 精简步骤 |
| **本文** | **完整安装说明 + 交互问答对照表** |
| [INSTALL_CUSTOMER_一页纸.md](./INSTALL_CUSTOMER_一页纸.md) | 默认/兜底/高档三层 |
| [INSTALL_装前装后对比_Hermes与不死鸟.md](./INSTALL_装前装后对比_Hermes与不死鸟.md) | **装前/装后对照表**、密钥当时/事后、做图分镜 |
| [PHOENIX_V8_CORE_DELIVERY.md](./PHOENIX_V8_CORE_DELIVERY.md) | 交付口径 |
| [RELEASE_交付流程与验收.md](./RELEASE_交付流程与验收.md) | 发布清单、手工矩阵、`sim_verify_v8.py` |
| [HERMES_融合与随版本升级.md](./HERMES_融合与随版本升级.md) | Hermes 升级后融合、`auto_fusion`、hooks |

---

*Phoenix V8 · 与 `install.sh` / `install.ps1` 行为对齐 · 修订请随版本更新*
