# Agent Light PySide6 桌面上位机开发规格

> 日期：2026-11-08  
> 状态：可行性审查后修订，待实施与验证  
> 目标平台：Windows 优先，Python 3.11+，PySide6  
> 文档用途：作为 AI 或开发者直接实施桌面化改造的设计、任务拆分和验收基线。  
> 关联文档：根目录 `README.md`、`contracts/usb-protocol-v1.md`、`contracts/fsm-transitions.md`、`docs/superpowers/specs/2026-11-06-dsh-plugin-design.md`。

---

## 0. 执行约定

实施本规格时必须遵守以下约束：

1. 保留 `DSH / Codex 适配器 → 本地上位机服务 → USB 灯板` 的调用关系。
2. 不修改 `firmware/`，不修改 `contracts/usb-protocol-v1.md`，不改变 USB v1 的命令、状态值、帧格式、ACK 或 revision 规则。
3. 不重写 `core.py` 的会话归约、来源交接、等待集合和聚合优先级。允许的受限改动为 Store 构造失败的资源清理、当前进程心跳辅助数据，以及 §5.7 的显式来源停用/重新启用门禁；必须先补回归测试，原有 enabled 来源行为不变。
4. 保留现有 `agent-light init/serve/status/health/clear/test/event/overlay` 命令、参数与路由。`test` 收紧为设备就绪后才接受；非 event 命令的 HTTP 错误分类与退出码按 §6.10 明确升级，其余 CLI 行为不变。桌面功能是增量，不替代 CLI。
5. UI 不直接打开串口、不直接读写 SQLite、不自行运行状态聚合。
6. “配置已保存”“插件已安装”“插件已加载”“插件正在上报”“灯板已连接”“灯板已确认”必须是不同状态，不得相互推断。
7. Codex 真实适配器尚未实现。首版只能检测环境和展示预留状态，不得宣称已经支持 Codex 接入。
8. 不硬编码 `D:/projects/agent-light`、`D:/deepseek`、COM6 或本机 Node 路径；所有路径必须动态发现或允许用户选择。
9. 不自动结束 DSH、Node、Python 进程，不删除活动锁文件，不上传 token、数据库、outbox、聊天内容或诊断隐私数据。
10. 每完成一个工作包，运行该工作包的定向测试和现有回归测试；没有验证证据时不得标记完成。

首版不实现独立 Windows Service、不实现云端同步、不实现 Codex 真实适配器、不实现自动更新。

### 0.1 本次修订的设计取舍

本次按可行性审查 F1–F8 修订设计，不表示对应代码已修复或实机验收已通过。

- 保留单进程双事件循环，补齐资源所有权和失败清理；不为生命周期缺口扩大为双进程重构。
- 旧来源故障采用后台显式停用/重新启用，保留数据和历史。仅在 UI 隐藏来源不能改变真实灯态；自动忽略失联来源会掩盖故障，均不采用。
- 保留测试接口成功响应中的 `scheduled`，增加 test_id；明确公布未就绪/重复测试的拒绝语义，不继续制造无设备测试成功。
- DSH 安装器识别固定 launcher 模板并迁移已知旧接入；未知结构只提供手工说明，不泛化改写任意 PowerShell 脚本。
- 完整插件目录作为 onedir 的稳定外部资源；在 WP1 后提前验证最小分发包，完整安装器仍在 WP6 完成。

这些是本修订采用的工程决策；对应实现、接口和验收条件以正文为准。

---

## 1. 当前实现基线

### 1.1 可复用模块

| 文件 | 当前能力 | 桌面化要求 |
|---|---|---|
| `pc/agent_light/api.py` | aiohttp 本地 HTTP、Bearer 鉴权、Origin 拒绝、限流、health/status/events/display | 改为既可 CLI 阻塞运行，也可由桌面线程嵌入运行 |
| `pc/agent_light/core.py` | SQLite、事件幂等、来源健康、会话状态、聚合、完成保持 | 原则上复用，不重写业务规则 |
| `pc/agent_light/serial_link.py` | VID/PID/序列号自动发现、串口事务、ACK、心跳、重连、三秒测试 | 增加设备快照、手动控制、详细测试状态 |
| `pc/agent_light/protocol.py` | USB COBS/CRC 编解码 | 保持不变 |
| `pc/agent_light/config.py` | 默认路径、初始化、token、默认显示配置 | 增加校验和原子保存 |
| `pc/agent_light/cli.py` | CLI 与 overlay 输出 | 将 overlay 生成提取为共享函数 |
| `plugins/dsh/src/index.ts` | DSH 宿主版本及指纹门禁、采集启动 | 运行逻辑保持不变，可新增只读检测工具 |
| `plugins/dsh/src/worker.ts` | 持久 outbox、HTTP 上报、两秒心跳 | 保持不变 |

### 1.2 当前可用能力

- 默认本地服务：`http://127.0.0.1:17321`。
- 当前已有 `GET /v1/health`、`GET /v1/status`、`POST /v1/display/test`。
- 当前三色测试约三秒，依次使用红、黄、绿，再恢复聚合状态，不改写 Agent 会话。
- 当前亮度范围 20–100，默认 35；完成保持默认 300 秒，0 表示不保持。
- 当前设备 `connected`、`serial_diagnostic`、`acked_revision` 已可作为设备状态基础。
- 当前来源 `health` 和 `lease_expired` 已可作为插件上报状态基础。
- DSH 插件包当前为 0.1.3，锁定 DSH 0.2.1-rc.2 / Cordis 4.0.5，并核查宿主文件指纹。
- GUI、托盘、开机启动和安装器尚未实现。

### 1.3 当前实现中需要修正的桌面化缺口

1. `api.serve()` 使用 `web.run_app()` 阻塞运行，不能直接放入 Qt 主线程。
2. `SerialWorker` 的配置主要在启动时传入，缺少运行时选择端口、断开和重新连接接口。
3. `/v1/display/test` 只返回 `scheduled`，即使设备不可用也会接受请求，不能支撑“每色 ACK 成功”的 UI。
4. 当前测试在某个颜色与已发送灯态相同时可能不生成新 SET，需要在显式测试模式中强制逐阶段 ACK。
5. `status.sources` 使用 JSON 字符串作为字典键，适合存储但不利于 UI；需要增加标准化数组，不破坏旧字段。
6. 当前没有当前进程收到心跳的墙钟时间，UI 不能仅凭持久化的 `healthy` 判断本次服务运行期间插件正在上报。
7. 当前设备状态缺少 UI 所需的选中端口、固件版本、设备 mode、实际灯态、最近状态时间等快照。
8. 亮度和完成保持时间缺少本地 HTTP 更新接口；更新后需要明确生效规则。
9. overlay 生成逻辑在 CLI 内，需要提取后供桌面端复用。
10. `application()` 在获取服务锁前打开 SQLite，启动失败可能不进入 cleanup；必须把创建和部分失败清理纳入同一所有权链。
11. 当前 `to_thread(open)` 会修改共享端口；取消外层任务后，线程仍可能创建未关闭的端口。退出和切换连接必须等待在途 I/O 收尾。
12. 所有历史 producer 都参与聚合，现有 clear 无法解除旧来源租约故障；需显式管理来源，而非删除数据或隐藏 UI。
13. 当前本机 launcher 已注入无成对标记的旧 overlay。安装器必须覆盖旧集成迁移，打包也必须包含完整 dist 依赖，不能只分发 index.js。

---

## 2. 产品目标与范围

### 2.1 首版必须完成

- 独立 PySide6 窗口程序。
- Windows 系统托盘驻留。
- 扫描串口、优先识别 Agent Light、手工选择 COM、查看连接与确认状态。
- 红、黄、绿逐色测试，逐阶段等待 ACK，结束后恢复最新业务灯态。
- DSH 环境检测、版本与指纹兼容检查、overlay 生成、受支持启动器的确认式安装。
- Codex 环境检测占位和“适配器未实现”的明确提示。
- 分别显示服务在线、插件上报通道正常、灯板已确认。
- 亮度、完成保持时间、开机启动、关闭窗口驻留托盘。
- 保留 CLI、现有 HTTP 事件接口、SQLite 数据和 outbox。
- 已停止来源可显式停用并保留历史，重新启用后通过新 runtime 屏障恢复。
- Windows onedir 安装包，插件入口使用稳定绝对路径。

### 2.2 首版明确不做

- 不修改固件或 USB 协议。
- 不增加光学传感器闭环，因此“三色测试成功”只表示设备已 ACK 并应用命令，不表示已验证肉眼或传感器所见亮度。
- 不实现 Codex 适配器。
- 不让桌面程序直接启动、停止或强制杀死 DSH 后端。
- 不自动修改不受支持的 DSH 启动脚本。
- 不实现 `dsh plugin add` 自动化；首版采用当前项目已经验证的独立 overlay 接入方式。
- 不实现 UI 崩溃后后台仍独立运行的双进程架构；保留后续拆分可能。
- 不实现插件在线下载、账号系统、云服务和远程访问。

---

## 3. 总体架构

### 3.1 进程和线程模型

首版采用单实例、单进程、双事件循环：

```text
Agent Light.exe
├─ Qt 主线程
│  ├─ QMainWindow + QStackedWidget
│  ├─ 状态 / 设备 / 插件 / 设置页面
│  ├─ QSystemTrayIcon
│  ├─ QNetworkAccessManager 本地异步客户端
│  └─ QProcess / QThreadPool 插件检测与安装任务
└─ asyncio 服务线程
   ├─ aiohttp AppRunner + TCPSite
   ├─ Store / SQLite
   ├─ SerialWorker
   └─ 现有事件、心跳和显示接口

DSH 插件 ──本机 HTTP──> asyncio 服务线程 ──USB CDC──> 灯板
Qt UI ──本机 HTTP 查询/控制──> asyncio 服务线程
```

### 3.2 为什么首版不拆成两个进程

- 用户只安装和启动一个桌面程序，托盘与后台生命周期一致。
- 不需要额外处理子进程隐藏窗口、跨进程停止、孤儿服务和双进程打包入口。
- 现有 `ProcessLock`、HTTP API 和状态边界仍然保留，未来可以拆分。
- UI 与后台通过本地 HTTP 交互，不形成 UI 直接操作串口或数据库的耦合。

### 3.3 Qt 与服务线程之间的规则

- Qt 主线程不能调用 `Store`、`SerialWorker.transaction()` 或阻塞式串口扫描。
- UI 使用 `QNetworkAccessManager` 访问 loopback，显式禁用代理，设置 Authorization，不发送 Origin。
- 服务线程使用独立 `asyncio` event loop。
- `ServiceRuntime.request_stop()` 通过 `loop.call_soon_threadsafe()` 请求停止；Qt 主线程不调用阻塞等待或 join。
- `SerialWorker` 的可变状态只由 asyncio 服务线程更新；HTTP handler 在同一线程读取快照。
- 串口阻塞调用使用专属单工作线程 executor；扫描使用独立受管任务。I/O 函数只接收固定句柄/参数并返回结果，连接、seq、ACK 等状态只在服务线程提交，具体收尾规则见 §5.4。
- 后台线程不得直接操作 QWidget；错误和生命周期变化通过 Qt Signal 或轮询结果传递。

### 3.4 启动与退出

启动顺序：

