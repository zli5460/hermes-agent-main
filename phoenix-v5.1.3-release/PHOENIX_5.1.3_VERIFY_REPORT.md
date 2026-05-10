# Phoenix V5.1.3 Manual Release 验证报告
## 结论
- 自动化检查项：18
- PASS：18
- FAIL：0
- WARN：0
- 自评分：9.2/10

## 检查明细
- ✅ 重新打包: ~/.hermes/work/phoenix_v513_package_build/phoenix-v5.1.3-release.zip
- ✅ zip解包: 170 entries
- ✅ 包内容完整性: 核心/插件/文档/doctor/双平台安装器齐全
- ✅ 路径级硬违规扫描: 0 个运行时/缓存/备份/凭证文件
- ✅ 个人信息/本机路径内容扫描: 0 命中
- ✅ 真实Key/Token扫描: 0 命中
- ✅ Python语法扫描: 114 个 .py AST通过
- ✅ install.sh bash -n: PASS
- ✅ install.ps1静态标记: 有交互/doctor fix/verify/显式路径参数
- ✅ install.ps1 PowerShell解析: PASS
- ✅ install.sh一键安装静态链: 备份/写配置/doctor/fix/verify/Gateway restart/start/权限/模式齐全
- ✅ 配置手动挡/兜底审计: /深度 /大神 /真神 精确口令 + fallback/emergency + 无daily/medium自动执行
- ✅ 插件真切换/确认链静态审计: 无假切换/无串Key/三口令/确认降级取消/真switch_model
- ✅ 虚拟触发词/确认流程模拟: 精确前缀触发；普通聊天不触发；确认/降级/取消状态机通过
- ✅ ProviderResolver虚拟解析: 五档解析无异常，含chat_completions，不暴露Key
- ✅ Doctor隔离环境fix/verify: 临时HOME=phoenix513_install_sim_aqd555i0，fix+verify rc=0
- ✅ 重新打包: ~/.hermes/work/phoenix_v513_package_build/phoenix-v5.1.3-release.zip
- ✅ 校验清单: ~/.hermes/work/phoenix_v513_package_build/CHECKSUMS.txt

## 已覆盖
- 包内容完整性、敏感信息、真实Key/Token、Python语法、install.sh、install.ps1静态链。
- `/深度`、`/大神`、`/真神` 精确触发模拟；确认/降级/取消状态机模拟。
- ProviderResolver、fallback/emergency、doctor --fix/--verify 隔离环境拨测。

## 剩余风险
- 当前是虚拟/静态/隔离拨测，不等同真实 Telegram/TUI/Gateway 人工收发全链路。
- macOS 本机如无 pwsh，只能静态审计 install.ps1，不能宣称 PowerShell 实机通过。
- 真实模型调用未执行，避免消耗学员或生产 Key；最终发版前建议在一台干净机用测试 Key 跑一次。
