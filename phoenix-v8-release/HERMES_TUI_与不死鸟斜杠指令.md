# Hermes TUI 与不死鸟「/深度 /大神 /真神」— 必知补丁说明

## 为什么要单独一份文档？

不死鸟在 **`AIAgent.run_conversation`** 里识别 **`/深度 …`** 等**普通用户消息**。  
但 **Hermes TUI（Ink）** 会先把 **`/…`** 交给 **`slash.exec`** 当**内置命令**解析；若命令表里没有「深度」，就会出现 **`Unknown command: /深度`**，**消息永远进不了对话**，Phoenix 再正确也接不到。

因此：**仅安装 Phoenix zip 不够**——在「使用官方 Hermes + TUI」的场景下，需要在 **Hermes 源码树**里为这三条口令加 **一层桥接**（本交付在 `tui_gateway/server.py` 已实现）。

## 改了什么（便于合并 / 代码审）

| 位置 | 行为 |
|------|------|
| `tui_gateway/server.py` 常量 | `_PHOENIX_MANUAL_TUI_SLASHES = {"深度", "大神", "真神"}` |
| `slash.exec` | 命中上述 base 时 **返回错误**，迫使 TUI **fallback 到 `command.dispatch`** |
| `command.dispatch` | 命中时 **`type: send`**，把 **`/深度 …`** 整行 **重新当作用户消息** 发给会话 |

**插件** `plugins/phoenix_full/__init__.py` 另注册了 **`/深度` `/大神` `/真神`** 三个 **插件 slash**，供 **经典 CLI** 用 **`inject_message`** 注入队列（与 TUI 路径互补）。

## 与平台的关系

- **macOS**：你当前验证环境；改的是 **Python 网关**，与芯片无关。  
- **Windows / Linux**：若使用 **同一套 Hermes Agent 仓库 + 同一 TUI 网关**，**同一补丁**适用；若客户只用 Telegram/飞书等 **不经 TUI slash 层** 的通道，可不受本条影响，但仍建议仓库一致以免行为分叉。

## 客户 / 二次安装时怎么做？

1. Phoenix：照常 **`install.sh`**（同步 `phoenix_full`）。  
2. Hermes：若 **未** 合并上述 `server.py` 补丁，TUI 里仍可能 **`Unknown command`**。  
   - **选项 A**：使用本组织维护的 **已打补丁的 `hermes-agent` 分支**（推荐对内统一）。  
   - **选项 B**：将 `tui_gateway/server.py` 的改动 **cherry-pick / 手工合并** 到客户当前 Hermes 版本后 **`hermes gateway restart`**。  
3. 验收：见 **`INSTALL_安装说明_完整版.md`** §6（含 TUI）。

## 上游建议

长期应把「插件注册的、或配置声明的手动路由前缀」在 **TUI slash 层** 统一 **降级为 `send`**，避免每个产品各打一遍补丁。在此之前，本文档即为 **交付完整性** 的一部分。
