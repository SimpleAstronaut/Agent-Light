# Agent Light 桌面版 0.2.1

按界面逐步操作的说明见[完整使用手册](user-manual.md)，包含首次启动、本机 DSH 路径、设备连接、日常使用和排障。本文件保留桌面架构与构建速查。

## 安装与启动

Windows 11 x64 发布包采用 onedir，GUI 为 `AgentLight.exe`，CLI 为同目录 `agent-light.exe`。整个目录必须一起保留；外部 DSH 插件位于稳定的 `resources/plugins/dsh` 路径。安装器默认安装至当前用户的 `%LOCALAPPDATA%/Programs/AgentLight`，不需要管理员权限。

源码运行：

```powershell
pc/.venv/Scripts/python.exe -m pip install -e "./pc[desktop]"
pc/.venv/Scripts/agent-light-desktop.exe
# 独立配置
pc/.venv/Scripts/agent-light-desktop.exe --config "C:/Example/Agent Light/config.json"
```

首次启动创建配置；已有配置、token、数据库和 outbox 不会被重置。默认数据目录为 `%LOCALAPPDATA%/AgentLight`。同一用户只允许一个桌面实例，第二次启动激活现有窗口；不同 `--config` 会提示冲突，需要先从托盘退出原实例。已运行 CLI 服务会阻止桌面重复启动，桌面不会自动接管或结束它。

## 四个页面

- **状态**：服务、DSH 上报、灯板确认、业务灯态分别显示。未收到本进程心跳不显示上报正常；一次刷新失败即撤销旧确认快照。
- **设备**：扫描不会试开串口。可自动发现或手动选择；多设备需选择端口/序列号。保存并连接只表示接受意图，设备确认需等待 SET ACK 后的匹配 STATUS。断开会禁止自动重连。
- **Agent 接入**：从二级导航选择 DSH，再选择 DSH `lib/bin.js`、该宿主使用的 Node 和 `dsh-web.ps1`。只读检测版本及固定文件指纹，不读取聊天。生成只写草稿；安装前显示精确 diff，并要求确认 DSH 已退出。安装后重启 DSH 才生效。
- **设置**：亮度 20–100，完成保持非负秒数，0 表示不保持。保存后反馈配置及后台提交，设备确认仍单独显示。完成保持只影响新完成事件。安装版支持当前用户开机启动，源码运行禁用此项。

三色测试依次红、黄、绿，每色从真实 ACK 后保持至少一秒，再以新的 ACK 恢复当时最新业务灯态。测试不改写会话；测试期间不能保存显示配置，但断开/切换设备/退出仍可执行并终止测试。成功表示 USB 命令已获设备确认，不表示光学检测。

## 托盘与退出

启用“关闭窗口时保持后台运行”后，关闭窗口只隐藏；托盘可打开主界面、测试、进入设置或完整退出。无托盘时窗口保持可见。`--minimized` 用于安装版开机启动；无托盘会回退到窗口。

完整退出会等待在途串口调用、扫描和已接受配置写入结束，再释放数据库及锁。超过目标时长会显示清理中，不强杀线程或 DSH。Qt 主线程不阻塞等待后台。

## DSH 接入、迁移与卸载

只支持已登记模板的 launcher；已知无标记旧集成会迁移为一对 `BEGIN/END AGENT-LIGHT MANAGED v1` 管理块。未知脚本只给手工方案，不会被重写。写入前再次核对文件 hash，保留原编码、换行和权限并创建备份。外部修改管理块后须手工核对，程序拒绝猜测覆盖。

默认 overlay 和记录位于 `%LOCALAPPDATA%/AgentLight/integrations`；自定义配置按规范化完整配置路径的 SHA256 分目录，a.json 与 b.json 完全隔离。全局配置索引记录自定义配置的安装记录位置，不保存 token。草稿在各自 `drafts` 目录，不覆盖正在被 launcher 引用的正式 overlay。

卸载接入后要退出/重启 DSH。旧来源若已停止并租约过期，可在状态页确认停用，保留历史并排除其旧灯态贡献。重新启用进入恢复状态，需要新 runtime 屏障及健康心跳；不删除 outbox 或身份来制造恢复。

升级前退出 Agent Light 及加载插件的全部 DSH。安装器不自动停止进程。卸载程序会运行维护入口 `AgentLight.exe --prepare-uninstall`，逐项解除本安装目录已登记的 launcher 引用；取消、文件被修改或状态不明会中止卸载。手工创建的未登记 overlay 由用户自行解除。配置、token、数据库、outbox、overlay 和备份均保留。

## CLI 与排障

原有 `init/serve/status/health/clear/test/event/overlay` 保留。安装版 CLI 的默认 overlay 指向同目录稳定插件资源。test 无就绪设备或已运行时退出 3；鉴权失败退出 4；连接失败退出 1 并返回 `SERVICE_UNAVAILABLE`，其他 HTTP 错误不会误报离线。event 保持静默。

| 错误 | 处理 |
|---|---|
| SERVICE_ALREADY_RUNNING / ENDPOINT_IN_USE | 正常退出原服务或选择其他 loopback 端口；不删除活动锁 |
| DEVICE_NOT_UNIQUE | 选择端口或填写唯一序列号 |
| DEVICE_NOT_READY | 等待 SET ACK 与 STATUS 同步，再开始测试 |
| CONFIG_CHANGED_EXTERNALLY | 重启服务加载外部修改，不覆盖旧文件 |
| HOST_NOT_FOUND / NODE_RUNTIME_MISSING | 手工选择宿主入口和对应 Node |
| UNSUPPORTED_VERSION | 使用匹配的宿主版本；不能绕过文件指纹 |
| INSTALLER_CONCURRENT_CHANGE | 重新检测和预览差异 |
| INSTALLER_ROLLBACK_REQUIRED | 按安装记录和备份核对文件，完成前不要删除程序目录 |
| PRODUCER_STILL_REPORTING | 退出来源采集器并等待租约过期 |

二级导航提供 DSH、Codex、ZCode、WorkBuddy。DSH 已支持；Codex 保留独立的只读环境检测，ZCode、WorkBuddy 显示待适配且禁用未实现操作。选择只切换页面，保留 DSH 输入和检测结果，不停止或切换实际来源。

## 构建与验证

`packaging/windows/runtime-lock.json` 记录实际依赖版本、hash 和验证范围。安装 `packaging/windows/requirements-desktop.lock` 的 hash 锁定依赖（pip `--require-hashes`），并通过 `-ISCC` 指定 Inno Setup 6.7.4 编译器后，使用 `packaging/windows/build.ps1` 构建，插件先从锁定 TypeScript 重新编译，再打包和校验完整资源。Windows ICU 使用系统 API，避免把其他工具的 ICU 库混入冻结包。

自动化验证采用 fake 串口、临时数据库、合成 token/outbox、Qt offscreen/QTest 和独立中文空格目录的冻结包运行。真实灯板、真实聊天事件、Windows 登录与第二台机器的验收结果须以实施记录为准，不能由自动化结果推断。
