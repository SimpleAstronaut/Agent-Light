# 桌面上位机实施与验收记录

日期：2026-11-08。规格：`docs/superpowers/specs/2026-11-08-desktop-ui-development-spec.md`。
分支：`codex/desktop-runtime`。WP0–WP6 的代码与分发产物均已实现；自动化及本机只读检测通过，尚需的手工/硬件验收见末节。

## 执行约定

按用户要求，省去审查代理、逐任务审查、重复全量回归及逐项 RED/GREEN。保留关键生命周期、协议、配置/文件事务、Qt/冻结包和性能验证。没有提交、推送、发布或改写真实 DSH launcher，没有修改真实用户配置、token、数据库、outbox、开机启动项或 firmware/USB 合约。

原目录内独立功能分支作为等价工作边界，保留原先未跟踪的设计和可行性审查文档。源自需求的确认界面（来源管理、launcher diff、确认宿主退出、卸载预检）保留在产品中。

## 工作包结果

| 工作包 | 实现与证据 |
|---|---|
| WP0 | 阅读规格/README/USB/PC/DSH 基线；修改前 PC 5/5、插件 7/7；F1/F2 回归、四组脱敏 launcher fixture、精确候选依赖及 hash |
| WP1 | ServiceRuntime 双线程生命周期、部分启动失败清理、独立串口 executor、原子配置与 ACL、取消写入收尾、显示 API、CLI 分类 |
| WP1a | Qt 6.10.3 / PyInstaller 6.16.0 最小双入口 onedir；独立中文空格路径通过 Qt、CLI、schema/元数据、完整资源、inspect-host、fake Worker、缺资源拒绝 |
| WP2 | 扫描、连接/断开、有界控制队列、连接代次和迟到结果隔离、ACK 后匹配 STATUS 确认、逐色 ACK/保持/恢复、source_admin 管理与新 runtime 恢复门禁 |
| WP3 | 四页主窗口、异步 HTTP、有限在途查询、过期快照、250ms 测试轮询、producer 明细/确认管理、设备连接及阶段结果 |
| WP4 | 托盘、关闭驻留、异步退出、无托盘回退、用户级锁/IPC、跨 config 激活冲突、QSettings、安装版用户 Run 项（fake registry 验证） |
| WP5 | 动态 DSH/Node/launcher 发现、严格 verifyHost、共享 overlay、独立草稿、精确模板迁移、diff/备份/确认、并发 hash 校验、pending 记录/恢复、所有权索引、安装/卸载及失败回滚 |
| WP6 | GUI/console onedir、完整插件资源 manifest、每用户 Inno 安装器、运行中升级拒绝、卸载维护入口、许可文件、指南、wheel/插件/便携归档 |

source_admin 是受限管理扩展，未重写原会话归约或优先级；FSM 管理语义已同步增补。CLI 保留原命令，test 仅在灯板当前已确认时接受。设备未就绪/测试重复退出 3，鉴权失败退出 4，网络不可用与 HTTP 业务错误分别报告。

## 自动化与本机证据

- `python -m unittest discover -s pc/tests -v`：32/32，通过且没有 Qt skip。覆盖资源清理、迟到 open、失败/取消配置写入、来源门禁、设备 ACK 测试/恢复、API、CLI、Qt 轮询超时、主线程启动/保存/退出、第二实例 IPC、假注册表、launcher 事务。
- `npm run build` 与 `npm run check`：TypeScript 构建成功，插件 7/7 通过。
- `verify_toolchain.py`：Windows x64 CPython 3.14.0 及锁定依赖/TypeScript 精确版本匹配。
- 冻结 GUI 和 console 在 `.tmp/分发 final` 独立目录运行通过；完整插件 import、fake token/outbox Worker、缺失 worker 负例、schema、元数据和 CLI health/status 均通过。
- 冻结 GUI 内经受控 DLL/PATH 环境调用选定 DSH Node，实际宿主 `dsh-agent/dsh-session 0.2.1-rc.2`、Cordis 4.0.5、Node 22.23.2 及全部指纹通过。只读检测不代表实际 DSH 事件链路已重新联调。
- 四页 Qt 画面已渲染并目视检查；`outputs/desktop-preview.png` 使用临时配置展示真实服务在线、无 producer、无匹配灯板的状态，没有伪造硬件确认。
- Inno Setup 6.7.4 编译成功；编译器来自官方发布链接，Authenticode 为 Valid / Pyrsys B.V.，SHA256 记入 runtime-lock。
- `compileall`、`git diff --check` 通过。