1. 解析 `--config` 和 `--minimized`，得到规范化绝对 config_path；创建 QApplication。
2. 按 §10.2 获取用户级单实例锁；第二实例只发激活请求，不初始化配置或服务。
3. 创建主窗口/托盘和异步启动协调器，先显示“正在启动”；托盘不可用时，即使 --minimized 也显示窗口。
4. 在受管任务中加载或初始化配置，不覆盖已有 token、数据库和 outbox；缺失 token 等不自动重置身份，报告可操作错误。
5. 异步探测 endpoint。已有兼容服务返回 SERVICE_ALREADY_RUNNING；其他服务、鉴权不符或占用不明返回 ENDPOINT_IN_USE。预探测仅作提示，最终以服务锁和端口绑定为准，不自动附加或结束进程。
6. `ServiceRuntime(cfg, config_path=...)` 只保存构造参数，start 后由服务线程创建应用及其资源。HTTP 成功绑定且本实例 health 验证成功后才进入 RUNNING。
7. 开始状态轮询。任何启动阶段均可请求退出；清理完成前不得创建替代 runtime。

退出顺序：

1. UI 进入“正在退出”，禁用新操作并停止轮询，异步调用 request_stop。
2. 停止 HTTP site 接受新连接；现存连接的新控制请求返回 SERVICE_STOPPING。处理在途 handler，最多给予 2 秒异步宽限；超时可取消 HTTP 响应等待，但已接受的配置/控制事务必须单独追踪并等待其持久化和内存发布完成，期间数据库保持打开。已提交的 connect 在 STOPPING 状态只保存配置，不再派发新串口 I/O；所有已接受任务收拢后才进入下一步。
3. 向串口队列发停止命令，测试转 failed/SERVICE_STOPPING。停止派发新 I/O，等待在途 open/transaction 完成，关闭返回的所有句柄；不得以 task.cancel() 代替 I/O 完成。
4. 收拢配置写入、扫描等受管任务并 shutdown 对应 executor，再关闭 SQLite、释放服务 ProcessLock。后台任务异常也必须走同一 finally 链。
5. 结束服务 loop 和线程；Qt 主线程用完成 Signal/定时检查确认线程结束，不同步 join。
6. 隐藏托盘、释放桌面 IPC/锁，再退出 QApplication。

正常退出目标为 5 秒内。超时报告 SHUTDOWN_TIMEOUT 并保持“清理中”、资源所有权和防重入，不伪报已停止、不启动新服务、不强杀线程。操作系统或驱动永久阻塞不承诺硬超时退出；必须提供可见错误并在验证记录中说明。启动失败按已取得资源逆序清理，不依赖 cleanup context 已执行到 yield。

关闭窗口只有在启用“关闭驻留托盘”时才隐藏窗口；托盘“退出”始终执行完整退出流程。

---

## 4. 模块和文件改造清单

### 4.1 新增文件

```text
pc/agent_light/
├─ runtime.py                    # ServiceRuntime，嵌入/阻塞两种运行方式
├─ devices.py                    # list_ports 扫描和标准化设备信息
├─ integrations/
│  ├─ __init__.py
│  └─ dsh.py                     # 路径发现、检测调用、overlay 生成、安装/卸载
└─ desktop/
   ├─ __init__.py
   ├─ app.py                     # 桌面入口、单实例、启动和退出协调
   ├─ client.py                  # 异步本地 API client、超时和错误映射
   ├─ models.py                  # 三类链路状态和业务灯态的展示模型
   ├─ main_window.py             # 主窗口、导航、页面切换
   ├─ tray.py                    # 托盘图标、菜单和提示
   ├─ startup.py                 # Windows 当前用户开机启动抽象
   ├─ resources.py               # 开发/安装环境的资源与插件路径解析
   └─ pages/
      ├─ __init__.py
      ├─ status.py
      ├─ device.py
      ├─ plugins.py
      └─ settings.py

plugins/dsh/tools/
└─ inspect-host.mjs              # 只读 JSON 检测结果，复用 verifyHost

pc/tests/
├─ test_runtime.py
├─ test_source_management.py
├─ test_devices.py
├─ test_desktop_api.py
├─ test_desktop_models.py
├─ test_dsh_desktop_integration.py
└─ test_desktop_ui.py

pc/tests/fixtures/dsh-launchers/  # clean、legacy-unmarked、managed-v1、unsupported

packaging/windows/
├─ AgentLight.spec               # PyInstaller onedir 配置
├─ runtime-lock.json             # 实测发布工具链与资源清单
└─ agent-light.iss               # 每用户安装器配置
```

图标等二进制资源可放入 `pc/agent_light/desktop/resources/`，并使用 package data 或 PyInstaller data 明确包含。若暂时没有正式图标，使用简单 SVG 资源，不阻塞功能开发。

### 4.2 修改文件

| 文件 | 修改范围 |
|---|---|
| `pc/agent_light/api.py` | 使用可嵌入 runtime；扩展 health/status；新增设备与显示配置接口；增强测试接口 |
| `pc/agent_light/serial_link.py` | 设备快照、启停/连接控制、显式测试状态机、最近 GET_STATUS 数据 |
| `pc/agent_light/config.py` | 配置校验、原子保存、显示配置更新；不改变默认目录和 token 初始化 |
| `pc/agent_light/cli.py` | 调用共享 overlay 生成器、传递 config_path；保留命令/成功输出，按 §6.10 更新错误分类 |
| `pc/agent_light/core.py` | 构造失败的 SQLite 清理、当前进程心跳辅助数据；§5.7 来源管理元数据及聚合参与门禁，不改 session 归约或优先级 |
| `contracts/fsm-transitions.md` | 实施 §5.7 时增补显式来源管理语义，保留所有默认 enabled 行为及 USB 合约 |
| `pc/pyproject.toml` | 增加 PySide6 desktop extra 和 GUI entry point，包含必要资源 |
| `plugins/dsh/package.json` | 若将只读检测工具纳入 npm 包，更新 files 清单；不放宽宿主版本门禁 |
| `README.md` | 增加桌面使用、托盘、配置和安装说明；保留 CLI 手册 |
| `THIRD_PARTY_NOTICES.md` | 增加 PySide6/Qt 及实际随包分发组件的许可说明 |

不要仅为桌面 UI 修改固件源码、USB 合约或 DSH 事件映射。

---

## 5. 后台详细设计

### 5.1 ServiceRuntime

`runtime.py` 提供统一的运行抽象，至少支持：

```text
ServiceRuntime(cfg, *, config_path)
.start()              # 非阻塞启动线程；完成/失败通过 Signal 桥或状态快照通知
.request_stop()       # 线程安全、非阻塞、幂等；启动中也可调用
.wait_stopped(timeout=...)  # 仅 CLI/测试/非 Qt 主线程可阻塞等待
.run_blocking()       # CLI serve 模式：保持现有命令行为
.is_running()
.startup_error        # 启动失败的结构化错误
.state                # NEW | STARTING | RUNNING | STOPPING | STOPPED | FAILED
```

实现要求：

- 在服务线程中使用 `web.AppRunner(application(cfg, config_path=...), access_log=None, handle_signals=False)` 和 `web.TCPSite`。CLI 主线程将 KeyboardInterrupt/停止请求送入同一清理入口。
- 继续校验 endpoint 只能是 IPv4 loopback HTTP。
- `application()` 构造阶段仅注册路由/上下文，不打开 SQLite。cleanup context 内先获取 ProcessLock，再读取 token、打开 Store、创建 ConfigRepository/SerialWorker；每个资源取得后立即登记 finally/ExitStack 清理。SQLite 创建、访问、关闭均在服务线程，不能用 check_same_thread=False 掩盖归属错误。
- Store 构造中途失败也必须关闭其已创建的 SQLite 连接；获取锁失败不得触碰数据库。runner.setup 或 site.start 任一步失败，runtime 的 finally 仍调用适用的 runner 清理并释放已取得资源。
- 启动失败必须通知 UI，不得留下半运行线程。
- 停止必须幂等，重复调用不抛异常。
- `api.serve(cfg, config_path=...)` 改为调用同一 runtime 的阻塞入口，CLI 传入实际 --config 路径。重复 start 在 STARTING/RUNNING 返回当前状态，不新建线程；STOPPED/FAILED 的实例不可复用，重试创建新实例。
- 保留 `application(cfg)` 供现有只读/事件单元测试调用，但无 config_path 时配置写入接口返回 503 CONFIG_PATH_REQUIRED，不猜测默认路径。生产入口必须传入路径。

### 5.2 配置管理

继续使用：

```text
%LOCALAPPDATA%\AgentLight\config.json
%LOCALAPPDATA%\AgentLight\token
%LOCALAPPDATA%\AgentLight\state.sqlite3
%LOCALAPPDATA%\AgentLight\dsh-outbox\
```

`config.py` 增加：

- `validate_config(cfg)`：校验必需字段、endpoint、亮度和完成保持时间。
- `save_atomic(path, cfg)`：同目录临时文件、flush/fsync、原子替换；保留原文件权限。
- `update_display_config(cfg_path, patch)`：只修改允许字段，不重写 tokenFile/database/dataDir。
- `ConfigRepository(config_path, cfg)`：唯一配置写入协调者；显示和串口更新共用 asyncio 锁及当前内存快照，不能各自读取旧文件后覆盖。

规则：

- `brightness` 必须是整数且 20–100，不能接受 bool。
- `completedHoldSeconds` 必须是非负整数，不能接受 bool；UI 建议范围 0–86400，但后台不新增不必要的历史配置上限。
- 保存失败时不得破坏原配置。
- 配置写入成功只代表持久化成功，连接与设备确认另行判断。
- 桌面专属配置使用 `QSettings("AgentLight", "Desktop")`，不写入后台 config.json。
- config_path 必须显式传递并规范化；使用非默认 --config 时只写该文件。显示 patch 不接受未知字段；串口 patch 只允许 port/serialNumber 等该接口明确允许的字段。
- 写入序列为“校验并预留操作 → 从最新内存快照合并 → 受管 I/O 原子保存 → 服务线程发布 cfg/Store.hold → 排队设备动作”。同一管理操作锁也用于测试启动，避免亮度保存与 start_test 穿插；持锁期间不等待串口 ACK。
- 写入线程不得修改服务状态。原子替换前失败保留旧配置和运行状态；成功替换后必须提交对应内存状态再释放锁。客户端超时/取消不取消已经接受的写入事务，UI 通过 GET 查询最终状态。
- 替换后的文件 hash/版本作为下次写入基线；检测到外部编辑返回 409 CONFIG_CHANGED_EXTERNALLY，提示重启服务重新加载，不自动覆盖。声明运行时外部直接编辑不受支持。
- 原子保存保留 Windows ACL（不能把 chmod 当作 ACL 保留实现）；使用同目录临时文件，失败清理临时文件，已有 token 文件不参与配置替换。

生效规则：

- 亮度保存后立即在后台更新，并强制下一次 SET 使用新亮度；IDLE 仍全灭。
- 完成保持时间保存后更新 `Store.hold`，只影响之后新观测到的完成事件，不批量重置当前会话 deadline。
- 串口选择保存后由后台开始连接；保存成功不等于连接成功。
- 测试 running 时拒绝所有显示配置 PATCH，返回 DISPLAY_TEST_RUNNING，既不保存也不排队；UI 禁用该保存按钮。设备离线时仍可保存显示配置，等待下一次正常同步。

### 5.3 串口扫描

`devices.py` 提供纯数据函数，例如：

```text
scan_devices(cfg, include_all=False) -> list[DeviceInfo]
```

`DeviceInfo` 至少包含：

- `port`：如 COM6。
- `description`。
- `manufacturer`，允许为空。
- `vid`、`pid`，十进制整数或 null。
- `serial_number`，允许为空。
- `matched`：是否符合当前 VID/PID 和可选序列号。

规则：

