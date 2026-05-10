# Phoenix V5.1.3 — 交付流程、验收顺序、要不要重装 Hermes

给内部：**这一次主线是手动挡路由**（`/深度` `/大神` `/真神`），安装包与脚本已在仓库；交付前按本文跑一遍，减少外发翻车。

---

## 1. 你现在该「敲代码」还是「打包交付」？

| 状态 | 说明 |
|------|------|
| **核心逻辑 / install / doctor / 插件** | 已在 **`phoenix_v513_manual_release/`** 内；发布前跑 **`python3 sim_verify_v513.py`** 生成 zip + `CHECKSUMS.txt`。 |
| **本次补齐** | **流程文档**（本文）+ **装后自检脚本**（`scripts/post_install_smoke.sh`）+ **多环境手工验收表**（见下）。 |
| **若要改产品逻辑** | 另立需求（例如 Web 安装向导、自动同步 `model.default`）；不在「交付_closure」里静默改路由行为。 |

---

## 2. 推荐安装顺序（给客户 / 你自己试机）

**永远：先 Hermes，后 Phoenix。**

```text
1) 安装 Hermes Agent（官方方式）→ 终端里 hermes --help 正常
2) 解压 Phoenix 发布 zip
3) bash install.sh（Mac/Linux/WSL）或 install.ps1（Windows）
4) 装完后：可选跑 scripts/post_install_smoke.sh（见第五节）
5) TUI/Telegram 等测四条验收话术（INSTALL_安装说明_完整版.md）
```

---

## 3. 要不要删了 Hermes 重装？

**不是必须。** 只在下面情况考虑「干净重装」：

- 多次版本混搭、`hermes` 被旧教程劫持、doctor 长期红  
- 你愿意 **先备份** 再重来

**推荐做法（你自己试新机效果）**：

1. **备份**：把整个 **`~/.hermes`** 拷到桌面或 `~/hermes_backup_日期`。  
2. （可选）按 Nous 文档 **卸载 Hermes CLI / pipx**，再 **重装 Hermes**。  
3. 确认 **`hermes --help`** 正常。  
4. **解压本次 zip**，重新 **`bash install.sh`**，按终端交互填 Key。

**不要**：没备份就删目录。

---

## 4. 多环境测试矩阵（手工 —— 脚本无法替你模拟三台真机）

在发布说明里勾选：

| 环境 | 命令 | 必测项 |
|------|------|--------|
| **macOS** | `bash install.sh` | hermes 入口复检绿；gateway；doctor verify；四条话术 |
| **Windows 原生** | `install.ps1` | 同上（路径换 PowerShell） |
| **WSL2 Ubuntu** | `bash install.sh` | zip 放在 `/mnt/c/...` 或家目录；同上 |

**自动化部分**：本机可重复跑 **`sim_verify_v513.py`**（静态 + 隔离 doctor）；**不等于**三家 OS 真机测完。

---

## 5. 装完自检脚本（可选）

发布包内：**`scripts/post_install_smoke.sh`**

用途：**安装脚本跑完之后**，在同一终端执行，快速检查：

- `hermes` 是否存在  
- `hermes gateway status`（若失败仅提示）  
- `doctor.py --verify`  

**用法**：

```bash
chmod +x scripts/post_install_smoke.sh
./scripts/post_install_smoke.sh
```

若 Hermes 源码目录不在默认路径，可先导出：

```bash
export HERMES_AGENT_DIR=/你的/hermes-agent路径
./scripts/post_install_smoke.sh
```

---

## 6. 发布物清单（交付同事核对）

- `phoenix-v5.1.3-release.zip`（由 `sim_verify_v513.py` 产出）  
- 同目录 **`CHECKSUMS.txt`**  
- 文档：**`INSTALL_安装说明_完整版.md`**、**`RELEASE_交付流程与验收.md`**（本文）

---

## 7. 一句话给老板

**代码与包已在树里；交付_closure = 验证脚本绿 + zip + CHECKSUMS + 按矩阵手工冒烟；你自己想「从零试一遍」= 备份 →（可选）重装 Hermes → 再跑 Phoenix install，不必先删 Hermes 除非要干净环境。**
