# 上位机 GUI 详细设计可行性审查

审查日期：2026-11-08。对象：[桌面开发规格](D:/projects/agent-light/docs/superpowers/specs/2026-11-08-desktop-ui-development-spec.md)。

结论：**技术路线可行，可以保留整体架构；当前规格需补齐关键生命周期、迁移和分发约定，再作为直接实施基线。** 主要难点在 ServiceRuntime、SerialWorker 和 DSH 安装接入，四个 Qt 页面本身风险较低。没有发现必须修改固件或 USB v1 才能实现首版需求的障碍。

本次完整阅读了 1135 行规格，并交叉核对 PC 实现、测试、USB/FSM 合约、DSH 插件、此前设计和联调记录；只读核对了当前本机 dsh-web 包装脚本。未实施 GUI，未修改原规格、业务源码、真实配置、启动脚本或固件，未操作实物串口。

## 1. 可以保留的设计

| 设计 | 判断与条件 |
|---|---|
| Qt 主线程 + asyncio 服务线程 | 可行。QNetworkAccessManager 提供异步 API，需在所属 Qt 线程使用；AppRunner/TCPSite 适合自行管理服务生命周期。无需为此引入第三套事件循环桥接。 |
| UI 经本机 HTTP 访问后端 | 可行，能保持 UI、SQLite、串口和状态机边界。新增接口仍须复用鉴权与校验。 |
| 不修改 USB v1 | 可行。GET_STATUS 已有 mode、灯态、revision、亮度、固件版本、运行时间和 CRC 计数；三色测试可由普通 SET_STATE 实现。 |
| 保留业务状态机，测试仅覆盖显示 | 可行。但显示事务、revision 分配、测试退出与恢复必须由一个串口执行者协调。 |
| 托盘与后台同进程 | 适合首版；GUI 崩溃会使服务停止是规格已接受的限制。 |
| onedir + 稳定插件路径 | 合理，但需要完整资源清单、安装版 CLI 策略和升级/卸载处理。 |
| DSH 锁定版本，Codex 仅预留 | 与现有实现一致，避免把环境发现误报为事件链路可用。 |