- 匹配设备排在前面，其余按端口名稳定排序。
- 默认 UI 只显示匹配设备，可展开全部串口。
- 多个匹配设备时不自动选择。
- 扫描失败返回可显示错误，不修改当前连接配置。
- 不根据“串口当前是否可打开”进行反复试开扫描，避免干扰现有连接。

### 5.4 SerialWorker 控制模型

保留现有事务、重试、心跳和指数退避。新增内部控制命令：

```text
connect(auto | manual, port=None, serial_number=None)
disconnect()
start_test(test_id)
```

所有命令通过 asyncio 服务线程的有界控制队列执行。HTTP handler 只校验、登记意图和排队，不能并发执行串口事务；队列满返回 409 DEVICE_BUSY，不保存未接受操作的配置。

串口所有权和取消规则：

1. 一个专属单工作线程 executor 只执行 open/transaction/close。事务函数接收固定 port、seq 和 payload；不得读取会被切换的 self.port，也不得更新 seq、cfg、confirmed 或 SQLite。服务线程分配 seq/显示 revision，重试复用同一个 seq。
2. open 只返回本地创建的句柄和状态数据，发生异常自行关闭句柄；返回后由服务线程接管。I/O future 的引用一直保留到实际完成，不因调用方请求取消而丢弃。单次事务沿用最多三次、每次约 100 ms ACK 等待，并保留串口读写超时。
3. 每次 connect、disconnect、重连或 stop 递增 connection_generation；立即撤销 confirmed/旧 ACK/旧 STATUS。结果必须带所属代次，旧结果不能提交，旧 open 返回的句柄必须排队关闭。
4. 换端口时先停止旧代次派发、等在途调用完成并关闭旧句柄，再打开新端口，始终最多一个活动串口句柄和一个未完成 USB 事务。断开/停止优先于尚未派发的普通显示动作。
5. disconnect 立即设置 enabled=false 并进入 DISCONNECTING，完全收尾后为 DISABLED；期间不得重连。connect 意图在旧连接清理完成后执行，配置保存成功只是意图已接受。
6. executor 关闭前等待其任务实际完成；不得以 daemon 线程、future.cancel 或 loop.close 伪装资源已释放。等待超过 2 秒报告 SERIAL_IO_STALLED，遵循 §3.4 的清理超时策略。
7. list_ports 扫描使用独立受管 executor，HTTP 等待超时返回 504 DEVICE_SCAN_TIMEOUT；同一时刻最多一个扫描任务，超时后不叠加新线程，结果过期只丢弃数据，退出仍收拢任务。

建议状态字段：

```text
enabled: bool
state: DISABLED | DISCONNECTING | DISCONNECTED | CONNECTING | RECONNECTING | CONNECTED
connection_generation: int
connected: bool
confirmed: bool
selected_port: str | null
serial_number: str | null
diagnostic: str
last_error: str | null
last_device_status: DeviceStatus | null
last_status_at: str | null
```

规则：

- `disconnect()` 禁止自动重连并执行上述收尾，最终状态为 DISABLED；不清除已保存配置。
- `connect()` 重新启用自动重连，立即开始一次连接。
- 手动连接保存 port 和可选 serialNumber，提供序列号时必须与端口枚举信息相符，否则 DEVICE_IDENTITY_MISMATCH。自动模式保存 port=None 和请求指定的 serialNumber；未提供/传 null 明确清空旧筛选，避免隐式沿用手动模式配置。
- 当前串口异常后继续 0.5 秒至 5 秒指数退避。
- 设备 CONFIRMED 与 CONNECTED 分开；打开 COM 不等于确认设备。

### 5.5 灯板确认规则

后台生成 `device.confirmed`，UI 不自行猜测。必须同时满足：

1. 当前 `connected=true` 且 `diagnostic="OK"`。
2. 当前 connection_generation 至少成功完成一次目标灯态 SET ACK；之前连接的成功记录无效。
3. 最近一次 GET_STATUS 成功，mode 为 ACTIVE，`revision_valid=1`。
4. STATUS 在最近成功 SET ACK 之后请求并完成，display revision、applied_state、brightness_pct 与该次已发送命令一致；IDLE 的状态亮度字段仍与命令配置比较，实际 LED 始终全灭。
5. GET_STATUS 接收时间距当前单调时钟不超过 2.5 秒。正常每 1 秒发 GET_STATUS，测试保持期间也不能停止保活；墙钟 UTC 只用于展示。
6. 存在尚未确认的新显示命令时 confirmed=false，状态为“同步中”。判断目标使用已排队/已发送的灯态与亮度，不把 Store 聚合 revision 的额外增长误当成已发送 USB revision。

GET_STATUS 原始数据转换为：

- `mode`：BOOT/WAIT_SYNC/ACTIVE/LINK_LOST/SUSPENDED/UNKNOWN。
- `applied_state`：IDLE/RUNNING/ATTENTION/ERROR/COMPLETED/NONE。
- `display_revision`。
- `brightness_pct`。
- `firmware_version`。
- `uptime_s`。
- `crc_drop_count`。

服务离线时，UI 的设备卡显示“未知（服务离线）”，不能显示“已断开”或继续沿用绿色已确认。

### 5.6 ACK 驱动的三色测试

保留 `POST /v1/display/test` 路径和 CLI 默认空调用，内部改为显式测试状态机：

```text
idle
  → red
  → yellow
  → green
  → restoring
  → succeeded

任意阶段发生设备错误 → failed
```

每个测试实例包含：

```text
test_id: str
state: idle | running | succeeded | failed
stage: none | red | yellow | green | restoring
started_at: str | null
finished_at: str | null
error: str | null
stage_results: list             # 每阶段 revision、ACK 时间、保持结束时间、错误码
```

行为要求：

1. 只有设备当前已确认时才允许启动，否则返回 409 `DEVICE_NOT_READY`。
2. 已有测试运行时返回 409 `DISPLAY_TEST_RUNNING`。
3. 每色匹配 ACK 到达后用单调时钟保持至少 1 秒，顺序固定为红、黄、绿；等待用 asyncio 定时，不阻塞 HTTP/保活。总时长为至少 3 秒加通信和恢复耗时。
4. 红色使用 ATTENTION，黄色使用 RUNNING，绿色使用 COMPLETED。
5. 每个阶段都强制递增 revision 并发送 SET，即使颜色恰好等于之前已发送状态，也不能因 `desired == sent` 而跳过 ACK。
6. 每阶段收到匹配 ACK 后才进入下一阶段。
7. 测试不修改任何 session base、waits、deadline 或 closed 状态。
8. 测试可以修改显示 revision，这是现有 USB 协议允许且需要保留的行为。
9. 测试期间 Store 仍正常接收和聚合 Agent 事件。
10. 恢复阶段发送派发该 SET 时的最新聚合状态，不使用测试开始前快照；恢复也强制使用新 revision，收到其匹配 ACK 后才为 succeeded。恢复 ACK 不等于保证之后没有新业务事件。
11. 中途断开时测试为 failed；重连后仍按正常同步机制恢复最新业务状态。
12. 测试结束后保留最近结果供 UI 查询，下一次测试或服务重启时重置。
13. 恢复等待中到达新业务事件，仍正常聚合；恢复 ACK 后退出覆盖模式并立即比较最新目标，必要时继续 SET，不将旧目标回写 Store。失败时也必须撤销覆盖，恢复交给正常连接流程。
14. 测试期间显示配置保存返回 DISPLAY_TEST_RUNNING；换端口、主动断开、服务退出均可接受，测试分别以 DEVICE_RECONFIGURED、DEVICE_DISCONNECTED、SERVICE_STOPPING 失败。不得等待三色结束才处理用户断开。
15. 开始测试时在同一管理操作锁内检查 confirmed/正在测试并设置 running，避免两个 HTTP 请求都被接受。每个 stage_results 只记录实际发送和 ACK 结果，UI 不按本地计时推测成功阶段。

### 5.7 来源停用与重新启用

本节是对 core 的受限管理扩展。来源键仍为 agent + producer_id；不删除 inbox、session、outbox 或身份，不改变普通事件的归约与健康优先级。实施时同步增补 `contracts/fsm-transitions.md` 的管理语义。

- 在同一 SQLite 中增加 `source_admin` 表，主键为来源键，保存 mode（enabled/disabled/activation_pending）、generation、disabled_at 和 enable_after_runtime_seq。老数据库缺行视为 enabled，迁移不得重置原 state/inbox。
- 显式 disabled 来源及其关联 sessions 不参与聚合；activation_pending 按下述恢复门禁贡献故障，暂不参与旧 session 聚合。UI 隐藏、插件卸载、没有聊天、普通租约过期均不得自动停用。enabled 的失联/degraded 继续贡献 ERROR，clear 不改变管理状态。
- 停用只接受已有来源，要求当前租约过期且用户确认已停止对应采集器；提交时重新检查租约和 source_admin.generation。最近仍有心跳返回 409 PRODUCER_STILL_REPORTING；服务重启授予的 15 秒登记窗口内也不能停用。
- 停用操作原子写管理状态并重新聚合，历史会话原样保留。不承诺消除其他来源的 ERROR。新到达该来源的 heartbeat/events 返回 409 PRODUCER_DISABLED，不续租、不修改其会话；只更新内存中的 rejected_after_disable_at 以提示“已停用但仍有上报”。保留既有重复事件最终确认规则，已入 inbox 的完全相同重试可返回原 duplicate 结果，不新增业务写入。
- 重新启用将 mode 置为 activation_pending，捕获该来源最高已知 runtime_seq/ready_seq 的最大值为 enable_after_runtime_seq；贡献恢复中的 ERROR，旧 sessions 暂不参与，提示重启 DSH。未知来源不能通过此接口虚构登记。
- activation_pending 允许既有事件正常入库与按原规则回放；只有提交 runtime_seq 严格大于上述基线的新 runtime_ready，且收到同一 runtime 的有效 heartbeat 后，才原子转 enabled。完成屏障仍由原 runtime_ready 逻辑退休旧实例，不批量改写 waits/base/deadline；旧心跳和旧屏障不能解除恢复门禁。
- 停用后的采集器若曾因 409 降级，重新启用后需重启采集器才能重放保留的 outbox。UI 必须说明这一点，不修改或删除 quarantine/segment 来伪装恢复。
- 管理状态跨服务重启保存；当前进程 last_heartbeat_at 仍从空开始，只有被 core 接受并续租的心跳才更新。旧 runtime 的被忽略心跳不能让 UI 显示正在上报。
- 来源管理与插件安装状态独立。卸载接入后显示“重启/退出 DSH 后，可停用旧来源”；不要根据安装脚本修改成功自动改变 source_admin。

---

## 6. 本地 HTTP API 扩展

所有现有和新增端点继续使用 Bearer token、Origin 拒绝、loopback 和限流。以下新增响应字段均为增量，不删除旧 CLI 已使用字段。

### 6.1 `GET /v1/health`

增加：

```json
{
  "desktop_api": 1,
  "service_version": "<从包元数据读取>"
}
```

保留 `schema_version`、`usb_protocol`、`database`、`event_types` 和 `sources`。

### 6.2 `GET /v1/devices`

查询参数：`include_all=true|false`，默认 false。

响应示例：

```json
{
  "devices": [
    {
      "port": "COM6",
      "description": "USB Serial Device",
      "manufacturer": null,
      "vid": 1155,
      "pid": 22336,
      "serial_number": "0123456789ABCDEF01234567",
      "matched": true
    }
  ]
}
```

### 6.3 `POST /v1/device/connect`

自动模式：

```json
{"mode": "auto", "serial_number": null}
```

手动模式：

