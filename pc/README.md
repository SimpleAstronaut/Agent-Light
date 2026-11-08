# Agent Light 上位机 v0.2.1

Python 本地服务负责 HTTP 鉴权、SQLite 持久化状态与幂等、跨来源聚合、USB v1 单串口管理。配置默认亮度 35%、完成保持 300 秒、端口 17321。DSH 插件见 `../plugins/dsh/README.md`。

项目总览与完整使用手册见 [根目录 README](../README.md)。2026-11-06 已完成真实 DSH 对话的运行黄灯、完成绿灯联调；完整验收范围见根文档与现场记录。

在项目根目录 PowerShell 执行：

```powershell
py -3.14 -m venv pc/.venv
pc/.venv/Scripts/python -m pip install -e ./pc
pc/.venv/Scripts/agent-light init
pc/.venv/Scripts/agent-light serve
```

另一个终端：

```powershell
pc/.venv/Scripts/agent-light health
pc/.venv/Scripts/agent-light status
pc/.venv/Scripts/agent-light test
pc/.venv/Scripts/agent-light clear
```

`init` 输出真实配置绝对路径。Windows 使用当前用户 LocalAppData/AgentLight，收紧目录 ACL；不要在重写用户目录的 dsh.cmd 内执行初始化。`--config <绝对路径>` 可使用独立配置。不要输出或复制 token 内容到聊天/日志。

自动发现仅接受配置的 VID/PID；多块匹配设备时必须指定 serialNumber，或明确配置 port。不会打开第一个任意 COM 口。当前原型默认 0483:5740。串口连接失败自动退避重连；只有 ACK 确认后 connected 才为 true。status 中 desired 是业务灯态，acked_revision 是设备确认代次。三色测试每色 ACK 后保持至少 1 秒，随后以 ACK 恢复最新聚合状态；不改变聊天记录。

只监听 IPv4 loopback。全部端点要求 Bearer token，禁止浏览器 Origin 请求；事件默认 2 KiB，batch/屏障上限 64 KiB。CLI `event` 从 stdin 接受规范化事件，上报超时退出 0；它不是 Codex 适配器。诊断命令失败返回非零。

事件入口、终态、等待和来源交接见 `../contracts/event-schema.json` 与 `../contracts/fsm-transitions.md`。真实 Codex 适配器尚未实现；`codex` 仅为预留协议标识。

最小验证：`pc/.venv/Scripts/python -m unittest discover -s pc/tests -v`。不包含实板、性能、断电耐久性验收。本版增加 PySide6 四页 GUI、托盘、当前用户开机启动、设备管理和 DSH 接入；使用方法见 [桌面指南](../docs/desktop-guide.md)。

桌面化已开始实施，进度见 [实施记录](../docs/superpowers/plans/2026-11-08-desktop-ui-progress.md)。后台可通过 `ServiceRuntime(cfg, config_path=...)` 在线程中启动，并用非阻塞 `request_stop()` 请求完整清理；阻塞 `wait_stopped()` 仅用于 CLI/测试，不应在 Qt 主线程调用。

新增 `GET/PATCH /v1/config/display`，沿用 Bearer 鉴权。PATCH 仅接受 `brightness` 和 `completedHoldSeconds`，写入启动时指定的配置文件；成功的 `configuration_saved` / `backend_applied` 只表示配置和后台已更新。运行中检测到配置文件外部修改会拒绝覆盖，需重启加载。`GET /v1/health` 增加 `desktop_api` 和包元数据版本。CLI 的鉴权失败返回 4，HTTP 错误保留业务错误码，网络连接失败返回 `SERVICE_UNAVAILABLE`。
