# 不死鸟与 Hermes：融合架构 & 随上游升级

**定位**：Phoenix **建在 Hermes 之上**，通过插件、`switch_model`、配置扩展来接管路由；**不替换 Hermes 本体**，也不抢占 **`hermes` 命令**（安装脚本已强制检查）。

---

## 1. 「自动融合」相关的程序分别是什么？

| 组件 | 路径（安装后在用户机上） | 做什么 |
|------|--------------------------|--------|
| **Post-Upgrade 钩子壳** | `~/.hermes/phoenix/post_upgrade_hook.sh` | Hermes **声明支持 hooks** 且用户执行过注册后，在 **`post_upgrade`** 时机被调用，写入 `fusion.log` 并调用下面的 `auto_fusion.py`。 |
| **自动融合主程序** | `~/.hermes/phoenix/auto_fusion.py` | 扫描当前 Hermes 能力（工具集/插件等），对照 **`feature_registry.json`**，可 `--apply` 做能力对齐与配置侧融合。 |
| **适配器 / 扫描** | `phoenix/adapt/`（`adapter.py`、`compat_report.py`、`scanner.py` 等） | 检测 Hermes 与 Phoenix 版本/结构变化，输出兼容报告，部分情况可 **自动打补丁**（如历史设计里对 `run_agent` 等位的恢复思路）。 |
| **安装时小补丁** | `install.sh` 内 `patch_hermes_cli_verbose_compat` 等 | **一次性、手术式** 兼容老 CLI 签名（如 WSL 下 `verbose` 参数），**不**改变 Hermes 产品方向。 |

**注册钩子（需 Hermes 支持 `hooks` 子命令时）**：

```bash
hermes hooks add post_upgrade ~/.hermes/phoenix/post_upgrade_hook.sh
```

若你方 Hermes 版本**没有** hooks 子命令，则 **post_upgrade 不会自动跑**——可改由 **用户升级 Hermes 后手工执行**：

```bash
python3 ~/.hermes/phoenix/auto_fusion.py --apply
```

---

## 2. 设计理念（和你们对外说的话）

```text
不争 Hermes 原生 CLI / Gateway / 工具注册机制；
只在插件层扩展路由、记忆、自愈、账本；
上游变了 → 先用适配层扫描 → 能自动的自动，不能的就发新版 Phoenix + doctor。
```

**永远对齐**：`switch_model`、`chat_completions` transport、`plugins` 加载路径——这是「融合」的技术锚点。

---

## 3. 「用户说 Hermes 更新了」你们实际操作顺序建议

1. **记下 Hermes 版本号**（`hermes --version` 或官方 Release）。  
2. **备份 `~/.hermes`**。  
3. 升级 Hermes（官方流程）。  
4. **`python3 ~/.hermes/phoenix/auto_fusion.py --report`** 先看报告；再决定是否 **`--apply`**。  
5. **`python3 ~/.hermes/phoenix/doctor.py --fix && python3 ~/.hermes/phoenix/doctor.py --verify`**。  
6. **`hermes gateway restart`**。  
7. 若 Phoenix 侧因 **API 大变** 仍需改版 → **发新不死鸟安装包**，而不是让客户改 Hermes 源码对抗。

---

## 4. 不能过度承诺什么？

| 现实 | 说明 |
|------|------|
| **不能 100% 无人值守** | Hermes 大版本可能改 CLI、插件 API、Gateway；自动融合能处理 **一部分** 扫描得到的问题。 |
| **Hooks 依赖上游** | `post_upgrade` 只有 Hermes 真实现并用户注册才触发。 |
| **「马上融合」** | 指 **流程上** 先跑 `auto_fusion` + `doctor`；若需改 Phoenix 代码，仍要 **发版周期**。 |

---

## 5. 与 V5.1.3 手动挡路由的关系

**路由策略**（手动 `/深度` 等）与 **随 Hermes 升级做融合** 是两条线：

- 前者：产品行为，写进 `phoenix_open` 与插件。  
- 后者：工程维护，靠 `auto_fusion` + `adapt` + 新 zip。

---

*内部交付用 · 对外可简化为：「我们跟 Hermes 同向升级，有自动融合脚本和 doctor；大改会发新安装包。」*