```json
{"mode": "manual", "port": "COM6", "serial_number": null}
```

成功接受返回 202：

```json
{"status": "connecting", "configuration_saved": true}
```

该响应不能包含或暗示 `connected=true`。UI 继续轮询 status 获取最终连接结果。

### 6.4 `POST /v1/device/disconnect`

返回 202：

```json
{"status": "disconnecting", "enabled": false}
```

§6.4 的 202 只表示停止意图已接受；实际句柄关闭后 status.device.state 才为 DISABLED，不能提前宣称资源已释放。

### 6.5 `GET /v1/config/display`

```json
{"brightness": 35, "completedHoldSeconds": 300}
```

### 6.6 `PATCH /v1/config/display`

允许只更新一个字段：

```json
{"brightness": 50, "completedHoldSeconds": 120}
```

成功：

```json
{"status": "applied", "configuration_saved": true, "backend_applied": true, "brightness": 50, "completedHoldSeconds": 120}
```

校验失败返回 422 `INVALID_DISPLAY_CONFIG`，写入失败返回 500 `CONFIG_SAVE_FAILED`，不得截断原配置。

`applied` 仅表示持久化和后台配置已提交，不表示设备 ACK。响应不提供推测的 device_confirmed；从后续 status 获取设备同步结果。测试运行时为 409 DISPLAY_TEST_RUNNING；运行时外部改文件为 409 CONFIG_CHANGED_EXTERNALLY。

### 6.7 `GET /v1/status` 增量结构

保留原有 `sources`、`sessions`、`desired`、`revision`、`connected`、`acked_revision` 和 `serial_diagnostic`，新增：

```json
{
  "producers": [
    {
      "agent": "dsh",
      "producer_id": "p",
      "runtime_id": "r",
      "management_state": "enabled",
      "management_generation": 0,
      "sessions_participating": true,
      "health": "healthy",
      "lease_expired": false,
      "last_heartbeat_at": "2026-11-08T07:00:00Z",
      "persisted_seq": 10,
      "acked_seq": 10
    }
  ],
  "device": {
    "enabled": true,
    "state": "CONNECTED",
    "connection_generation": 1,
    "connected": true,
    "confirmed": true,
    "selected_port": "COM6",
    "serial_number": "0123456789ABCDEF01234567",
    "diagnostic": "OK",
    "last_error": null,
    "mode": "ACTIVE",
    "applied_state": "RUNNING",
    "display_revision": 12,
    "acked_revision": 12,
    "brightness_pct": 35,
    "firmware_version": "1.0",
    "uptime_s": 100,
    "crc_drop_count": 0,
    "last_status_at": "2026-11-08T07:00:00Z"
  },
  "display_test": {
    "test_id": "uuid",
    "state": "running",
    "stage": "yellow",
    "started_at": "2026-11-08T07:00:00Z",
    "finished_at": null,
    "error": null
  }
}
```

`last_heartbeat_at` 使用 UTC ISO 8601；只有当前服务进程实际收到 heartbeat 后才设置。服务重启后，持久化的旧 `healthy` 不得单独让 UI 显示“正在上报”。

更准确地说，该 heartbeat 必须被 core 接受并续租；被拒绝或因旧 runtime 被忽略的请求不算。producers 数组保留 disabled 项并标记 sessions_participating=false，不从历史 sources 删除。activation_pending 项 sessions_participating=false，但其恢复故障仍参与聚合。enabled 项为 true；此字段仅指关联 sessions 的贡献，不表示所有故障贡献均已排除。

display_test 另含 stage_results，顺序为 red/yellow/green/restoring；每项有 stage、revision、acked_at、held_until、error。恢复阶段 held_until=null；未发生的时间为 null，不能补造。UTC 时间用于呈现，保持和超时采用单调时钟。返回最近测试的完整阶段结果使低频轮询也可展示真实历史。

### 6.8 错误处理

新接口至少使用稳定的机器可读错误码：

```text
INVALID_REQUEST
DEVICE_NOT_UNIQUE
DEVICE_NOT_FOUND
DEVICE_NOT_READY
DEVICE_BUSY
DISPLAY_TEST_RUNNING
INVALID_DISPLAY_CONFIG
CONFIG_SAVE_FAILED
SERVICE_ALREADY_RUNNING
ENDPOINT_IN_USE
CONFIG_PATH_REQUIRED
CONFIG_CHANGED_EXTERNALLY
DEVICE_SCAN_TIMEOUT
DEVICE_IDENTITY_MISMATCH
DEVICE_RECONFIGURED
DEVICE_DISCONNECTED
SERIAL_IO_STALLED
SERVICE_STOPPING
SHUTDOWN_TIMEOUT
PRODUCER_NOT_FOUND
PRODUCER_STILL_REPORTING
PRODUCER_DISABLED
SOURCE_STATE_CHANGED
```

UI 使用错误码映射中文说明，不解析英文异常正文。日志只记录白名单错误码和必要的端口/路径，不记录 token。

新增/修改的管理接口使用 JSON `{"error":{"code":"DEVICE_NOT_READY"}}`，Content-Type 为 application/json；401/403/429 等共享 middleware 响应可继续保留旧格式。现有 events、heartbeat 的既有错误格式与成功响应保持兼容，PRODUCER_DISABLED 为新增机器码，不扩展事件 schema。

### 6.9 `POST /v1/display/test`

继续接受 CLI 的空对象 `{}`。设备确认有效且没有正在运行的测试时，返回 HTTP 200：

```json
{"status": "scheduled", "test_id": "uuid"}
```

保留旧成功状态码和 scheduled 字段；接受时测试实例已登记为 running，后续成功/失败从 status 查询。未就绪为 409 DEVICE_NOT_READY，已有测试为 409 DISPLAY_TEST_RUNNING；这两项是明确的兼容性收紧，不承诺旧的无设备接受行为。

### 6.10 CLI 错误与安装版入口

- 保留所有原命令名、参数和正常成功输出；test 成功只增加 test_id，退出码为 0，不阻塞等待测试结束。
- test 的设备未就绪/重复测试，stderr 分别输出 `DEVICE_NOT_READY` / `DISPLAY_TEST_RUNNING`，退出码 3。
- 连接拒绝、网络超时才输出 SERVICE_UNAVAILABLE，退出码 1；401/403 输出 AUTH_FAILED，退出码 4；其他 HTTP 错误使用白名单码或 HTTP_ERROR，退出码 1。不能把全部 HTTPError 映射为服务离线。
- argparse 参数错误仍为退出码 2；event 的安静输出和原有超时/退出行为不变。源代码安装仍提供 agent-light，Windows 安装器同时提供 console 入口 agent-light.exe，与 GUI 共享运行逻辑及用户配置。

### 6.11 `POST /v1/producers/disable` 与 `POST /v1/producers/enable`

请求均为明确身份和预期管理版本，不允许按 agent 一次批量处理：

```json
{"agent": "dsh", "producer_id": "p", "expected_generation": 0, "confirm": true}
```

字段严格校验；confirm 必须为 true。来源不存在返回 404 PRODUCER_NOT_FOUND，版本不同返回 409 SOURCE_STATE_CHANGED，disable 时仍有有效租约返回 409 PRODUCER_STILL_REPORTING。校验与写入在服务线程同一事务完成。

成功返回 200，包含 `agent`、`producer_id`、`management_state`、`management_generation`；enable 另含 `restart_required:true`。真正状态变化才增加 generation，相同目标状态且 generation 匹配的重复调用不改变数据。activation_pending → disabled 也须满足停用的租约条件。正常 enabled 来源重复 enable 为幂等操作，restart_required=false。

这两个接口遵循 §5.7。UI 对停用/重新启用展示来源身份与效果并请求确认；确认的是来源管理，不是删除数据或强制结束 DSH。

---

## 7. 桌面 UI 详细设计

### 7.1 主窗口

采用 Qt Widgets：

- `QMainWindow`。
- 左侧导航：状态、设备、插件、设置。
- 中央 `QStackedWidget`。
- 顶部或底部显示最近错误与“重新检测”入口。
- 建议初始尺寸约 960×640，允许缩放，不使用固定像素布局。
- 状态不能仅靠颜色表达，必须同时有文字和图标/形状。

### 7.2 状态页

顶部四块信息：

1. 本地服务。
2. DSH 上报。
3. 灯板确认。
4. 当前业务灯态。

Codex 在来源列表单独显示“适配器未实现”，不与 DSH 合并成“全部插件正常”。

状态页显示：

- 服务版本、endpoint（不显示 token）。
- 每个 producer 的 agent、health、最近心跳、队列水位。
- 当前业务 `desired`。
- 设备 COM、固件版本、mode、applied_state、revision/acked_revision。
- 当前测试阶段和结果。
- 白名单诊断错误码。

多个 producer 的汇总规则（只对 management_state=enabled/activation_pending 的来源计算运行摘要，disabled 保留在明细）：

“活跃来源”在这里指管理状态未停用，不以是否存在聊天或近期是否有事件筛选。正常须同时满足 enabled、health=healthy、lease_expired=false 且当前进程 last_heartbeat_at 非空；时间是否有效由后台租约判断，UI 不使用本机墙钟猜测。

- 有任一 `degraded` 或 `lease_expired`：该 agent 显示异常。
- 有任一健康活跃 producer，同时另一 producer 失联：仍显示异常，可展开查看。
- 只有所有已登记活跃 producer 都满足健康条件，才显示该 agent 上报正常。
- 没有 producer：显示“未上报”，而不是“正常”。
- 全部来源 disabled：显示“来源已停用”；activation_pending 显示“待重启来源/恢复中”，并解释其故障仍贡献 ERROR。disabled 来源出现被拒绝上报时显示独立警告。
- 明细提供“停用来源”“重新启用”操作，确认文案说明旧状态将排除/需新 runtime 重建；成功后重新查询 status，不能自行改 session 或直接刷成绿色。

### 7.3 设备页

控件：

- “扫描”按钮。
- “自动发现/手动指定”选择。
- COM 下拉框和“显示全部串口”开关。
- 可选序列号显示/筛选。
- “保存并连接”“断开”“重新扫描”。
- 设备状态、最近错误和详细设备信息。
- 红黄绿预览和“开始三色测试”按钮。

交互要求：

- 扫描和连接期间禁用重复提交，但不阻塞其他页面。
- 连接按钮返回后立即显示“连接中”，不能等待串口最终结果才恢复 UI。
- 手动模式未选择端口时禁止提交。
- 测试运行期间禁止重复测试，显示当前阶段。
- 测试期间禁用显示配置保存；断开和切换端口仍可用，并提示将终止当前测试。连接收尾期间显示 DISCONNECTING，不以已发送请求代替已关闭句柄。
- 测试成功文案为“灯板已确认完成三色测试”，不得写成“LED 光学检测通过”。

### 7.4 插件页

DSH 区域：

- 自动检测结果和手工路径选择。
- DSH 入口、Node 运行时、宿主版本、Cordis 版本、插件版本。
- 兼容/不兼容/未检测状态。
- 不支持项目的列表。
- “重新检测”“生成接入配置”“安装接入”“卸载接入”“打开配置目录”。

Codex 区域：

- 检测命令和版本可作为只读信息。
- 固定显示“统一事件接口已预留，真实适配器尚未实现”。
- 生成与安装按钮禁用。

### 7.5 设置页

- 亮度：滑块 + 数字输入，20–100。
- 完成保持：秒数输入，0 表示不保持。
- 开机启动：开关。
- 关闭窗口驻留托盘：开关。
- 显示配置使用“保存并应用”按钮；避免滑块每个 tick 都写配置和发串口。
- 桌面开关可立即生效并写入 QSettings。
- 保存后分别反馈“配置已保存”和“后台已应用/应用失败”。

