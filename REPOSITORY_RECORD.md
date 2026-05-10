# Phoenix V8 仓库记录

项目名称：不死鸟 Phoenix V8 初心回归版

项目定位：
Hermes Agent 插件 + 配置层，为 Hermes 增加手动档位切换、多模型兜底、预算控制、记忆系统能力。

GitHub 仓库地址：
https://github.com/zli5460/hermes-agent-X-Phoenix-Architecture

Phoenix 发行目录（克隆后）：
`phoenix-v8-release/`

Hermes 基线（本仓库 `pyproject.toml`）：
**hermes-agent 0.13.0**（上游 NousResearch）

当前主分支：
main

查看远程仓库命令：
git remote -v

查看提交记录命令：
git log --oneline --decorate --graph --all -10

查看最后一次上传内容：
git show --stat HEAD

查看本地是否和仓库同步：
git status
git branch -vv

备注：
Phoenix 本身是私有交付项目，不依赖公开 GitHub 仓库地址。
Hermes Agent 底层框架来自 NousResearch，Phoenix 是在 Hermes 之上的插件层。
Phoenix 变更见 `phoenix-v8-release/CHANGELOG.md` 与 `phoenix-v8-release/VERSION.md`。

交付前静态验收（本仓库已包含）：

```bash
cd phoenix-v8-release
pip install pyyaml   # 若尚未安装
python3 sim_verify_v8.py --no-zip
# 打发布 zip + CHECKSUMS：python3 sim_verify_v8.py
```

本地一键安装（Ollama 日常 + DeepSeek 高档）：

```bash
cd phoenix-v8-release
export HERMES_AGENT_DIR=/你的/hermes-agent源码目录   # 可选，默认识别常见路径
bash install.sh --profile=local-deepseek -y
```
