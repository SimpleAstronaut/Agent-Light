# PC / DSH v0.1 实施记录

日期：2026-11-06。依据最新 DSH 专项设计与 USB v1 合约实施。按用户要求采用单执行者，省略重复审批、独立审查、大规模测试与性能/故障注入验收。

交付：

- `pc/agent_light`：本地认证 HTTP、严格 schema、SQLite inbox/FSM/display 事务、多来源聚合、来源租约、精确等待集合、完成保持、串口发现/ACK/重试/重连/revision 对账、CLI。
- `plugins/dsh`：TypeScript ESM 插件、宿主版本/指纹门禁、顶层生命周期、审批/两类提问、非阻塞有界上报、持久 segment/checkpoint、恢复重放和诊断。
- `contracts`：事件 schema、FSM 说明、来源能力 schema、DSH 指纹与 unverified 能力声明。
- `outputs/packages/agent_light-0.1.0-py3-none-any.whl`、`agent-light-dsh-0.1.0.tgz`：可安装构建产物。运行说明见 `pc/README.md`、`plugins/dsh/README.md`。

本轮证据：

- Python 5 项检查通过：等待跨取消/回合保留、精确 resolve、去重与冲突、完成期限、错误终态、来源隔离/交接、内容拒绝、USB 黄金向量、HTTP 鉴权及事务应答。
- TypeScript 编译成功；Node 4 项检查通过：生命周期/子 Agent、legacy 返回值与异常原样传播、timed 超时清理不误解等待、Worker 离线重放与畸形 ACK 不推进 checkpoint。
- 本机 DSH 指纹通过；真实 Cordis Context 验证 global 监听与 prepend 包装先于合成 answerer。
- 独立临时目录中的软件集成通过：真实 Cordis 观察器 → 真实 Worker/outbox → 真实 PC HTTP/SQLite，显示 RUNNING → ATTENTION → COMPLETED。测试结束关闭临时进程，无更改真实 DSH profile。
- 串口枚举仅 COM3/COM4，均不匹配配置 VID/PID；本轮未做实板通信，不覆盖用户此前的通信测试结论。

边界：真实 Web 装载和内置 answerer 顺序、PTC 所有结局、断电/磁盘满/每个 fsync 点强杀、16/32 路性能、30 回合实板 E2E 仍未验收；不得将 v0.1 宣称为完整硬件验收通过。真实 Codex 插件、GUI/托盘/自启/发布安装器按专项设计另期处理。预留 Codex 的统一协议与来源隔离已实现。

运行时默认 35% 亮度、完成 300 秒、loopback 17321。配置初始化收紧用户目录 ACL；DSH overlay 引用同一绝对 tokenFile/dataDir。没有初始化真实用户配置、输出 token 或自动启用插件。