### 7.6 状态轮询

- 窗口可见时每 2 秒请求一次 `/v1/status`。
- 窗口隐藏到托盘后可降为每 5 秒一次。
- 连接、测试、保存等操作完成后触发一次提前刷新。
- 请求超时建议 1–2 秒，不阻塞 UI。
- 使用递增请求序号，忽略晚到的旧响应。
- 连续三次失败后显示服务离线；恢复成功后立即更新。
- 首次超时、网络错误或鉴权失败即把插件/设备旧快照标记为过期或未知，撤销绿色正常标记；前三次之间服务标签可显示“刷新失败”，第三次才改“离线”。任何失效响应都不能被较早的成功响应覆盖。
- 运行三色测试时，无论窗口是否可见，status 临时改为每 250 ms 请求一次，每类查询最多一个在途请求；请求未完成不累积队列。结束/失败后恢复普通频率，stage_results 用于补齐漏看的 ACK 历史，不重放虚构动画。
- Qt 网络 client 设置真实总超时，超时 abort 并 deleteLater 回收 reply；服务启动/停止不等待主线程同步网络调用。

---

## 8. DSH 检测与接入

### 8.1 路径发现

按顺序尝试：

1. 用户上次在 QSettings 中保存的有效路径。
2. PATH 中的 `dsh.cmd`、`dsh-web`/`dsh-web.ps1`。
3. 用户手工选择 DSH `lib/bin.js` 和对应 Node 运行时。

不得在代码中固化当前开发机路径。发现失败时允许浏览选择，不执行修改。

### 8.2 只读宿主检测

新增 `plugins/dsh/tools/inspect-host.mjs`：

- 输入：DSH `lib/bin.js` 绝对路径。
- 使用 DSH 对应 Node 执行。
- 通过 `createRequire(entry)` 读取实际宿主包版本。
- 调用现有 `verifyHost(entry)` 执行完整版本和 SHA-256 门禁。
- stdout 只输出一个 JSON 结果；诊断写 stderr。
- 工具只读，不启动 Web、不读取聊天、不修改 profile。

建议输出：

```json
{
  "schema_version": 1,
  "compatible": true,
  "entry": "<absolute bin.js>",
  "detected": {
    "dsh-agent": "0.2.1-rc.2",
    "dsh-session": "0.2.1-rc.2",
    "cordis": "4.0.5"
  },
  "expected": {
    "dsh-agent": "0.2.1-rc.2",
    "dsh-session": "0.2.1-rc.2",
    "cordis": "4.0.5"
  },
  "adapter_version": "0.1.3",
  "mismatches": [],
  "error_code": null
}
```

失败时保留检测到的版本，`compatible=false`，`error_code` 使用 `UNSUPPORTED_VERSION`、`HOST_NOT_FOUND`、`NODE_RUNTIME_MISSING` 等稳定值。指纹不匹配可报告 `host_fingerprints`，不得通过修改版本号或忽略指纹绕过。

桌面端用 QProcess 运行检测，设置超时并捕获 stdout/stderr；不得使用 shell 拼接未经转义的命令。

检测超时为 10 秒，stdout/stderr 各限 64 KiB；仅可终止本程序启动且仍持有句柄的只读检测子进程，不能按进程名结束宿主 Node/DSH。§0 禁止杀进程不包括这一受管检测任务的清理。参数使用独立 argv，工作目录显式指定，Node 必须来自选中宿主而非随意使用 PATH 中另一个版本。冻结程序的子进程环境处理见 §11.5。

### 8.3 overlay 生成

从 CLI 提取共享函数，例如：

```text
generate_dsh_overlay(cfg, package_dir, installed=False) -> str
```

要求：

- 保持现有 CLI 输出结构。
- 校验 §11.2 的完整插件资源清单，不只检查 `dist/index.js`；遗漏返回 PLUGIN_BUILD_MISSING 并列出缺失的白名单相对文件名。
- 入口必须使用 `Path.resolve().as_uri()`。
- endpoint/tokenFile/dataDir 使用同一份 PC 配置。
- 不包含 token 内容。
- 桌面实际接入文件为 `integration_root(config_path)/dsh-overlay.yml`；默认配置沿用 `%LOCALAPPDATA%\AgentLight\integrations\dsh-overlay.yml`，自定义配置的隔离目录按 §11.2 计算。
- 生成成功后仅显示“配置已生成”。
- “生成接入配置”只写 `integration_root/drafts/dsh-overlay.yml` 供预览/手工另存，不覆盖 launcher 已引用的正式 overlay；点击“安装/更新接入”并确认后才按事务发布正式文件。CLI overlay 仍只输出文本，不写这些文件。

### 8.4 安装接入：首版范围

首版只支持当前项目已验证的“独立 overlay + dsh-web 包装脚本自动携带 `--patch`”方式，不自动执行 `dsh plugin add`。

安装步骤：

1. 重新执行宿主兼容检测，不兼容则停止。
2. 确认完整插件资源和 §8.3 的 overlay 草稿均存在；正式 overlay 在确认后的事务中发布，不能在此提前覆盖。
3. 解析实际 `dsh-web.ps1`，确认是受支持的 PowerShell 包装脚本。
4. 按 §8.4.1 的固定模板分类并生成最小差异；未知结构返回 INSTALLER_UNSUPPORTED，不修改文件。发现旧接入时先走显式迁移。
5. 检查 3080 端口、相关进程和 outbox 锁只能作为辅助；无法可靠确认时要求用户明确确认“已退出所有 DSH Web 后端”。
6. 展示目标脚本、草稿与正式 overlay 路径、精确差异和备份位置，等待用户确认。
7. 备份原脚本到 `%LOCALAPPDATA%\AgentLight\backups\`，文件名包含时间戳和原文件哈希。
8. 保留原文件其他内容、参数转发和浏览器打开逻辑；新接入只维护标记块，已知旧接入按 §8.4.1 替换其精确范围。
9. 已存在相同管理块时保持幂等；路径变化时只更新管理块。
10. 写入前重新核对预览时原文件 SHA-256；不同返回 INSTALLER_CONCURRENT_CHANGE 并重新预览。原子写入保留原 ACL、换行和编码，首版支持 UTF-8（含/不含 BOM）、UTF-16LE BOM；未知编码停止。Unicode/空格路径必须经过正确 PowerShell 字符串转义并测试，不能把中文用户名当作默认不支持。
11. 写入后重新读取校验并原子保存安装记录。校验失败仅在当前文件仍等于本次写入内容时回滚；若有用户并发修改则不覆盖，返回 INSTALLER_ROLLBACK_REQUIRED 和备份位置。
12. 最终只显示“接入配置已安装，重启 DSH 后生效”。

不得自动结束 DSH 进程，不得通过删除 `owner.lock` 解决冲突。

### 8.4.1 launcher 模板、旧接入迁移和记录

fixture 位于 `pc/tests/fixtures/dsh-launchers/`，内容使用占位路径，不提交真实用户路径。首版识别 clean（无接入）、legacy-unmarked（已验证旧注入代码）、managed-v1（本版本管理块）；其余为 unsupported。受支持结构要求参数数组在调用前构建、唯一 DSH 调用及已知参数转发，不靠关键词或宽泛正则修改任意脚本。

新管理块标记固定为 `# BEGIN AGENT-LIGHT MANAGED v1` 与 `# END AGENT-LIGHT MANAGED v1`，每文件只允许一对，位于参数数组初始化之后、浏览器和 DSH 调用逻辑之前。缺失一端、嵌套、重复标记或块内部未知修改均停止自动修改。

- clean：在 fixture 唯一锚点插入管理块。
- legacy-unmarked：按已审计 token/AST 结构精确匹配旧 `$agentLightPatchPath`、patch 去重循环及注入分支，路径字面量允许变化，控制流必须相同。预览明确“迁移旧接入”；确认后只替换旧范围，不在旧块旁追加第二块。无法证明匹配即拒绝自动迁移。
- managed-v1：按标记、已记录的块 hash 和支持模板更新；相同目标重复安装为 no-op。块外用户修改保留。
- 管理块按规范化绝对路径去重同一 overlay；显式用户 patch 若引用另一个已知 Agent Light overlay，则报告 INTEGRATION_CONFLICT，不能同时注入两个固定节点 id。只检查独立 overlay 的插件节点标识，不遍历聊天或原始 profile；未知来源的 Agent Light 接入要求用户先手工解除。
- 安装记录写到 `integration_root(config_path)/dsh-installation.json`，保存 config_path、launcher_path、模板版本、管理块 hash、overlay_path、plugin_root、备份路径及原/新文件 hash，不保存 token、脚本正文或聊天。修改脚本前先持久化 pending 记录，成功后标记 committed；下次启动发现 pending 时核对 hash 并恢复/引导核对，不盲目重复安装。
- 首版每个 config 最多一个已管理 launcher，同一 launcher 最多归属一个 config。检测/浏览新宿主不转移接入所有权；安装到不同 launcher 前，必须先按记录解除旧 launcher 并把记录标为 detached，再允许新安装。旧 launcher 无法访问或状态不明时返回 INTEGRATION_TARGET_CHANGED，保留原记录并要求先手工核对，不能覆盖记录后遗忘旧引用。
- 已归属另一个 config 的 launcher 返回 INTEGRATION_OWNED_BY_OTHER_CONFIG，先解除原配置接入再切换。§11.4 的用户级配置索引保存所有 pending/committed 记录路径；只有明确 detached 后才可撤销活动引用，不因用户切换配置或选择新宿主而删除索引。历史记录/备份保留供回滚，路径更新仅指同一已管理 launcher 内的受控 overlay/plugin 路径变更。
- launcher 与 overlay 的多文件变更不是单一文件原子事务。先暂存所有文件和备份，确认退出 DSH后依次提交；失败按 hash 保护回滚，安装记录保留可恢复状态。安装完成检查只剩一个预期的 Agent Light 接入。
- 若用户直接更改任意文件导致无法识别，停止自动修改并展示明确差异/手工方案；不通过重写整份 launcher 获得“成功”。

### 8.5 卸载与回滚

- 卸载只移除 Agent Light 明确管理标记块，保留用户其他修改。
- 若脚本已有无法识别的后续变化，不直接用旧备份覆盖整个文件；提示用户核对。
- 保留 overlay 和备份，除非用户另行明确删除。
- 卸载后同样显示“重启 DSH 后生效”，不影响当前运行中的 DSH。
- 对已知 legacy-unmarked，可经同样预览和确认精确移除旧范围；未知旧接入不自动处理。管理块卸载使用安装记录和即时 hash 校验，pending/外部变化按 §8.4.1 处理。
- 卸载接入不删除 source_admin，也不把旧 producer 标健康。待采集器停止且租约过期，UI 引导用户显式停用来源；重新接入沿用原 config/dataDir/producer，避免无意创建第二身份。

### 8.6 插件运行状态

- `diagnostics.json` 的 `CAPTURE_READY` 只能作为“最近报告已加载”的辅助诊断。
- 该文件可能被失败的新实例覆盖，不能单独作为活跃来源依据。
- 最终运行状态以 PC `/v1/status` 的 producer health、lease 和当前进程心跳为准。
- 安装、卸载和生成配置都不能直接改变“正在上报”状态。

---

## 9. Codex 预留

首版实现一个通用 `IntegrationInspector` 接口即可，不实现 Codex 适配器：

```text
detect() -> IntegrationDetection
generate_config() -> 不支持
install() -> 不支持
```

