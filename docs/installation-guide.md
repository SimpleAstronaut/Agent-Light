# Agent Light 0.2.1 安装手册

发布渠道：[v0.2.1-preview.1 预览版](https://github.com/SimpleAstronaut/Agent-Light/releases/tag/v0.2.1-preview.1)。

## 系统与下载选择

- 目标系统：Windows 11 x64。
- GUI 和命令行版已包含 Python/Qt 运行时，无需单独安装 Python 或 PySide6。
- 使用灯板需要 USB 数据连接；使用 DSH 接入需要自行安装兼容的 DSH 及其 Node 环境。此包不包含 DSH、Node 或新固件。

| 下载文件 | 用途 |
|---|---|
| `AgentLight-0.2.1-windows-x64-setup.exe` | 常规每用户安装 |
| `AgentLight-0.2.1-windows-x64.zip` | 便携运行，完整解压后使用 |
| `agent_light-0.2.1-py3-none-any.whl` | Python 源码用户使用；普通桌面用户不必下载 |
| `agent-light-dsh-0.1.3-desktop.tgz` | 单独分发的 DSH 插件；桌面程序已包含该插件 |
| `AgentLight-0.2.1-SHA256SUMS.txt` | 安装包、便携包、可选分发和手册的 SHA256 校验值 |

本预览版安装程序尚未做代码签名。若 Windows 显示未知发布者，请核对 GitHub 仓库、下载文件名和 SHA256 后自行判断是否运行。

PowerShell 校验示例：

```powershell
Get-FileHash -LiteralPath .\AgentLight-0.2.1-windows-x64-setup.exe -Algorithm SHA256
```

## 安装版

1. 正常退出旧 Agent Light：从托盘选择“退出 Agent Light”。旧 CLI 服务需在原终端按 `Ctrl+C` 退出。
2. 退出所有加载此插件的 DSH Web 后端。仅关闭网页标签不会停止后端。
3. 运行安装程序，阅读说明及许可。
4. 在安装向导确认 Agent Light 和有关 DSH 后端已退出。安装器不会替你结束进程。
5. 选择安装目录。默认是 `%LOCALAPPDATA%\Programs\AgentLight`，按当前用户安装，无需管理员权限。
6. 完成后从开始菜单打开 Agent Light，等待“服务在线”。
7. 按[使用手册](user-manual.md)连接灯板，再通过“Agent 接入 → DSH”检测和配置接入。

安装程序不会自动修改 DSH 启动脚本。需要在应用内预览差异并确认后才安装接入。

## 便携版

1. 将 zip 完整解压到准备长期保留的目录。
2. 打开 `AgentLight` 文件夹，运行 `AgentLight.exe`。
3. 保留同目录的 `agent-light.exe`、`_internal`、`resources` 和许可证文件；不能只移动一个 exe。
4. 设置 DSH 接入或开机启动后不要随意移动目录；移动后需重新核对启动项和插件接入路径。

## 数据与旧版本迁移

程序文件和用户数据分开。默认数据目录为 `%LOCALAPPDATA%\AgentLight`，包括配置、token、SQLite 状态、outbox、接入记录及备份。已有配置和身份不会因安装新版本而重置。

已运行旧 CLI 服务时，先退出它再打开桌面版。DSH 插件使用相同 outbox 和配置时，可保留 producer 身份；不要通过删除 outbox 或 token 来迁移。

需要自定义配置时，可以运行：

```powershell
$agentLightInstall = Join-Path $env:LOCALAPPDATA 'Programs\AgentLight'
& "$agentLightInstall\AgentLight.exe" --config "C:\My Agent Light\config.json"
```

同一 Windows 用户只运行一个桌面实例，切换配置前先完整退出原实例。

## 升级与卸载

升级前正常退出 Agent Light 及加载其插件的 DSH，再运行新安装包。便携版也需在退出后整体更新，避免新旧插件文件混用。

安装版从 Windows“设置 → 应用 → 安装的应用”找到 Agent Light 并卸载。卸载维护入口会检查已登记、引用本安装目录的 DSH 启动器，并要求逐项预览和确认解除接入；取消或记录异常会中止卸载。手工创建的未登记 overlay 也需要自行解除。

卸载会保留配置、token、数据库、outbox、overlay 和备份。便携版删除目录前，应先解除其 DSH 接入和开机启动项。

## 预览版验收范围

发布前已通过 PC 35 项回归、DSH 插件 7 项回归及独立目录冻结包验证。真实灯板、实际 DSH 迁移链路、Windows 登录自启、交互安装/升级/卸载和第二台机器的验收尚未全部完成，因此作为 Pre-release 发布。

DSH 是当前已实现的事件适配；Codex、ZCode、WorkBuddy 页面仍标为待适配，Codex 仅保留只读环境检测。此包不声称新增这些 Agent 的真实上报能力。