官方依据：[Qt 异步网络与线程约束](https://doc.qt.io/qtforpython-6/PySide6/QtNetwork/QNetworkAccessManager.html)、[aiohttp 应用运行器](https://docs.aiohttp.org/en/stable/web_advanced.html#application-runners)、[PyInstaller 资源路径](https://www.pyinstaller.org/en/stable/runtime-information.html)。USB 判断依据为本仓库 [USB v1](D:/projects/agent-light/contracts/usb-protocol-v1.md:26)。

## 2. 开发前必须补齐的高优先级问题

### F1：启动失败的资源清理不能沿用当前实现

**位置：**规格 §3.4、§5.1；[api.py](D:/projects/agent-light/pc/agent_light/api.py:14)。

目前 application(cfg) 先创建 Store/SQLite，再读取 token；ProcessLock 到 cleanup context 启动时才获取。锁失败发生在 yield 之前，现有关闭数据库代码不会执行。规格写“继续由 cleanup context 管理”容易掩盖这一现有缺口。

临时目录探针模拟 ProcessLock 冲突，执行 runner.setup() 失败和 runner.cleanup() 后，原数据库连接仍可执行 SELECT，确认没有被关闭。aiohttp 明确说明只有对应启动成功，才执行其正常 cleanup 段，不能依赖它清理启动过程中遗漏的资源。[官方清理语义](https://docs.aiohttp.org/en/stable/web_advanced.html#cleanup-context)

**建议补充：**ServiceRuntime 构造函数只持有配置；在服务线程中创建 application 和 SQLite，先取得服务锁，再创建受保护资源；每一层部分初始化失败都必须逆序释放。TCPSite 绑定失败也必须完整清理。退出需要先停止接收新请求并处理在途 handler，再关闭数据库。Qt 线程用异步完成通知展示启动/退出过程，不能直接阻塞 join。

**新增验收：**锁冲突、token 缺失、数据库初始化失败、端口绑定失败、启动中退出、重复 start/stop 后，均无遗留连接/线程/锁；GUI 始终可响应。

### F2：取消 asyncio 任务不等于串口工作线程已经停止

**位置：**规格 §3.3、§3.4、§5.4；[serial_link.py](D:/projects/agent-light/pc/agent_light/serial_link.py:69)。

当前 open() 在 to_thread 中直接修改 self.port；transaction() 也直接使用该共享端口并修改 seq。若 open 还未完成就取消 run，finally 可能看到 port=None，随后工作线程继续打开端口，留下未关闭的句柄。切换 COM 时，同一类晚到结果还可能覆盖新连接。

使用 fake open 和线程事件控制时序，实测结果为：worker task 已结束，但随后 port 被创建，且未关闭。这不涉及实物串口。Python 的 executor 也不支持取消已经运行的调用。[官方 Future.cancel 语义](https://docs.python.org/3/library/concurrent.futures.html#concurrent.futures.Future.cancel)

**建议补充：**由串口命令队列统一处理连接、断开、测试及普通 SET；定义停止请求、在途 I/O 收尾、关闭句柄的顺序；open 返回句柄由服务线程接管，过期结果必须主动关闭。用连接代次隔离旧操作，切换端口/重连时清空旧 ACK、STATUS 和 confirmed。明确 executor 收尾与超时策略，而非仅 task.cancel()。

**新增验收：**扫描中退出、打开中断开、SET 中换端口、重连退避中退出、旧连接结果晚到，均不泄漏句柄、不产生两个并行 USB 事务、不恢复错误的 confirmed。

### F3：安装包资源清单不足以支撑 DSH 加载

**位置：**规格 §8.2、§11.2；[index.ts](D:/projects/agent-light/plugins/dsh/src/index.ts:5)、[reporter.ts](D:/projects/agent-light/plugins/dsh/src/reporter.ts:14)。

安装树只列了 resources/plugins/dsh/dist/index.js，但 index.js 还导入 reporter.js、adapter-0.2.1-rc.2.js、host-lock.js，Reporter 再启动 worker.js。新增 inspect-host.mjs 也需要随安装包分发。

临时目录中仅复制 index.js 和 package.json，实际 Node import 返回 ERR_MODULE_NOT_FOUND，缺失 reporter.js；复制完整 dist 后 import 成功。后者只证明模块可导入，不等同于宿主门禁、Worker 或真实 DSH 链路通过。

**建议补充：**即使原目录树只是示意，也应增加强制清单：完整 dist、保留 type=module 的 package.json、inspect-host.mjs、Python event-schema、Qt 必需插件/图标和版本元数据。检测插件完整性不能只检查 index.js 是否存在。明确安装版是否提供独立 CLI 可执行入口；保留 pyproject 中的脚本声明本身不能证明安装包具有 CLI。

**新增验收：**无源码目录下导入插件、运行宿主检测、启动 Worker；缺任意必要资源有明确错误；带空格及中文的路径可用。冻结程序调用外部 Node 时，还需检查继承的 DLL 搜索路径，不能假定开发环境的 QProcess 测试覆盖安装环境。[PyInstaller 外部程序注意事项](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#launching-external-programs-from-the-frozen-application)

### F4：当前已接入的 DSH 包装脚本缺少迁移路径

**位置：**规格 §8.4、§8.5；只读检查的 [现有包装脚本](D:/deepseek/bin/dsh-web.ps1:4)。

方案要求只添加/更新/删除明确 BEGIN/END 管理块，但现有脚本第 4–30 行已经自动注入旧 overlay，且没有这种成对标记。旧脚本按 overlay 文件路径去重，新桌面默认输出另一个路径，所以仅增加管理块可能把两个 overlay 都带给 DSH。现有两个 overlay 若都 insert 同一个插件节点，会造成重复接入或冲突；具体宿主结果本次未启动验证。

**建议补充：**提供去除本机路径后的受支持 launcher fixture、管理块格式、插入锚点、检测及迁移算法。对已知旧集成，在备份和用户确认后迁移为一个管理块；无法识别的旧接入应明确拒绝自动修改并给出迁移说明。不能仅凭“有参数数组和 DSH 调用”就认定可安全修改。

**新增验收：**干净脚本、现有无标记旧脚本、已有新管理块、用户附加 patch、重复安装、路径变更与卸载后均只保留预期接入；同时核查预览后至写入前脚本是否发生变化。

## 3. 需要明确的行为与接口问题

### F5：旧 producer 的停用和卸载后状态没有闭环

**位置：**规格 §7.2、§8.5；[core.py](D:/projects/agent-light/pc/agent_light/core.py:150)。优先级：中高。

所有已登记 sources 都长期保存在数据库中，任何一个租约过期都会贡献 ERROR；clear() 只清会话中的 ERROR/COMPLETED，不移除来源故障。runtime_ready 只处理同一 producer 的交接，不能替换另一个 producer。

探针建立 old/new 两个 producer，使 old 过期、new 保持健康：clear 前后 desired 均为 ERROR。正常重启若沿用同一 outbox/producer，不会触发“新旧 producer 并存”问题；但主动卸载后旧来源失联、改变 dataDir 或来源迁移都会暴露该边界。这是继承的核心行为，不是 GUI 已实现的新缺陷。

**建议补充：**定义“已登记活跃 producer”的准确范围，以及主动卸载后仍持续报错的产品预期。首版若坚持不改 core，须明确这是限制并约束迁移保留 producer 身份；若要求永久停用来源后恢复正常，需要单独设计显式注销/停用语义、回归测试和操作入口。UI 仅隐藏旧 producer 无法改变真实灯态。

### F6：新增测试失败语义与“保留 CLI 行为”存在冲突

**位置：**规格 §0 第 4 项、§5.6；[cli.py](D:/projects/agent-light/pc/agent_light/cli.py:45)。优先级：中。

旧 test 接口无设备也返回 scheduled；新规则要求未确认设备返回 409 DEVICE_NOT_READY，重复测试返回 409 DISPLAY_TEST_RUNNING。现有 CLI 将所有 HTTP 异常统一输出 SERVICE_UNAVAILABLE，因此桌面改造后，服务明明在线，CLI 却可能报告服务不可用。

**建议补充：**明确保留的是命令形式/路由，还是完整退出码与响应语义。若接受收紧就绪条件，记录兼容性变化，并让 CLI 识别新错误码。为 POST test 固定成功状态码、响应体和 test_id，旧客户端使用的 scheduled 字段是否保留也需明文规定。

**新增验收：**服务离线、设备未就绪、测试已运行和测试接受成功，CLI 输出及退出码可区分。

### F7：三色测试的控制交互和 UI 进度不足以确定实现

**位置：**规格 §5.6、§7.6、§13.4。优先级：中。

每阶段约 1 秒，普通轮询却为 2 秒/5 秒，无法保证 UI 看见红、黄、绿各阶段。还没有明确测试期间保存亮度、切换端口、主动断开、服务退出的处理，以及 ACK 到达后才开始保持还是发送时开始保持。恢复阶段也需明确以恢复 SET 的 ACK 作为成功条件。

**建议补充：**测试运行时临时加快轮询，例如 200–250 ms，或返回阶段记录；禁止伪造未确认的进度。每色的保持时间从匹配 ACK 后计算；连接变化令测试失败并退出覆盖模式；对亮度修改选择拒绝或排队并写入规格。恢复读取当时最新聚合状态，收到恢复 ACK 后再 succeeded；若恢复等待期间出现新业务事件，保证随后正常同步且不会被测试清理覆盖。

§13.4 的“测试前后 sessions 完全一致”仅适用于无外部事件的隔离场景。存在并发 Agent 事件时，应验证测试流程没有额外修改 session，而不是要求 session 不变化。

### F8：配置写入路径、并发与确认时效仍缺少合约

**位置：**规格 §5.1、§5.2、§5.5、§6.3、§6.6、§7.6。优先级：中。

ServiceRuntime(cfg) 和 application(cfg) 只接收配置内容，但保存接口需要 cfg_path。使用 --config 时不能反推默认文件。配置原子替换只能避免半文件，不能避免亮度 PATCH 与串口 connect 同时读旧值后相互覆盖。

**建议补充：**将解析后的 config_path 显式传入 Runtime 或配置存储对象；显示和串口修改统一经串行写入器处理，保存成功后发布内存状态，失败不改变现有状态。把 configuration_saved、backend_applied 和 device_confirmed 分开，说明 PATCH 返回 applied 只指后台配置。

设备确认还需给定具体新鲜度阈值，用单调时钟判断；UTC 字符串仅用于展示。GET_STATUS 应匹配当前连接代次和最近发送的 revision，必要时核对 state/brightness。首次刷新失败立即将旧绿色标记为“过期/未知”，第三次失败才将服务标签改为“离线”，以协调 §7.6 与 §12。

## 4. 其他值得补充的验收边界

- 单实例锁/IPC 按用户还是按用户加 config 隔离，第二实例携带不同 --config 时如何处理，需要明确；启动项必须正确引用路径，并保留用户选用的配置。
- 托盘驻留需设置正确的 QApplication 退出策略。--minimized 启动时托盘不可用，也要显示窗口，不能只覆盖“关闭窗口时”的分支。
- 安装器卸载程序后，外部 dsh-web 脚本可能仍引用已删除的插件。需要先引导解除接入或采用已记录且可校验的清理方式；“保留用户数据”不足以覆盖这一问题。
- 锁定一组实际支持的 Windows、Python、PySide6、PyInstaller 版本及开发测试依赖。当前环境为 Python 3.14.0，未安装 PySide6/PyInstaller；“Python 3.11+”尚不是经过验证的打包矩阵。
- 同步 SQLite 持久化目前位于服务事件循环。暂不要求改成另一线程，但应测量 outbox 重放、磁盘慢及状态轮询时的心跳/HTTP 延迟，确保没有跨过固件 5 秒保活窗口。

## 5. 本次验证证据与限制

| 检查 | 结果 | 证明范围 |
|---|---|---|
| `pc/.venv/Scripts/python.exe -m unittest discover -s pc/tests -v` | 5/5 通过 | 现有核心、HTTP、协议向量回归 |
| `npm.cmd run check`，目录 plugins/dsh | 7/7 通过 | 现有 adapter、outbox、Reporter 回归，使用当前已有 dist |
| `node_modules/.bin/tsc.cmd --noEmit`，目录 plugins/dsh | 退出码 0 | 当前 TypeScript 源码类型检查；未重新构建发布产物 |
| fake open 取消时序探针 | task_done=true；随后出现 port；port_closed=false | 确认在途线程资源收尾缺口 |
| ProcessLock 启动失败探针 | cleanup 后数据库仍能 SELECT | 确认部分启动失败未关闭数据库 |
| 旧 producer 过期探针 | clear 前后均 ERROR | 确认旧来源故障无法由现有 clear 解除 |
| 临时安装目录插件导入 | index-only 失败；完整 dist 导入成功 | 确认分发依赖清单不能只列入口 |
| 本机包装脚本只读核对 | 已有旧 overlay 注入，无成对管理标记 | 确认首批迁移场景客观存在 |

运行环境：Python 3.14.0、aiohttp 3.14.5、pyserial 3.5、jsonschema 4.26.0；本次测试使用 PATH 中的 Node 22.12.0。没有以此替代 DSH 实际选择的 Node 运行时验证。

所有定向探针只使用临时目录、合成状态及 fake 串口，不读取真实 token、聊天、数据库或 outbox。本次未运行 GUI/托盘/启动项/安装器验证，未运行真实 DSH 加载和实板三色测试。现有 5 项 PC 测试不包含 SerialWorker 的完整生命周期测试，不能据此判定桌面改造风险已经覆盖。

## 6. 实施建议

保留 WP0–WP6 分层，但在进入各包前增加以下门槛：

1. **WP0/WP1：**先补充 F1/F2 的生命周期约定和定向回归，明确 config_path 与 CLI 兼容性。
2. **WP2：**固定连接代次、confirmed 新鲜度、测试仲裁与恢复 ACK 规则；明确旧 producer 的首版边界。
3. **WP3/WP4：**按既定 Qt Widgets 架构开发，覆盖异步启动/退出、阶段进度与无托盘场景。
4. **WP5：**以实际 launcher fixture 验证新装、旧集成迁移、重复安装和卸载，不能只测全新管理块。
5. **提前做一次最小 onedir 验证：**测试 Qt 壳、资源定位、外部 Node 检测和完整插件导入，再继续完善 WP5/WP6，避免最后才发现分发问题。

这一规格适合作为修订基础。完成上述补充后，可以按原有架构逐包实施，无需推翻方案或扩大到固件改造。