### 性能与故障注入

`pc/tools/desktop_load_probe.py` 使用 16 个合成会话、1000 条积压事件、真实 Qt 轮询、本地 HTTP/SQLite 和 fake 串口：

| 指标 | 实测 |
|---|---|
| HTTP p95 | 4.226 ms（目标 <200ms） |
| HTTP 最大值 | 6.292 ms |
| 服务事件循环最大延迟 | 14.298 ms |
| 正常有效 USB 请求最大间隔 | 1.059 s（目标 <2s） |
| 注入 SQLite 阻塞 | 5.3 s |
| 阻塞期间撤销 UI 旧快照 | 通过 |
| 模拟固件链路丢失后重新 SET/STATUS 确认 | 通过 |

结果保存在 `outputs/desktop-load-results.json`。这是当前本机健康磁盘及模拟串口证据，不替代真实设备请求间隔或任意慢磁盘保证。

## 实施决定与修正

1. 遵照用户要求省去独立审查和繁复测试流程，以关键回归及可执行产物验证控制改动风险；没有独立审查结论。
2. 保留现有 checkout，创建功能分支；不移动用户文件或创建额外 worktree。
3. Qt 使用 Windows ICU。PyInstaller 曾从构建 PATH 误收 Poppler 的不兼容 ICU，导致冻结包缺符号；排除外来 ICU 并先加载 System32 ICU，重跑源码外烟雾验证通过。只承诺规格约定的 Windows 11 x64。
4. 插件检测使用 Qt QThreadPool 中的受管只读子进程，共用串行 DLL 启动临界区、10 秒超时及各 64KiB 输出上限；这是 §3 架构允许的方式，相对于 §8 的 QProcess 建议复用同一 headless/冻结包检测器，CLI 不因检测而强制依赖 Qt。
5. endpoint 预探测超时不认定端口被占用：Windows 对未监听端口的拒绝可能晚于短探测时限。最终以 ProcessLock 和 TCPSite 绑定为准；已有鉴权兼容服务/明确 HTTP 占用仍报告冲突，不附加、不结束进程。
6. 修正 QApplication.quit 被 closeEvent 防护拦截的问题：资源收尾结束后设置 final_close 再关闭窗口、退出事件循环。实际异步生命周期和冻结包退出均复验通过。
7. Qt offscreen 在本机不枚举字体，验证时按需加载系统已有微软雅黑；原生 Windows 继续使用系统字体。四页中文渲染已复查。

## 产物与使用

- `outputs/packages/AgentLight-0.2.0-windows-x64-setup.exe`：每用户安装器。
- `outputs/packages/AgentLight-0.2.0-windows-x64.zip`：完整便携 onedir，解压后运行 AgentLight/AgentLight.exe。
- `pc/dist/AgentLight/AgentLight.exe` 和 `agent-light.exe`：本次构建的 GUI 与 CLI。
- `outputs/packages/agent_light-0.2.0-py3-none-any.whl`：Python 分发。
- `outputs/packages/agent-light-dsh-0.1.3-desktop.tgz`：带只读检测工具的插件归档；原 0.1.3 历史归档保留。
- `packaging/windows/runtime-lock.json`、`requirements-desktop.lock` 和 `build.ps1`：锁定版本/hash 与可重复构建入口。
- `docs/desktop-guide.md`：使用、维护、升级、卸载和兼容说明。

## 尚未完成的实机/手工验收

这些是明确未通过的验收项，不能以代码完成、安装器编译或 fake 测试替代：

- 实板三色、真实 GET_STATUS/保活、托盘驻留后的真实 DSH 对话控灯及退出后固件 LINK_LOST。本次只枚举到没有匹配 VID/PID 的串口，没有打开实物串口。
- 实际将旧 launcher 迁移到安装目录并重启 DSH、退出旧 producer/重新启用新 runtime 的完整链路。已通过真实宿主只读检测和临时 launcher 迁移，不改写真正 launcher。
- 交互式安装、覆盖升级和卸载、Windows 登录启动与运行中托盘失效。对应实现、保护和 fake/Qt 测试已做，但没有实际切换用户登录或执行真实卸载。
- 第二台无源码机器的运行验收。本机独立无源码目录已通过，不等同第二台机器。

runtime-lock 保持 `automated_verified_manual_acceptance_pending` / `verified=false`，未将整个实机矩阵伪报为已验证。代码与本机可自动执行的工作已落地，待以上条件具备后完成最终发布验收。