UI 可以检测 `codex` 命令和版本，但该信息只表示安装了 Codex，不表示事件链路可用。

未来 Codex 适配器需要独立设计和验证：

- 真实生命周期 Hook 或插件事件来源。
- producer/runtime/instance/turn 身份映射。
- 持久 outbox、心跳和 runtime_ready。
- 与 DSH 相同的来源隔离和隐私约束。

这些工作不属于本次桌面 UI 实施范围。

---

## 10. 托盘、单实例和开机启动

### 10.1 托盘

菜单至少包含：

- 打开主界面。
- 服务、DSH、灯板的只读简要状态。
- 三色测试。
- 设置。
- 退出 Agent Light。

要求：

- 托盘 tooltip 显示三项状态，但不包含聊天或 token。
- 第一次关闭到托盘时提示“Agent Light 仍在后台运行，可从托盘退出”。
- 托盘测试与窗口测试调用同一接口，不另写控灯逻辑。
- 托盘不可用时禁用关闭驻留，并保持窗口可见。
- QApplication 使用 `setQuitOnLastWindowClosed(False)`，统一由退出协调器在资源清理完成后 quit；关闭驻留未启用时 closeEvent 请求完整退出。启动时 --minimized 且无托盘也必须显示窗口；托盘运行中失效时恢复窗口。

### 10.2 单实例

- 使用用户级 QLockFile：首版同一 Windows 用户只运行一个桌面实例，不按 config 分裂多个 GUI。锁/IPC 名含用户身份稳定摘要，放在该用户本地目录。
- 使用 QLocalServer/QLocalSocket 或等价本机 IPC，让第二实例请求已有实例显示主窗口。
- 第二实例不启动第二个 ServiceRuntime。
- 服务 ProcessLock 仍作为 CLI 与桌面之间的最终冲突保护。
- 锁文件异常时显示错误，不直接删除未知活动锁。
- IPC 限当前用户，仅接受 show_window 和规范化 config_path 等白名单字段；不接受任意执行命令或 token。相同 config 请求激活；不同 config 激活现有窗口并显示 CONFIG_INSTANCE_CONFLICT，要求先退出再切换，不静默替换配置。
- QLockFile/IPC 的陈旧资源只能在系统确认所属进程已退出后由正常恢复机制处理；不能以连接失败单独认定锁已过期。另一个用户不共享端口时仍各自独立；同端口由 HTTP 绑定失败显式报告。

### 10.3 开机启动

Windows 使用当前用户 Run 键，值名 `AgentLight`，目标为完整引用的安装版 exe 加 `--minimized --config "<实际配置绝对路径>"`。必须使用 Windows 命令行参数引用规则，测试空格和中文路径；不能省略自定义 --config。

要求：

- 不需要管理员权限。
- 开关失败时保留 UI 真实状态并显示错误。
- 启动设置抽象为 `StartupManager`，单元测试使用 fake，不修改真实注册表。
- 源码运行模式没有稳定安装入口时禁用开机启动并提示安装桌面版，不写指向开发虚拟环境的命令。
- 卸载只移除当前值仍指向本安装目录的 AgentLight 启动项，不覆盖用户另行修改的值，不删除用户数据目录。

---

## 11. 打包与资源路径

### 11.1 Python 包

`pyproject.toml` 建议增加：

- desktop optional dependency：`PySide6>=6.10.1,<6.11`；Python 3.14 支持从该补丁线起计，实际发布构建按 §11.5 精确锁定，不随机器解析到不同依赖。
- GUI entry point：`agent-light-desktop = agent_light.desktop.app:main`。
- 桌面图标、SVG、event-schema 等 package data。

CLI entry point 保留。

### 11.2 Windows 分发

采用 PyInstaller onedir + 每用户安装器：

```text
%LOCALAPPDATA%\Programs\AgentLight\
├─ AgentLight.exe                # windowed GUI
├─ agent-light.exe              # console CLI，保留原命令
├─ _internal/                   # Python、Qt、元数据、event-schema、图标
└─ resources/
   ├─ resource-manifest.json    # 必需资源相对路径和 hash
   └─ plugins/dsh/
      ├─ package.json          # 保留 type=module、插件版本
      ├─ dist/                 # 构建所得完整目录
      │  ├─ index.js
      │  ├─ reporter.js
      │  ├─ worker.js
      │  ├─ adapter-0.2.1-rc.2.js
      │  └─ host-lock.js        # 其他构建文件也随完整 dist 分发
      └─ tools/inspect-host.mjs
```

