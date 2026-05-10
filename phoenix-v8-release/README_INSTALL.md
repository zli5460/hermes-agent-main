# Phoenix 一键安装说明

## macOS / Linux

```bash
unzip phoenix-v8-release.zip
cd phoenix-v8-release
bash install.sh
```

## Windows

```powershell
Expand-Archive phoenix-v8-release.zip
cd phoenix-v8-release
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

安装器会引导用户填写自己的默认模型 primary、兜底模型 fallback、API Key、Base URL，并自动同步插件、写入配置、安装皮肤、开启记忆/压缩/检查点、运行 Doctor 自动修复、重启 Gateway、复测。

安全说明：发布包不包含 .env、auth、session、memory runtime、logs、cache、backups，也不包含开发者 API Key。


## Phoenix V8 路由启动
普通聊天直接发；高档只认 `/深度`、`/大神`、`/真神`，确认后执行，失败自动 fallback/emergency。
