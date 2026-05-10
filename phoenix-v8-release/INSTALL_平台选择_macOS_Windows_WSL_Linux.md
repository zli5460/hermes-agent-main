# 安装不死鸟：苹果 / Windows / WSL / Linux 怎么选？（给非技术同学）

你不需要把四种叫法都背下来，只要**认电脑界面** + **用对一条安装命令**。

---

## 1. 先搞清：没有「第四套宇宙系统」

大家常说的几件事，其实可以压成 **三类安装方式**：

| 你实际在用什么 | 一句话 | 不死鸟用哪个安装脚本 |
|----------------|--------|----------------------|
| **苹果 Mac**（菜单栏苹果图标） | 原生 Unix，和 Linux 很像 | **`bash install.sh`** |
| **Windows 电脑**（窗口按钮在右下角那种） | 微软桌面系统 | **`install.ps1`**（PowerShell） |
| **在 Windows 里开了一个「Linux 小黑窗」**（Ubuntu 等） | 这叫 **WSL**，本质是 **Linux 跑在 Windows 里面** | **`bash install.sh`**（跟 Mac/Linux 一样） |
| **服务器 / 裸机 Linux**（云主机、Ubuntu 桌面） | 就是 Linux | **`bash install.sh`** |

你说的 **「LU」之类**：行业里多半就是指 **Linux（林尼克斯）**，不是「另一个神秘 OS」。和 Mac 一样都用 **`install.sh`**。

---

## 2. WSL 是啥？为什么要单独提？

**WSL（Windows Subsystem for Linux）** = 在 **不重装电脑** 的前提下，让 Windows 里能跑 **Linux 终端**。

- **右键「在终端打开」**若路径以 **`/mnt/c/`** 开头（Windows 盘映射进 Linux），多半是 **WSL**。  
- Phoenix 的安装脚本 **`install.sh`** 就是在 **这种 Linux 环境**里跑的。  
- **要先装好 Hermes（Linux/WSL 版）**，再在同一个终端里 `bash install.sh`。

**常见晕点**：同一个人桌上既有「Windows 的 PowerShell」，又有「WSL 的 Ubuntu」——**装不死鸟时，用你打算日常跑 `hermes` 的那一种终端**，别混着配一半。

---

## 3. 交付给混合环境客户时，怎么说最省事？

可以照读下面三句：

1. **纯 Mac 用户**：打开「终端 Terminal」→ 进解压目录 → `bash install.sh`。  
2. **纯 Windows 用户（不玩 Linux）**：右键用 **PowerShell** 打开发布包目录 → 按 `INSTALL_GUIDE` 跑 **`install.ps1`**。  
3. **Windows 但平时用 WSL 开发**：打开 **WSL（Ubuntu 等）** → 用 **Linux 路径**进解压目录（若 zip 在 C 盘，WSL 里一般是 `/mnt/c/...`）→ `bash install.sh`。

---

## 4. 兼容性原则（产品侧记一句就够）

- **同一套 Phoenix 包**：**`install.sh` 管 Mac + Linux + WSL**；**`install.ps1` 管原生 Windows**。  
- ** Hermes 本体**必须客户自己先按 **各自平台**装好；不死鸟是 **插件**，不替 Nous 发安装包。  
- **网关**：装完都会走 `hermes gateway restart`；**哪套终端装的，就在那套环境里 `hermes gateway status`** 看状态。

---

## 5. 和《一页纸》的关系

**先读本文件选平台** → 再跟 **[INSTALL_CUSTOMER_一页纸.md](./INSTALL_CUSTOMER_一页纸.md)** 里「一条命令装到底」。

---

*若客户环境是「公司只给云 Linux 服务器」：同样用 `install.sh`，注意用 `ssh` 登录后的那台机子就是 Linux，没有 WSL 这一说。*