用户数据继续保存在 `%LOCALAPPDATA%\AgentLight\`，与程序目录分离。

目录树是最小必需清单，不允许删去间接依赖。spec 明确收集 Python event-schema、agent-light distribution metadata、Qt platforms/qwindows 和使用的 SVG 插件及图标；仅声明 package-data 或 GUI entry point 不能替代冻结打包清单。dist 由本次锁定工具链重新构建，发布清单记录 hash；缺任一依赖或 hash 不匹配均不得生成可安装产物。Node 不随本程序捆绑，检测和插件均使用所选 DSH 环境的 Node。

`integration_root(config_path)` 由一个共享函数解析：规范化真实绝对路径并按 Windows 文件路径的大小写规则生成 config_id（完整 SHA-256）。规范化路径等于 default_path 时使用 `%LOCALAPPDATA%\AgentLight\integrations`；其他配置使用 `<config父目录>/integrations/<config_id>/`。overlay、draft、安装记录都在各自根目录中；同一父目录的 a.json/b.json 也必须完全隔离。不可仅按父目录、文件 stem 或 endpoint 判断身份。全局安装索引存实际 config_path 与对应根目录，不静默迁移已存在记录。

GUI 的生成/安装/卸载及安装器维护入口共用这一解析函数；CLI 文本生成使用调用者提供的 cfg，不隐式改写其他配置的 overlay。已登记旧路径迁移必须经过 §8.4.1 的预览/确认。

不使用 onefile，原因：

- 临时解压目录会变化。
- DSH overlay 需要稳定插件 file URL。
- DSH 重启后仍必须能访问同一插件入口。

### 11.3 路径解析

`desktop/resources.py` 统一处理开发环境和打包环境：

- 不依赖当前工作目录。
- 不在业务模块散落 `sys._MEIPASS` 判断。
- 冻结环境稳定外部插件目录按 exe 所在目录解析；Python 内部资源按包资源位置解析。两者分开，不能把 `_internal` 或临时解压目录误写入 overlay；校验完整 manifest，缺失时返回 PLUGIN_BUILD_MISSING。
- 程序升级保留相同安装根目录；插件变更后提示重启 DSH。

### 11.4 安装器边界

- 默认不修改 DSH，只有用户在插件页明确执行安装接入才修改。
- 默认不覆盖 `%LOCALAPPDATA%\AgentLight` 中的 token、配置、数据库和 outbox。
- 记录 PySide6/Qt 等实际随包组件许可。
- 首版不要求代码签名和自动更新，但发布公开安装包前应另行补充。
- 覆盖升级前要求用户退出 Agent Light 和加载该目录插件的 DSH 后端，再替换文件；不在运行中混用新 index 和旧 Worker。资源清单校验失败不启动新版，保留旧版以供回滚。
- 程序卸载前执行接入预检：发现本安装记录中仍有外部 launcher 引用该 plugin_root，先展示并确认移除受管块；未知/被修改结构或用户取消解除时中止卸载，先给出手工移除路径，不能删除插件后留下损坏启动器。手工创建的未登记 overlay 需在卸载向导明确提示用户解除，不能宣称已扫描所有宿主环境。
- 预检/解除由安装目录内的维护入口实现（GUI `--prepare-uninstall` 模式，不启动服务）；若桌面已运行先引导用户正常退出。解除须核对所有已登记配置的安装记录、hash 和预览，成功退出码 0 才允许安装器删除文件。安装器另保存最小配置/记录路径索引以覆盖自定义 --config，不存 token。
- 维护入口不能自动停用数据库来源；保留用户数据、overlay、备份及 source_admin。以后重新安装时状态仍可解释和恢复。

### 11.5 工具链与最小分发验证

首版发布目标限定 Windows 11 x64、CPython 3.14.0 标准 GIL 构建；其他 Windows/ARM64/free-threaded 组合不在首版验收矩阵。Python 包保留 3.11+ 的源码兼容声明，但不能据此宣称所有组合已完成桌面分发验证。

候选构建基线为 PySide6/Qt 6.10.3、PyInstaller 6.16.0，运行依赖使用当前已通过基础回归的 aiohttp 3.14.5、pyserial 3.5、jsonschema 4.26.0；DSH 构建沿用 package-lock 和 TypeScript 5.7.3。WP0 解析并写入 runtime-lock.json 的精确 PySide6、shiboken6、hooks-contrib、安装器版本及全部构建依赖/hash，WP1a 实测通过后才能标记 verified。失败时调整锁文件并重跑，不能把候选组合写成已验证兼容矩阵。上游支持依据：[Qt 6.10 发布说明](https://doc.qt.io/qtforpython-6.10/release_notes/pyside6_release_notes.html)、[PyInstaller 发布说明](https://pyinstaller.org/en/latest/CHANGES.html)；本项目安装和烟雾验证仍是发布条件。

构建最小 onedir 后，从不含源码的目录验证：Qt 窗口/平台插件加载、CLI health/status、event-schema 与版本元数据、完整插件 import、选定 Node 运行 inspect-host、fake HTTP/token/outbox 下 Worker 就绪；并使用带空格和中文的路径运行。无 DSH 环境时报告 HOST_NOT_FOUND，不能假装通过真实宿主兼容检查。

冻结程序启动外部 Node/Codex/PowerShell 的只读检测时，建立受控子进程环境，清理冻结包注入的 DLL/PATH 搜索影响。在 Windows 上将 SetDllDirectoryW 的临时恢复与恢复原值封装成串行启动临界区，避免多个任务交错改变进程级搜索路径；Qt 动态插件先完成加载，实际可行性必须在冻结包验证。只改子进程环境变量不足以保证消除全部影响。[PyInstaller 外部程序说明](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#launching-external-programs-from-the-frozen-application)

---

## 12. 安全、隐私与故障处理

- HTTP 继续只监听 `127.0.0.1`，不得绑定 `0.0.0.0`。
- QNetworkAccessManager 对 loopback 显式禁用代理。
- UI、日志、overlay、安装记录不展示或保存 token 内容。
- 不新增任何提示词、回答、工具参数、错误正文的采集。
- 插件检测只读取版本和固定指纹文件，不读取聊天或 profile 内容。
- 外部脚本修改必须预览、备份、确认、可回滚。
- 不根据端口占用直接杀进程；向用户展示具体冲突和处理建议。
- UI 对服务离线、请求超时、配置保存失败、串口占用、ACK 超时、版本不兼容分别给出可操作提示。
- 任何异常都不能让 UI 把旧状态继续展示为绿色正常；应标记状态未知或刷新失败。

---

## 13. 测试设计

### 13.1 现有回归

每次工作包完成后至少运行：

```powershell
pc/.venv/Scripts/python.exe -m unittest discover -s pc/tests -v
```

DSH 检测工具发生变化时运行：

```powershell
Push-Location plugins/dsh
npm.cmd run build
npm.cmd run check
Pop-Location
```

不要求为本桌面需求运行固件构建；若发现 firmware 或 USB 合约被修改，应停止并复核范围。

仅 CLI 的无 desktop-extra 环境可以明确 skip Qt 测试并报告数量；WP3 及以后桌面验收环境必须安装锁定桌面依赖，Qt 测试缺依赖/被 skip 视为未完成，不能用 CLI 回归全绿代替。

### 13.2 Runtime 与配置测试

- ServiceRuntime 可在非 Qt 测试线程启动和停止，SQLite 创建/访问/关闭线程相同。
- 重复 request_stop 幂等；重复 start 不创建第二线程，终态实例不复用。
- 端口占用和 ProcessLock 冲突能返回结构化错误。
- token 缺失、Store 构造中途失败、runner.setup 失败、site.start 失败、启动中退出及清理函数抛错，均释放已经取得的资源；验证数据库关闭且锁可再次获取，不能只断言返回了错误码。
- 受管任务晚到时仍收尾；超时显示清理中且不释放所有权、不新建 runtime。Qt 主线程在启动/退出期间持续处理事件。
- CLI `serve` 仍调用相同 runtime。
- 配置原子写入失败不损坏旧文件。
- 亮度 bool、越界值和完成保持负数被拒绝。
- 更新显示配置不改变 tokenFile/database/dataDir。
- 自定义 config_path 写入正确文件，缺路径返回 CONFIG_PATH_REQUIRED；默认配置文件完全不变。
- 并发亮度/串口修改不会丢失对方字段；外部 hash 变化返回 CONFIG_CHANGED_EXTERNALLY；客户端断开后已经接受的持久化事务仍完成并能查询最终状态。
- 原子保存 ACL/编码符合约定，替换前失败不发布内存状态；测试开始与保存互斥，拒绝的 PATCH 不落盘。
- 新亮度即使灯态不变也会触发下一次 SET。
- 新完成保持只影响新完成事件。

### 13.3 设备与 API 测试

使用 fake list_ports 和 fake serial，不依赖真实 COM：

- 匹配设备优先、全部串口展开、多个匹配不自动选择。
- auto/manual connect 的请求校验。
- connect 返回 connecting，不提前返回 connected。
- disconnect 禁止自动重连。
- fake open 在取消请求后才返回句柄，验证迟到句柄被关闭；事务中换 COM、重连中退出、扫描超时后退出均无遗留 executor/句柄。
- connection_generation 阻止旧 ACK/STATUS 覆盖新连接，DISCONNECTING → DISABLED 只发生在真正关闭之后。
- 当前代次 SET ACK 后的 STATUS 必须匹配 state/brightness/revision；2.5 秒过期、新命令在途或连接变化立即撤销 confirmed；不以墙钟回拨延长确认。
- 自动模式显式清除旧序列号筛选；手动端口与指定序列号不一致拒绝，队列满和扫描超时不额外创建线程。
- 新 status 保留旧字段并新增 producers/device/display_test。
- 未收到当前进程心跳时 last_heartbeat_at 为空。
- 服务重启后旧 healthy 不直接变成 UI“正在上报”。
- 未鉴权和带 Origin 的新接口仍被拒绝。

### 13.4 三色测试测试

- 未确认设备返回 DEVICE_NOT_READY。
- 并发测试返回 DISPLAY_TEST_RUNNING。
- 顺序严格为红、黄、绿、恢复。
- 每阶段均产生新 revision 和 ACK，包括当前业务状态恰好为红色的情况。
- 无外部事件的隔离测试前后 sessions 快照完全一致，显示 revision 允许变化；并发事件场景与仅应用同一事件序列的对照 Store 比较，不要求 session 停止变化。
- 测试期间新 Agent 事件仍被聚合，恢复使用最新状态。
- 任一阶段 ACK 超时则 failed，并进入正常重连/恢复逻辑。
- UI 只在 succeeded 后显示成功。
- 每色保持从 ACK 后开始计时，保持期间 GET_STATUS 继续；恢复 SET 未 ACK 不得成功，恢复 ACK 等待中新事件必须触发后续同步。
- 测试中保存配置拒绝且不写文件；换端口、断开、退出使用指定错误码并撤销覆盖，重复请求仅一项成功接受。
- 普通轮询可能漏过阶段，stage_results 仍包含所有实际 ACK；测试时 250 ms 轮询且最多一个请求在途。
- CLI test 正常接受保留 HTTP 200/scheduled 和退出码 0；未就绪/重复测试为退出码 3；离线、鉴权和参数错误分别为 1/4/2。

### 13.5 DSH 集成测试

全部在临时目录和 fake QProcess/Node 环境中进行：

- 输出 JSON 可解析，兼容和不兼容结果正确。
- 版本不符和指纹不符均不能安装。
- overlay 使用 file URL，包含正确 endpoint/tokenFile/dataDir，不包含 token。
- dist 缺失时生成失败。
- 支持的 launcher 能幂等添加、更新和移除管理块。
- clean、legacy-unmarked、managed-v1、unsupported 四组 fixture：旧无标记接入迁移后恰好一个插件引用，不重复 insert；混合用户 patch/冲突 overlay 可解释地拒绝。
- UTF-8/UTF-16LE BOM、CRLF/LF、中文/空格/单引号路径正确处理；模板识别失败不修改任何文件。
- 预览后文件被修改返回 INSTALLER_CONCURRENT_CHANGE；pending 记录中断恢复、记录保存失败和并发修改下回滚均不覆盖用户更改。
- 同 config 从 launcher A 改选 B，未解除 A 前不能安装 B/覆盖记录；不同 config 不能接管同一个活动 launcher。卸载预检覆盖所有 pending/committed 索引，旧路径不可达不能被静默忽略。
- 同一目录 a.json/b.json 的草稿、正式 overlay 和安装记录彼此隔离；B 的生成操作不能更改 A launcher 所引用文件；更新已安装配置前只改 draft，确认后才发布正式文件。
- 不支持的 launcher 不被修改。
- 写失败能回滚，原用户内容不丢失。
- 安装结果只进入“待重启”，不制造 producer 健康状态。

### 13.6 Qt UI 测试

可使用 QTest 和 offscreen 平台：

- 状态模型覆盖服务在线/离线、插件未配置/待重启/上报/失联、设备未知/连接中/已确认。
- 旧响应不会覆盖新状态。
- 关闭窗口按设置隐藏或退出。
- 托盘不可用时不会把应用隐藏到无法恢复。
- 第二实例不启动第二个服务。
- 第二实例自定义 --config 不同显示 CONFIG_INSTANCE_CONFLICT，不重写既有配置；IPC 仅允许当前用户与白名单消息。
- --minimized 且托盘缺失自动显示窗口；运行中托盘失效恢复窗口，最后窗口隐藏不触发 QApplication 自动退出。
- 首次状态失败即标记所有旧健康快照过期，第三次才显示服务离线；旧成功响应不能覆盖后来的失败。
- StartupManager 使用 fake 验证开关，不触碰真实注册表。
- 启动命令正确引用 exe/config 的中文和空格路径，保留 --config；源码模式禁用开机启动。

### 13.6.1 来源管理回归

- 旧数据库无 source_admin 行时完全保持既有 enabled 行为；来源普通失联仍 ERROR，clear 不隐藏来源故障。
- fresh lease/服务重启登记窗口内拒绝 disable；确认和 expected_generation 校验，旧管理请求不能覆盖新状态。
- 停用 old、保留健康 new 后，仅 old 及其 sessions 被排除；其他来源错误、身份、waits、deadline、inbox 内容不变。
- 已停用来源的新事件/心跳为 PRODUCER_DISABLED，完全相同的已确认重试仍能幂等确认；被拒绝心跳不续租，UI 显示异常上报提示。
- enable 后 activation_pending 持续贡献 ERROR，旧心跳/旧 ready/不同 runtime 心跳都不能解除；新代次 runtime_ready 加同代次有效心跳才恢复，并遵循既有 FIFO/pending_identity 规则。
- 停用/恢复中断后重启服务，管理状态、generation 与恢复基线不丢失；最新心跳展示不沿用旧进程时间。
- 安装或卸载脚本不会隐式停用来源；采集器重启重放原 outbox 能恢复，不要求删除 quarantine/segment。

### 13.6.2 分发与响应性

- 安装版 GUI/CLI 不依赖源码、当前工作目录或开发虚拟环境，event-schema、版本元数据、Qt 平台/SVG 插件完整。
- 仅复制 index.js 的负例必须报资源缺失；完整目录可 import，inspect-host 与 fake 环境的 Worker 可运行。单纯 import 成功不算 DSH 链路通过。
- 冻结包启动外部 Node 的 DLL/PATH 环境恢复可验证，并发检测不交错修改进程环境；超时仅清理本程序启动的检测子进程。
- 卸载预检发现受管引用时先解除；用户取消/未知修改/记录异常中止删除程序，用户数据保留。自定义 config 索引也覆盖，升级不在运行中覆盖插件。
- 以正常 16 会话和至少 1000 条 outbox 积压进行性能验收，开启 UI 轮询，记录 HTTP 延迟、事件循环延迟和实际设备请求间隔。健康磁盘正常事件请求 p95 <200 ms；有效 USB 请求最大间隔目标 <2 秒，不得达到固件 5 秒链路超时。
- 人为延迟 SQLite 提交（含超过 5 秒的失败场景）时必须显示/记录服务与设备状态失效，恢复后重新 SET/STATUS 确认；不能承诺任意慢磁盘仍保活。若正常基线达不到目标，先优化测得的阻塞路径并复验，不通过加长固件超时掩盖。

### 13.7 实机验收

- 服务在线、插件未配置、灯板断开：三卡状态独立且正确。
- 只生成 overlay：显示配置已生成，不显示插件正在上报。
- 安装后未重启 DSH：显示待重启。
- DSH 正常心跳但 USB 断开：插件正常、灯板未确认。
- 灯板确认但无插件：设备正常、插件未上报。
- 三色实板依次红黄绿，每阶段有 ACK，结束恢复最新业务状态。
- 关闭窗口后真实 DSH 对话仍能控灯。
- 托盘退出后服务停止，灯板按既有固件逻辑进入链路丢失。
- 开机启动只驻留托盘，设置重启后保持。
- 安装包移动到另一台无源码环境后，overlay 插件路径仍有效。
- 从当前无标记旧 launcher 迁移到安装版，只加载一份插件；停用已停止旧来源后灯态不再受其影响，重新启用/重启后新屏障恢复。
- 安装版运行期间不覆盖升级；卸载预检能移除受管外部引用并保留自定义配置、历史数据和备份。

---

## 14. AI 实施工作包

必须按 WP0 → WP1 → WP1a → WP2 → WP3 → WP4 → WP5 → WP6 顺序实施，每个工作包完成定向测试后再进入下一个。WP1a 是提前验证分发风险的最小包，不代表 GUI/安装器已完成。不要一次性重写所有模块。

### WP0：基线确认

- [ ] 阅读本规格、README、USB v1、现有 PC 和 DSH 测试。
- [ ] 运行现有 PC 与插件测试，记录基线失败，不能把历史失败算作新回归。
- [ ] 确认不修改 firmware 和 USB 合约。
- [ ] 将 F1/F2 的启动失败、迟到串口句柄探针转成定向回归，建立 launcher 四组脱敏 fixture。
- [ ] 为 §5.7 显式管理语义建立回归基线，明确允许的 core/FSM 管理扩展范围。
- [ ] 记录 §11.5 候选工具链及精确依赖，runtime-lock 状态为 candidate，不伪报已验证。
- [ ] 建立桌面分支或等价工作边界，不删除用户数据。

完成标准：现有测试基线明确，实施范围无歧义。

### WP1：可嵌入后台与配置

涉及：`runtime.py`、`api.py`、`config.py`、`cli.py`、`pyproject.toml`。

- [ ] 实现 ServiceRuntime，保留 CLI serve。
- [ ] 实现配置校验和原子保存。
- [ ] config_path 显式传递；统一配置/控制操作锁、外部修改检测、取消后的事务收尾。
- [ ] 重构 application 资源创建顺序、部分启动失败清理；Qt 非阻塞停止入口与受管 executor 收尾协议就位。
- [ ] 增加 health 的 desktop_api/service_version。
- [ ] 增加 GET/PATCH display config。
- [ ] 亮度更新强制后续 SET 生效，保持时间按约定生效。
- [ ] 添加 runtime/config/API 测试。
- [ ] 实现 §6.10 的 CLI 错误分类，保留 event 安静行为。

完成标准：现有 CLI 和全部 PC 测试通过，后台可以在独立线程启动/停止。

### WP1a：最小 onedir 分发验证

涉及：`packaging/windows/AgentLight.spec`、`runtime-lock.json`、最小 Qt 测试入口、`desktop/resources.py`、`inspect-host.mjs`。

- [ ] 锁定并安装候选依赖，在无源码目录运行最小 Qt 窗口和 console CLI。
- [ ] 提前实现只读 inspect-host 与完整插件资源清单，验证 import、检测输出、fake 环境 Worker 和 schema/元数据。
- [ ] 验证外部 Node 环境隔离、中文/空格路径和丢失间接资源的负例。
- [ ] 实测通过才将 runtime-lock 标为 verified，记录 OS/架构/完整版本；最小 Qt 入口仅作验证，不计入 WP3 的界面完成项。

完成标准：发布依赖组合和资源路径有实际证据；不等待 WP6 才发现安装环境无法加载插件。WP5 复用此检测器，避免另一套实现。

### WP2：设备控制、状态快照与三色测试

涉及：`devices.py`、`serial_link.py`、`api.py`、必要的 `core.py` 展示辅助数据。

- [ ] 实现扫描与标准化 DeviceInfo。
- [ ] 实现 connect/disconnect 和运行时端口选择。
- [ ] 串口单 executor、connection_generation、在途 I/O 收尾、DISCONNECTING 和扫描任务生命周期。
- [ ] 扩展 device 状态与 GET_STATUS 快照。
- [ ] 增加 producers 数组和当前进程心跳时间。
- [ ] 实现 §5.7 source_admin、来源管理 API 和数据库增量迁移，同步更新 FSM 的受限管理语义。
- [ ] 将三色测试改为逐色 ACK 状态机。
- [ ] 保留旧 status 字段和 CLI test 调用。
- [ ] 添加 fake serial/API/测试状态机回归。

完成标准：无需真实硬件即可验证全部状态转换，现有协议向量测试保持通过。

### WP3：桌面壳、状态页与设备页

涉及：`desktop/app.py`、`client.py`、`models.py`、`main_window.py`、状态/设备页面。

- [ ] 创建 QApplication、单实例和 ServiceRuntime 生命周期。
- [ ] 实现异步本地 API client 和轮询。
- [ ] 实现四区状态总览和 producer 明细。
- [ ] 来源停用/重新启用确认流程、恢复中/停用状态；单次刷新失败即标记快照过期。
- [ ] 实现设备扫描、选择、连接、断开。
- [ ] 实现三色测试进度和结果。
- [ ] 使用 250 ms 有界轮询与 stage_results；恢复成功和配置/设备操作冲突按协议处理。
- [ ] 添加状态模型、API fake 和 QTest 测试。

完成标准：窗口所有操作不阻塞，三类状态不混淆，CLI 无需被桌面替代。

### WP4：托盘、设置和开机启动

涉及：`tray.py`、`startup.py`、设置页面、`app.py`。

- [ ] 实现关闭驻留、托盘菜单和完整退出。
- [ ] 实现亮度与完成保持设置。
- [ ] 实现 QSettings 桌面偏好。
- [ ] 实现当前用户开机启动抽象。
- [ ] 实现 --minimized 和第二实例激活。
- [ ] 无托盘启动/运行中托盘丢失回退，跨 config 实例冲突，开机启动完整引用 --config。
- [ ] 添加 fake startup、托盘和关闭行为测试。

完成标准：关闭窗口不影响链路，退出能完整清理，开机启动和设置持久化可验证。

### WP5：DSH 检测与配置接入

涉及：`integrations/dsh.py`、`resources.py`、插件页、`inspect-host.mjs`、共享 overlay 生成器。

- [ ] 实现 DSH/Node/launcher 动态发现。
- [ ] 复用 WP1a 的只读 JSON 宿主检测，完成 UI 连接和错误映射，不放宽 verifyHost。
- [ ] 实现 overlay 生成和配置目录。
- [ ] 实现受支持 launcher 的预览、备份、幂等安装、卸载和回滚。
- [ ] 实现无标记旧接入迁移、pending 安装记录、文件并发修改保护、overlay 冲突检测与自定义配置索引。
- [ ] 不兼容或不支持环境只给手工方案，不修改宿主。
- [ ] Codex 显示真实预留状态。
- [ ] 添加临时目录和 fake 进程测试。

完成标准：配置状态与运行状态完全分离，不自动杀进程，不放宽门禁，不包含 token。

### WP6：安装包、文档和最终验收

涉及：`packaging/windows/`、`pyproject.toml`、README、第三方声明。

- [ ] 完成 onedir 打包和稳定资源路径。
- [ ] 完成每用户安装器，保留用户数据。
- [ ] 安装版 console CLI、维护入口、卸载前受管引用解除与覆盖升级前退出检查。
- [ ] 验证安装环境的 DSH file URL 和桌面入口。
- [ ] 更新桌面使用、排障、卸载和 CLI 兼容说明。
- [ ] 更新实际分发依赖许可。
- [ ] 执行全部自动化测试和实机验收矩阵。

完成标准：在无源码、无开发虚拟环境的 Windows 用户目录中可运行，现有数据和插件路径有效。

---

## 15. 最终验收矩阵

| 场景 | 服务 | 插件 | 灯板 | 必须观察到的结果 |
|---|---|---|---|---|
| 仅启动桌面程序，无灯板无 DSH | 在线 | 未上报 | 未确认/重连中 | 不出现虚假绿色正常 |
| 只生成 DSH overlay | 在线 | 配置已生成 | 独立判断 | 不显示正在上报 |
| 安装 overlay 但未重启 DSH | 在线 | 已安装待重启 | 独立判断 | 明确提示重启 |
| DSH 心跳正常，USB 断开 | 在线 | 正在上报 | 未确认 | 插件与设备状态分离 |
| USB 已确认，无 DSH | 在线 | 未上报 | 已确认 | 不误报插件正常 |
| 服务停止 | 离线 | 未知 | 未知 | 不沿用旧绿色状态 |
| 三色测试 | 在线 | 独立判断 | 逐色 ACK | 红黄绿、恢复最新业务灯态 |
| 测试中断开 USB | 在线 | 独立判断 | 重连中 | 测试 failed，恢复机制正常 |
| 关闭窗口驻留 | 在线 | 保持实际上报 | 保持实际确认 | 后台继续工作 |
| 托盘退出 | 已停止 | 随后失联由运行方决定 | 固件链路丢失逻辑 | 无残留锁和串口占用 |
| DSH 版本不兼容 | 在线 | 不兼容 | 独立判断 | 禁止安装，不绕过门禁 |
| 服务锁冲突/启动失败 | 未启动/失败 | 未知 | 未知 | 清理已取得资源，UI 可响应，无遗留 SQLite 连接 |
| 连接中断开/切换端口 | 在线 | 独立判断 | 断开中/连接中 | 旧代次结果无效，迟到句柄被关闭 |
| 旧来源失联且新来源正常 | 在线 | 异常 | 可已确认 ERROR | 不自动隐藏旧来源故障 |
| 显式停用已停止旧来源 | 在线 | 已停用，其他源独立 | 最新聚合 | 排除旧源及其 sessions，保留历史 |
| 重新启用旧来源 | 在线 | 恢复中 | ERROR/最新聚合 | 新 runtime 屏障和同代心跳后才恢复正常 |
| 旧 launcher 迁移 | 在线 | 待重启 | 独立判断 | 只有一份插件接入，外部用户内容保留 |
| 测试期间保存亮度 | 在线 | 独立判断 | 测试继续 | DISPLAY_TEST_RUNNING，不写配置 |
| 程序卸载遇到未知脚本变更 | 预检模式 | 接入未解除 | 不操作 | 中止删除，保留资源和数据，给出手工路径 |
| Codex 已安装命令 | 在线 | 适配器未实现 | 独立判断 | 不提供虚假接入成功 |

---

## 16. 后续可选扩展

以下不属于首版完成条件：

- UI 与后台拆成两个进程，UI 崩溃不影响服务。
- Windows Service 或系统级常驻。
- Codex 真实适配器。
- 自动更新、代码签名和公开发布流程。
- 多灯板分别绑定不同 Agent。
- 自定义灯效和颜色映射。
- 光学闭环测试；这需要额外硬件，不是单纯固件修改。
- 固件持久化亮度或专用测试命令；当前需求不需要。

---

## 17. 实施完成定义

只有同时满足以下条件，桌面化改造才算完成：

1. WP0–WP6（含 WP1a）的必选项完成，相关自动化测试通过。
2. CLI 命令/成功输出、事件 schema、USB 协议和 DSH 门禁保持兼容；§6.10 的错误分类升级已记录并验证，来源管理只改变显式操作过的来源。
3. 真实 DSH 链路仍能完成运行黄灯、完成绿灯。
4. 真实灯板三色测试逐色 ACK，恢复最新状态，不改会话。
5. 关闭驻留、托盘退出、开机启动和设置持久化通过 Windows 实机验证。
6. 配置成功、插件加载、插件上报、设备确认在 UI 和日志中均有明确边界。
7. Codex 未被误标为已支持。
8. 安装版不依赖源码目录、开发机绝对路径或本机虚拟环境。
9. F1–F8 对应验收均有证据：启动失败无资源遗漏、串口迟到结果收尾、完整分发、旧接入迁移、来源管理、CLI 错误、测试仲裁及配置一致性。
10. runtime-lock 记录实际验证组合；更新和卸载不会遗留已登记的损坏外部插件引用，正常负载响应性达标。

---

## 18. 审查问题闭环索引

本表用于实施追踪，只表示设计已给出规则，不代表实现验收已完成。

| 问题 | 修订位置 | 实施工作包 | 验收位置 |
|---|---|---|---|
| F1 启动失败清理/SQLite 线程归属 | §3.4、§5.1 | WP1 | §13.2 |
| F2 在途串口 I/O 和迟到结果 | §3.3、§5.4、§5.5 | WP1/WP2 | §13.2、§13.3 |
| F3 插件完整资源/安装版 CLI | §6.10、§11.1–§11.5 | WP1a/WP6 | §13.6.2 |
| F4 旧 launcher 迁移 | §8.4.1、§8.5 | WP0/WP5 | §13.5、§13.7 |
| F5 旧来源故障与停用 | §5.7、§6.11、§7.2 | WP2/WP3 | §13.6.1 |
| F6 CLI test 兼容与错误分类 | §0、§6.9、§6.10 | WP1/WP2 | §13.4 |
| F7 测试时序/恢复/进度 | §5.6、§6.7、§7.6 | WP2/WP3 | §13.4 |
| F8 配置路径/并发/确认时效 | §5.2、§5.5、§6.6、§7.6 | WP1/WP2/WP3 | §13.2、§13.3、§13.6 |
| 其他：单实例/启动项/卸载/工具链/性能 | §10、§11、§13.6.2 | WP1a/WP4/WP6 | §13.6、§13.6.2、§13.7 |
