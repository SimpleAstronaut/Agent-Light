# Agent 三色状态指示灯详细执行方案

> 版本：v1.0  
> 日期：2026-10-26  
> 适用文档：`outputs/agent-indicator-design.md`  
> 执行方式：主 Agent 编排 + 专业 subagent 并行实施 + 阶段门禁  
> 首要目标：先完成 Windows 可用原型，再进行定制 PCB、发布和可选量产  
> 本方案优先级：当本文与原总体设计冲突时，以本文冻结的接口和状态语义为准

---

## 0. 如何使用本文

本文不是概念说明，而是后续 Agent 的工作分解和验收基线。主 Agent 应按以下方式执行：

1. 先完成 WP00 环境核验，再创建 WP01～WP42 任务。
2. 每个工作包使用独立 subagent；只把该工作包所需接口和目录交给它。
3. 合约、协议、状态机由集成负责人统一修改，其他 subagent 不得各自变更。
4. 每个 subagent 必须交付代码/文件、测试结果、已知限制和接口偏差，不能只回复“已完成”。
5. 未完成阶段准入条件时，不得跳过门禁；确需跳过必须记录原因、影响和回退方法。
6. Cube、Keil、嘉立创 EDA 的 GUI 操作，以及焊接、测量、插拔等实物操作，必须明确交给用户执行，Agent 不得虚报完成。
7. 每完成一个工作包，在对应复选框中记录完成日期、提交/构建号和测试报告路径。

### 0.1 首版交付定义

首版可用原型必须同时具备：

- STM32F042 开发板或定制板通过 USB CDC ACM 与 PC 通信。
- 红、黄、绿三灯正确显示五种 Agent 状态及链路异常。
- Python 常驻服务、CLI、事件持久化、失败补报和设备自动重连可用。
- Codex/DSH 至少一个真实适配器通过锁定版本合约测试；另一个不得在未核验时宣称支持。
- 服务重启、设备复位、ACK 丢失和事件补报后，最终灯态仍能自动对齐。
- 插件/Hook 不改变 Agent 的工具决策、错误传播、输出和退出码。
- 日志、数据库、spool 和 USB 帧不包含提示词、代码、工具参数、回答或错误正文。

---

## 1. 范围、优先级与非目标

### 1.1 P0：Windows 原型必须完成

- 单设备、单 Python 服务、单 CLI。
- 五种 Agent 状态：`IDLE/RUNNING/ATTENTION/ERROR/COMPLETED`。
- 一种链路状态：`LINK_LOST`，不得写入 Agent 会话状态。
- PC 统一管理多会话、完成保持、亮度、手动测试和状态清除。
- STM32 固件只管理显示、协议和链路看门狗。
- Python 测试、协议模拟器、真实设备 HIL 测试；仅在选择 DSH 时强制 Node 构建和测试。
- Windows 用户级运行、路径含空格、非交互 PATH 场景可用。

### 1.2 P1：发布前完成

- Windows 托盘、登录启动、安装/升级/卸载。
- DSH web/headless 等实际 profile 支持矩阵。
- 定制 PCB、外壳、光学、电气和 72 小时发布候选长稳。
- 合法 VID/PID、固件/安装包哈希、兼容矩阵和回滚方案。

### 1.3 P2：后续可选

- macOS/Linux 完整打包和平台权限适配。
- USB DFU、多设备、多工作区筛选、Web 控制台。
- 量产工装、EMC/ESD 认证、PVT 和批量追溯。

### 1.4 首版明确不做

- 不让灯具直接访问模型 API。
- 不用 OCR 或终端关键词判断错误。
- 不把工具非零退出直接当成 Agent 全局错误。
- 不让 USB 设备反向批准、拒绝或修改 Agent 操作。
- 不在固件保存 Agent 会话、回合、完成截止时间或业务状态。

---

## 2. 当前环境与工具边界

### 2.1 已探测环境

| 工具 | 当前结果 | 执行基线 |
|---|---|---|
| Python | `python` = 3.13.14；`py` = 3.14.0 | 首版固定 Python 3.13，避免多版本混用 |
| Node.js | v22.22.2 | DSH 插件使用 Node 22 |
| npm | 10.9.7 | 使用 lockfile 和 `npm ci` |
| Git | 2.55.0.windows.3 | 每阶段形成可回退提交 |
| Codex | 当前 PATH 未找到 | 安装或提供真实路径后才能执行 Codex 合约 |
| DSH | 当前 PATH 未找到 | 安装或提供真实路径后才能执行 DSH 合约 |
| Keil | 用户已安装 | 首次构建前记录 MDK、编译器、Device Family Pack 版本 |
| STM32Cube | 用户已安装 | 记录 CubeMX 和 STM32CubeF0 包版本 |
| 嘉立创 EDA | 用户已安装 | 记录专业版/标准版及版本；不假定存在可自动化的 CLI |

### 2.2 环境核验命令

Git Bash：

```bash
python --version
py --version
node --version
npm --version
git --version
command -v codex
command -v dsh
```

PowerShell 中定位真实程序：

```powershell
Get-Command python, node, npm, git -ErrorAction Stop
Get-Command codex -ErrorAction Stop
Get-Command dsh -ErrorAction Stop
```

`codex` 或 `dsh` 不存在时，门禁结果为“未满足”，不得使用猜测路径或虚构版本继续适配器实施。

### 2.3 GUI 和实物操作边界

| 类型 | Agent 可以做 | 用户必须做或确认 |
|---|---|---|
| STM32Cube | 给出精确料号、外设、时钟和配置清单；检查生成文件 | 在已安装版本中创建/确认工程，处理版本相关界面 |
| Keil | 检查工程、源码、map 和构建日志；修复代码 | 首次 Device Pack、调试器、Flash 算法和下载配置 |
| 嘉立创 EDA | 生成选型计算、BOM、审查清单；审查导出文件 | 原理图/PCB 的实际 GUI 绘制、DRC 确认和下单 |
| 实物 | 给出分级上电和测量步骤；分析日志/照片/波形 | 焊接、插拔、限流供电、万用表/示波器测量 |
| Agent 安装 | 生成适配器和安装配置 | 安装 Codex/DSH、确认 Hook 信任及必要授权 |

---

## 3. 必须冻结的架构决策

### 3.1 单一状态权威

- **PC 服务是 Agent 状态、会话聚合、完成保持、亮度和手动显示覆盖的唯一权威。**
- 固件只执行最近一次合法 `SET_STATE`，不运行完成保持计时，不判断 stale，不理解 Agent。
- 插件、CLI、wrapper 不得直接打开 COM 口。
- 全机只允许一个 PC 服务实例和一个串口写入者。

### 3.2 完成保持

- `completed_hold_seconds` 只存在于 PC 配置。
- PC 为每个完成回合保存 `completion_deadline`。
- 到期后 PC 生成新的目标 `IDLE` 和新的 `display_revision`。
- 固件收到 `COMPLETED` 后一直保持绿色，直到收到新状态、链路丢失或断电。
- 首版默认 300 秒；`0` 明确定义为“不过期”，正整数单位为秒，最大 86400。

### 3.3 等待状态

- `ATTENTION` 使用独立 `attention_id`，不是可被普通活动覆盖的标志位。
- 只有相同实例、相同回合、相同 `attention_id` 的 `attention_resolve` 才能正常解除。
- `activity`、工具执行、assistant stream、Subagent 活动、普通新 Hook 调用均不得自动解除。
- `turn_complete` 不伪造“已解决”；已经打开的等待记录只能由匹配 resolve 或 session end 关闭。
- 找不到真实审批解决事件时，该 Agent/版本的等待恢复能力必须标为不支持，不能用任意 `PostToolUse` 冒充。

### 3.4 终态规则

- 同一回合：`ERROR > COMPLETED > RUNNING`，只能单调折叠。
- 同回合 `ERROR` 后收到 `turn_complete`，保持 `ERROR`。
- 同回合 `COMPLETED` 后收到明确 `error`，升级为 `ERROR`。
- 实例结束：`ABNORMAL > NORMAL`，异常结束不得被后续普通结束降级。
- 已结束实例不得被迟到的 activity/complete/turn_start 复活。
- 新回合只重置该实例的当前回合基础状态，不自动解决旧 `ATTENTION`，也不清除实例级异常退出记录。

### 3.5 可靠事件与恢复

- 所有事件先写入本地持久 outbox，再尽力上报。
- 服务端按 `event_id + body_hash` 去重，FSM 修改和事件收件记录在同一 SQLite 事务提交。
- 服务重启恢复活动会话、等待、错误、完成截止时间和显示 revision。
- `activity` 可以合并；终态、等待、错误和结束事件不得因内存队列满而直接丢弃。
- 不宣称全链路 exactly-once；目标是**持久重试 + 幂等处理 + 最终一致**。

### 3.6 显示同步

- 每次有效目标显示变化，PC 先持久化 `desired_state + desired_brightness + desired_revision`，再允许发送。
- 串口同时最多一个未完成事务。
- 同一事务 ACK 超时最多原报文重试 2 次；最终失败后，以新事务持续同步**最新目标**。
- PC 保存 `acked_revision`，但设备重连、重启或 uptime 回退后必须重新对账。
- 心跳不能替代状态同步，也不能证明显示已经一致。

### 3.7 固定灯效

| 状态 | 灯效 |
|---|---|
| `IDLE` | 全灭 |
| `RUNNING` | 黄色常亮 |
| `ATTENTION` | 红色常亮 |
| `ERROR` | 红色 2 Hz，50% 占空比 |
| `COMPLETED` | 绿色常亮 |
| `WAIT_SYNC/LINK_LOST` | 黄色 1 Hz，50% 占空比 |
| `SUSPENDED` | 全灭 |

首版协议不开放任意 `pattern`、RGB、闪烁频率或动画编号。

---

## 4. 目标目录与责任边界

```text
agent-light/
├─ contracts/
│  ├─ usb-protocol-v1.md
│  ├─ usb-vectors.json
│  ├─ event-schema.json
│  ├─ fsm-transitions.md
│  ├─ compatibility.json
│  ├─ toolchain.lock.json
│  ├─ codex/<version>/sanitized-fixtures/
│  └─ dsh/<version>/sanitized-fixtures/
├─ pc/
│  ├─ pyproject.toml
│  ├─ src/agent_light/
│  │  ├─ daemon.py
│  │  ├─ api.py
│  │  ├─ schemas.py
│  │  ├─ identity.py
│  │  ├─ fsm.py
│  │  ├─ aggregator.py
│  │  ├─ store.py
│  │  ├─ outbox.py
│  │  ├─ display.py
│  │  ├─ config.py
│  │  ├─ cli.py
│  │  ├─ hooks/codex.py
│  │  ├─ wrappers/codex.py
│  │  ├─ serial/{worker,protocol,discovery}.py
│  │  └─ migrations/001_initial.sql
│  └─ tests/{unit,integration,crash_recovery,privacy}/
├─ plugins/
│  ├─ dsh/{package.json,package-lock.json,tsconfig.json,src/} 
│  └─ codex/agent-light/
├─ firmware/
│  ├─ Core/
│  ├─ USB_Device/
│  ├─ app/
│  └─ tests/{host,vectors}/
├─ hardware/
│  ├─ eda/
│  ├─ review/
│  ├─ bom/
│  ├─ manufacturing/
│  └─ bringup/
├─ structure/
├─ tests/
│  ├─ simulator/
│  ├─ hil/
│  ├─ agent_contract/
│  └─ reports/
├─ packaging/windows/
└─ outputs/
```

责任边界：

- 集成负责人独占 `contracts/` 和兼容矩阵。
- 固件 subagent 只修改 `firmware/` 及协议主机测试。
- PC subagent 只修改 `pc/`。
- DSH/Codex subagent 只修改各自插件和对应 fixtures。
- 硬件 subagent 只修改 `hardware/`、`structure/`。
- QA 只添加测试和报告，不通过修改生产代码让测试通过。

---

## 5. Subagent 编排方案

### 5.1 角色与工作包

| Subagent | 工作包 | 核心职责 |
|---|---|---|
| 集成负责人 | WP00/WP01/WP40 | 环境、合约、依赖、里程碑和最终集成 |
| 协议与测试替身 Agent | WP01/WP02 | 协议、golden vectors、模拟设备、故障注入 |
| PC Core Agent | WP10 | SQLite、事件模型、FSM、聚合、API |
| Device Link Agent | WP11 | 单串口 worker、事务、重连、desired/acked 对账 |
| CLI/Reliability Agent | WP12 | CLI、持久 outbox、wrapper、隐私入口 |
| DSH Agent | WP20 | 锁定版本适配器、真实事件映射、Node 测试 |
| Codex Agent | WP21 | Hook 合约、CLI 映射、Windows 信任与路径测试 |
| 固件 Agent | WP30 | Cube/Keil、CDC、协议、LED、看门狗 |
| 硬件 Agent | WP31 | 嘉立创 EDA、原理图、BOM、PCB、打样和 bring-up |
| 结构 Agent | WP32 | 遮光、扩散、外壳、安装与线缆应力 |
| QA/HIL Agent | WP40 | 全链路、恢复、性能、隐私、长稳和报告 |
| Release Agent | WP41/WP42 | Windows 打包、发布、可选跨平台和量产 |

### 5.2 统一 subagent 任务模板

主 Agent 分派任务时使用以下结构：

```text
你负责 <WP编号和名称>。
只允许修改：<目录列表>。
先阅读：contracts/ 中与本任务有关的冻结合约。
输入：<上游交付物及版本>。
必须完成：<步骤和验收条件>。
禁止：修改其他工作包接口；改变 Agent 决策；记录用户内容。
交付：文件清单、执行命令、测试结果、已知限制、接口偏差。
如果合约不足：停止对应实现，返回具体阻塞问题，不得自行猜测。
```

### 5.3 并行规则

- WP01 未完成前，PC、固件和适配器只能搭骨架，不能冻结业务代码。
- WP02、WP10、WP30、WP31 可在合约冻结后并行。
- WP20 与 WP21 可并行，但必须分别通过真实版本合约门禁。
- 任何协议变更必须由集成负责人升版本，并同时更新 C/Python 实现和向量。
- 同一文件不得交给两个并行 subagent 修改。
- 每个 P0/P1 缺陷先添加可复现测试，再修复。

---

## 6. 里程碑与依赖

```text
WP00 环境/工具核验
  ↓
WP01 合约冻结 ──→ WP02 模拟器
  ↓                 ↓
  ├─→ WP10 PC Core ─┬─→ WP11 串口对账 ──────────────────┤
  │                 └─→ WP12 CLI/outbox ────────────────┤
  ├─→ WP30 开发板固件 ─────────────────────────────────┤
  ├─→ WP31/WP32 硬件与结构并行                         │
  └─→ WP20 DSH / WP21 Codex 真实合约与适配器 ──────────┤
                                                       ↓
                                            WP40A 原型全链路验收
                                                       ↓
                                               WP41 发布打包
                                                       ↓
                                      WP40B 安装/升级/卸载与 RC 验收
                                                       ↓
                                             WP42 可选跨平台与量产
```

| 里程碑 | 准入条件 | 准出条件 |
|---|---|---|
| M0 可开发 | 工具版本记录完成 | 目录、依赖清单、合约负责人和回退机制就绪；项目依赖在各自工作包安装 |
| M1 可联调 | 协议和事件语义冻结 | C/Python 向量一致，模拟器可注入故障 |
| M2 虚拟全链路 | PC Core 和串口 worker 完成 | 多会话、乱序、补报、重启、对账测试通过 |
| M3 开发板全链路 | 固件与 PC 可构建 | 真实 USB 五态、看门狗、热插拔通过 |
| M4 Agent 全链路 | 至少一个真实 Agent 已安装 | 对应版本实景合约、非阻塞和行为不变通过 |
| M5 EVT 原型 | 定制板安全上电通过 | WP40A：电气、光学、结构、HIL 和 24 小时长稳通过 |
| M6 Windows RC | WP41 已生成实际发布包，所有 P0/P1 关闭 | WP40B：使用发布包完成 72 小时长稳、安装升级卸载和隐私审计 |
| M7 发布/量产 | RC 冻结 | 签名、VID/PID、回滚和适用生产门禁完成 |

---

## 7. WP00：环境、仓库与版本锁定

### 输入

- 本方案。
- 用户本机 Keil、STM32Cube、嘉立创 EDA、Node.js、Python。

### 操作

- [ ] 记录 Python、Node、npm、Git、CubeMX、CubeF0、Keil MDK、编译器、DFP、EDA 版本。
- [ ] 固定 Python 3.13 和 Node 22，禁止构建过程中隐式切换版本。
- [ ] 记录 Codex/DSH 是否存在、真实路径和版本；不存在则只阻塞对应适配器，不阻塞 PC/固件。
- [ ] 创建第 4 节目录，建立 Git 初始提交和 `.gitignore`。
- [ ] 忽略 `.venv/`、构建产物、数据库、token、spool、日志、真实敏感 fixtures 和制造临时文件。
- [ ] 创建 `contracts/toolchain.lock.json`，记录工具版本和构建哈希。
- [ ] 确认所有工作包可以独立回退，不在初始阶段生成安装器或修改用户 Agent 配置。

### Python 初始化

WP00 只创建虚拟环境，不安装尚未生成 `pyproject.toml` 的本地包：

```bash
py -3.13 -m venv .venv
./.venv/Scripts/python.exe -m pip install --upgrade pip
```

WP10 创建并锁定 `pc/pyproject.toml` 后，再执行：

```bash
./.venv/Scripts/python.exe -m pip install -e "./pc[dev]"
./.venv/Scripts/python.exe -m pytest pc/tests
```

建议依赖：

- 运行：`aiohttp`、`aiosqlite`、`pyserial`、`pydantic`、`platformdirs`、`PyYAML`。
- CLI：标准库 `argparse`。
- 测试：`pytest`、`pytest-asyncio`、`hypothesis`。

### Node 初始化

WP00 不要求 Node 项目已经存在。WP20 首次创建 `package.json` 后执行 `npm install`，生成并提交 `package-lock.json`；此后 CI 和后续 Agent 统一执行：

```bash
npm --prefix plugins/dsh ci
npm --prefix plugins/dsh run build
npm --prefix plugins/dsh test
```

### 交付与验收

- 工具版本矩阵、目录和初始提交存在。
- Python 3.13 虚拟环境可以创建；Python/Node 项目依赖和测试分别在 WP10/WP20 验收。
- 未安装 Codex/DSH 被明确记录为对应工作包阻塞，不影响其他线路。

---

## 8. WP01：冻结协议、事件模型和状态机

### 8.1 USB 协议 v1

如果已经存在按旧草案烧录的设备，旧草案与本方案布局不同，协议号必须升级；禁止同一版本号对应两种布局。

COBS 编码前帧：

```text
offset  size  field
0       1     version = 0x01
1       1     type
2       1     seq
3       1     length = payload 字节数
4       N     payload，小端
4+N     2     crc16，低字节在前
```

- Payload 最大 32 字节。
- CRC16-CCITT-FALSE：多项式 `0x1021`、初值 `0xFFFF`、不反射、不异或输出。
- `"123456789"` 的 CRC 校验值必须为 `0x29B1`。
- CRC 覆盖 `version` 至 payload 末尾。
- 整个 raw frame 标准 COBS 编码，末尾追加一个 `0x00`。
- COBS/CRC/截断/超长/帧结构错误：静默丢弃、计数、不改变灯态、不刷新看门狗。
- 只有通过帧结构和 CRC 校验的请求，才允许返回协议 NACK。

命令：

| type | 命令 | 请求 payload | 成功响应 |
|---|---|---|---|
| `0x01` | `SET_STATE` | `display_revision:u32, state:u8, brightness_pct:u8` | ACK + revision + applied |
| `0x02` | `HEARTBEAT` | 空 | ACK + `device_uptime_s:u32` |
| `0x03` | `GET_STATUS` | 空 | STATUS |
| `0x81` | `ACK` | `command:u8, result:u8=0, data...` | — |
| `0x82` | `NACK` | `command:u8, error:u8` | — |
| `0x83` | `STATUS` | 见协议合约 | — |

字节级长度必须固定：

- `SET_STATE` 请求 payload 顺序为 `display_revision:u32, state:u8, brightness_pct:u8`，因此 `length=6`，raw frame 固定 12 字节。
- 其成功 ACK payload 固定为 `command:u8, result:u8, display_revision:u32, applied:u8`，因此 `length=7`，raw frame 固定 13 字节。
- `applied=1` 表示本次接受并更新，`applied=0` 表示同 revision、同内容的幂等确认。
- 长度不符但 CRC 有效的请求返回 `BAD_LENGTH`；测试向量必须同时包含正确长度和错误长度。

首版删除固件 `CLEAR` 和 `SET_CONFIG`：

- 清除由 PC 修改会话/聚合后发送 `SET_STATE(IDLE)`。
- 亮度由 PC 随每次 `SET_STATE` 下发。
- 看门狗首版固定 5 秒。
- 因而首版不需要 Flash 配置双槽；后续新增持久配置时再单独设计，不提前增加故障面。

字段约束：

- `state` 仅允许 0～4；5 和其他值 NACK。
- `brightness_pct` 为 20～100，默认 35；`IDLE` 仍全灭。
- `display_revision` 由 PC 持久化，设备只在 RAM 保存，不写 Flash。
- 相同 revision + 相同状态/亮度：幂等 ACK，`applied=0`。
- 相同 revision + 不同内容：NACK `REVISION_CONFLICT`。
- 旧 revision：NACK `STALE_REVISION`，不得覆盖新状态。

NACK 错误码至少包含：

```text
0x01 BAD_LENGTH
0x02 UNKNOWN_COMMAND
0x03 UNSUPPORTED_VERSION
0x04 INVALID_VALUE
0x05 STALE_REVISION
0x06 REVISION_CONFLICT
0x07 SEQ_REUSED
0x08 NOT_READY
0x09 INTERNAL_ERROR
```

`STATUS` 至少返回：

```text
mode:u8
display_state:u8          # 无有效状态时 0xFF
display_revision:u32
revision_valid:u8
brightness_pct:u8
last_seq:u8
fw_version:u16
uptime_s:u32
crc_drop_count:u16        # 饱和计数
```

`mode`：`0=BOOT, 1=WAIT_SYNC, 2=ACTIVE, 3=LINK_LOST, 4=SUSPENDED`。

### 8.2 seq 与事务规则

1. 每个新事务使用下一 `seq`；同事务重试不变。
2. PC 同时只允许一个未完成事务，等待 ACK 时不得插入心跳。
3. 设备缓存最近一个完成事务的 `(seq,type,length,payload,response)`。
4. 完全相同的重试返回缓存响应，不重复执行。
5. 相同 seq 不同内容返回 `SEQ_REUSED`；PC 释放该事务，换下一 seq 同步最新目标。
6. seq 按 8 位自然回绕，测试至少覆盖 512 个事务。
7. PC 重开串口时从 seq 0 开始；设备 USB reset 时清空去重项。
8. 旧 ACK 只有匹配当前 `(seq,device_epoch,revision,payload_hash)` 才有效。

### 8.3 revision 回绕

- PC 使用 uint32 模递增；重试不增加 revision。
- 设备以无符号差值判断新旧：`0 < diff < 0x80000000` 为更新。
- `diff == 0` 走幂等/冲突规则；其他情况拒绝为旧版本。
- 必须测试 `0xFFFFFFFE → 0xFFFFFFFF → 0 → 1`。
- 实际实现若决定“回绕时强制设备复位并重新同步”，必须写入合约并删除不一致的模比较实现，不能两套规则并存。

### 8.4 统一事件字段

```json
{
  "schema_version": 1,
  "event_id": "uuid",
  "agent": "codex",
  "channel": "hook",
  "producer_id": "codex-hook-01",
  "producer_seq": 42,
  "session_id": "upstream-session-id",
  "instance_id": "uuid",
  "launch_id": "uuid-or-null",
  "turn_id": "turn-1",
  "turn_seq": 1,
  "attention_id": null,
  "type": "turn_start",
  "occurred_at": "2026-10-26T12:00:00+08:00",
  "reason_code": null
}
```

事件类型：

```text
session_start
turn_start
activity
attention_open
attention_resolve
error
turn_complete
session_end
clear
```

规则：

- `agent` 表示产品；`channel=hook/plugin/wrapper/manual` 只表示上报通道。
- 会话主键为 `(agent,session_id,instance_id)`，不得按 channel 拆分。
- `turn_seq` 在实例内递增；`producer_seq` 仅用于诊断，不作为跨 producer 的全局时钟。
- `occurred_at` 只用于展示，不用于判定因果顺序。
- `attention_open/resolve` 必须携带 `attention_id`。
- `session_end` 必须区分 `outcome=normal|abnormal`，可带标准退出码。
- 使用 `additionalProperties:false` 和字段白名单。
- 禁止 `prompt/message/content/tool_input/tool_output/error_text/cwd` 等字段进入统一事件。

### 8.5 FSM 迁移表

| 当前情况 | 事件 | 必须行为 |
|---|---|---|
| 无实例 | `session_start` | 创建新代次，基础状态 IDLE |
| 相同实例 | 重复 `session_start` | 幂等，不重置状态 |
| 旧代次 | 任意普通事件 | 返回 stale，不影响新代次 |
| ACTIVE | 更高 `turn_seq` 的 `turn_start` | 开新回合，基础状态 RUNNING |
| RUNNING | `activity` | 保持 RUNNING，更新本地活动时间 |
| ATTENTION | `activity` | 只更新活动时间，ATTENTION 不变 |
| RUNNING/ATTENTION | `attention_open` | 创建 OPEN 记录，显示 ATTENTION |
| ATTENTION | 错误 ID 的 `attention_resolve` | 不处理，保持 ATTENTION |
| ATTENTION | 精确匹配的 `attention_resolve` | 关闭该记录，重算基础状态 |
| RUNNING/ATTENTION | `turn_complete` | 当前回合基础状态 COMPLETED；不伪造等待已解决 |
| COMPLETED | 同回合 `activity` | 忽略，不把基础状态改回 RUNNING |
| ACTIVE 实例的当前回合 COMPLETED | 同回合 `attention_open` | 仍创建独立 OPEN 记录，最终 ATTENTION；覆盖 complete 先于 open 到达的乱序 |
| 旧回合或已 ENDED 实例 | 迟到 `attention_open` | 忽略，防止旧等待污染新回合或复活实例 |
| RUNNING/ATTENTION/COMPLETED | 当前回合 `error` | 进入或升级 ERROR |
| ERROR | 同回合 `turn_complete` | 忽略，保持 ERROR |
| COMPLETED/ERROR | 更高回合 `turn_start` | 新回合 RUNNING |
| 任意活动状态 | 正常 `session_end` | 关闭实例和等待；无错误则 IDLE，有错误则保留错误墓碑 |
| 任意活动状态 | 异常 `session_end` | 实例 ENDED/ABNORMAL，保留 ERROR |
| ENDED/NORMAL | 同实例 wrapper 非零退出 | 升级 ENDED/ABNORMAL + ERROR |
| ENDED/ABNORMAL | 重复正常结束 | 不得降级 |
| 任意 ENDED | 迟到 activity/complete/turn_start | 忽略，不复活 |
| COMPLETED | PC hold timeout | 基础状态 IDLE |
| ERROR/COMPLETED | 手动 `clear` | 清除对应终态 |
| RUNNING/ATTENTION | 手动 `clear` | 拒绝，不绕过等待和运行语义 |

### 8.6 交付与验收

- `usb-protocol-v1.md`、`event-schema.json`、`fsm-transitions.md` 完整。
- 冻结向量输入清单：字段值、预期 raw 长度、合法/非法结果和 CRC 覆盖范围；不要求本工作包提前实现下游 C/Python 模块。
- 每个状态 × 每个事件都有明确结果，不存在未定义 happy-path 外迁移。
- WP02 用独立 Python 参考实现生成 `usb-vectors.json`，WP30 完成 C 侧实现；M1 再检查 C/Python 双向一致性。
- 合约评审通过后，PC、模拟器、固件和适配器才可并行开发，解除 WP01 与 WP02/WP30 的依赖环。

---

## 9. WP02：协议模拟器、虚拟设备与事件回放

### 操作

- [ ] 实现 COBS/CRC/ACK/NACK/STATUS 的 Python 参考模型。
- [ ] 在 `serial_link` 传输边界实现内存虚拟设备，不把虚拟 COM 驱动作为产品依赖。
- [ ] 支持注入 ACK 丢失、延迟、重复、错误 seq、坏 CRC、截断、粘连、超长、NACK 和无响应。
- [ ] 支持模拟设备 uptime 回退、复位、USB 重连和 revision 边界。
- [ ] 建立 Agent 事件回放器：原始脱敏输入 → 入口裁剪 → 统一事件预期。
- [ ] 原始 fixtures 仅使用无敏感信息的测试会话；真实用户内容不得入库。
- [ ] 所有故障使用固定随机种子，失败可单独重放。

### 验收

- C/Python golden vectors 完全一致。
- 任意坏帧不改变虚拟设备或真实设备状态。
- 故障注入能稳定复现 ACK 全失败、旧 ACK、设备重启和事件补报。
- 模拟器通过不能替代真实 USB、LED 和真实 Agent 验收。

---

## 10. WP10：PC Core、SQLite、API 与聚合

### 10.1 数据模型

至少建立以下表：

| 表 | 关键内容 |
|---|---|
| `event_inbox` | event_id 主键、body_hash、白名单事件、首次处理结果、接收时间 |
| `pending_events` | 因缺少 session/instance/alias 而暂存的白名单事件、重试时间和到期时间 |
| `session_instances` | agent/session/instance/launch、生命周期、结束结果、当前 turn、错误标志 |
| `session_aliases` | launch_id 到 session_id 的晚绑定关系 |
| `turns` | 实例内 turn_seq/turn_id、RUNNING/COMPLETED/ERROR、完成 deadline |
| `attentions` | attention_id、turn、reason、OPEN/RESOLVED/CLOSED、打开和关闭事件 |
| `display_state` | aggregate、desired、acked、revision、device epoch、payload hash |
| `display_override` | HOLD/TEST、override_id、步骤、有效期和活动状态 |
| `meta` | schema 版本和迁移版本 |

强制事务：

```text
接收事件
→ 校验 event_id + body_hash
→ 应用身份/FSM/等待/终态
→ 重算聚合
→ 必要时递增并保存 desired_revision
→ 保存事件处理结果
→ 单事务 COMMIT
→ 通知 SerialWorker
```

### 10.2 API

| 接口 | 作用 |
|---|---|
| `POST /v1/events` | 接收单条事件并返回 applied/duplicate/stale/pending_identity；永久拒绝使用明确错误码 |
| `POST /v1/events/batch` | 批量补报，按 event_id 独立确认 |
| `GET /v1/status` | 返回脱敏会话、聚合、desired/acked 和设备状态 |
| `GET /v1/health` | DB、事件循环、设备、outbox 和丢帧计数 |
| `PUT /v1/display/override` | 设置 HOLD 或 TEST |
| `DELETE /v1/display/override` | 取消并恢复最新聚合 |
| `POST /v1/device/reconcile` | 使当前 ACK 世代失效并重新同步 |
| `POST /v1/sessions/clear` | 清除指定实例的 ERROR/COMPLETED |
| `POST /v1/sessions/forget` | 显式移除确认卡死的实例，单独审计 |

安全约束：

- 只绑定 `127.0.0.1`，随机 Bearer token，配置文件仅当前用户可读。
- HTTP body 默认上限 64 KiB；Codex 原始 stdin 上限 1 MiB。
- 限制 ID 长度、并发和请求速率；activity 按会话至少 1 秒节流。
- 相同 event_id 不同 body hash 返回 409，不覆盖首次事件。
- duplicate/stale 可作为最终确认，避免生产者无意义重试。
- orphan 不得直接最终确认：因缺少 session_start、instance 或 alias 导致的事件先写入 `pending_events`，返回可重试的 `pending_identity`；在身份绑定后自动重放，生产者保留原 outbox 记录。
- 同一 event_id 仍处于 pending 时，重复请求继续返回 `pending_identity`，不得因“收件记录已存在”而返回 duplicate 最终确认。
- 身份就绪后，pending 重放、FSM 修改和 inbox 当前结果更新必须在同一事务提交；应用成功后的后续重试返回最终 `duplicate`，生产者才可删除 outbox 记录。
- pending 默认保留 24 小时；到期或发生明确身份冲突后才永久拒绝并记录枚举诊断，避免真正乱序的关键事件被过早删除。
- 日志只记录枚举、脱敏 ID、时间和计数，不记录请求体。

### 10.3 聚合与恢复

- 跨实例固定：`ERROR > ATTENTION > RUNNING > COMPLETED > IDLE`。
- 只有有效目标显示变化才生成新 desired revision；普通 activity 不增加 USB 流量。
- 服务重启依次恢复数据库、活动实例、等待、当前回合、完成 deadline 和 override。
- 未完成 TEST 在崩溃后取消并恢复最新聚合；HOLD 是否持久恢复必须固定并测试。
- 过期 COMPLETED 在重启时先提交超时迁移，再启动显示 worker。
- pending 在 session_start/alias 绑定和服务重启后自动重放；重放使用 `turn_seq`、同 producer 的 `producer_seq`、接收序号构成确定性顺序，不使用墙钟猜测因果。
- 即使重放顺序不同，终态折叠和独立 ATTENTION 记录也必须得到相同最终状态；必须覆盖 `pending → applied → 重试 duplicate` 及各提交点崩溃恢复。
- 孤儿实例只能通过明确的 `forget` 或有证据的结束事件清理，不能简单定时删除错误。

### 10.4 验收

- FSM 全迁移、重复、迟到、实例代次和 wrapper/Hook 晚绑定测试通过。
- RUNNING/ATTENTION/ERROR/COMPLETED 各状态服务重启后精确恢复。
- 完成保持一半时重启，仍按原 deadline 到期。
- 16 会话随机事件测试无串态，空闲不覆盖运行，完成不覆盖等待。

---

## 11. WP11：串口 worker、设备发现与持续对账

### 11.1 执行模型

```text
aiohttp / CLI
   ↓
单一 StateStore 写入队列
   ↓
SQLite 事务提交 desired
   ↓ asyncio.Event
SerialWorker（唯一 COM 拥有者）
   ├─ 最新 SET_STATE，最高优先级
   ├─ SET_STATE 未同步时优先于心跳
   ├─ 每秒心跳，可合并过期心跳
   └─ GET_STATUS / 重连 / uptime 检查
```

- Windows 下 pyserial 阻塞 open/read/write/close 统一放入单线程专用 executor。
- 不得并发 `asyncio.to_thread` 操作同一串口。
- read 超时建议 50～100 ms；关闭时能及时唤醒。
- 状态队列只保留最新 desired，不积累历史灯态。
- 按 VID/PID 和序列号发现设备，不盲目打开第一个 COM 口。

### 11.2 对账算法

发送前记录：

```text
(seq, device_epoch, desired_revision, payload_hash)
```

仅完全匹配的 ACK 可以更新：

```text
acked_revision
acked_epoch
acked_state
acked_payload_hash
```

以下情况不得推进 ACK：

- NACK、超时、旧 seq、旧 device_epoch。
- payload hash 不一致。
- 写串口后服务崩溃。
- ACK 已收到但 ACK 落库前崩溃。

恢复规则：

- 普通事务 100 ms 超时，原报文最多重试 2 次。
- 最终失败后 0.5～5 秒退避，持续发送最新目标。
- 重连、设备 uptime 回退、协议错误和手动 reconcile 都使旧 ACK 失效。
- 设备重连后 5 秒内完成最新状态 ACK，不等待新的 Agent 事件。

revision 类 NACK 必须单独恢复，禁止用同一 revision 永久重试：

1. 收到 `STALE_REVISION` 后，下一事务执行 `GET_STATUS`，读取设备当前 revision。
2. PC 重新计算一个相对设备更新的 revision：必要时直接使用 `device_revision + 1`（按合约模规则），并在同一 DB 事务中保存“当前最新目标 + 新 desired_revision”。
3. 收到 `REVISION_CONFLICT` 时，PC 仍是目标状态权威，但必须递增 desired_revision 后再发送当前目标，不能重复发送冲突报文。
4. 只有新 revision 的匹配 ACK 才能推进 acked；NACK 本身绝不能视为同步成功。
5. 连续 3 次无法取得可信 STATUS 或仍发生 revision 冲突时，停止热重试，记录协议故障并重建连接；仍失败则要求人工检查 DB/固件兼容性。
6. 必须测试设备 revision 超前、同 revision 不同内容、PC DB 回退和恢复过程中又出现新 Agent 状态的场景。

### 11.3 手动测试与覆盖

- override 不暂停事件处理，不修改会话 FSM。
- 测试期间后台聚合继续更新。
- 每个测试步骤检查 override_id，防止旧任务覆盖新操作。
- 测试结束、取消或崩溃恢复时，生成新 desired revision，恢复**当时最新聚合**。
- 手动清除先修改 PC 会话/聚合，再发送 IDLE 或剩余最高优先级状态。

### 11.4 验收

- 多线程事件、心跳和手动操作下抓包无交叉写帧。
- WAIT_ACK 期间没有其他请求插入。
- ACK 全失败后仍持续同步，恢复后显示最新而非失败事务旧值。
- 测试期间聚合从 RUNNING 变 ERROR，测试结束后必须显示 ERROR。

---

## 12. WP12：CLI、持久 outbox、wrapper 与隐私

### 12.1 自有 CLI 合约

```text
agent-light serve --foreground
agent-light health
agent-light status --json

agent-light hook codex
agent-light wrap codex -- <真实codex路径> <参数>

agent-light outbox status
agent-light outbox flush

agent-light device ports
agent-light device reconcile

agent-light display override set IDLE|RUNNING|ATTENTION|ERROR|COMPLETED
agent-light display override clear
agent-light display test

agent-light session clear --agent codex --instance-id <uuid>
agent-light session forget --agent codex --instance-id <uuid>
```

这些是待实现的命令，不表示当前已经存在。

### 12.2 CLI outbox

```text
读取 stdin
→ 限长并解析
→ 内存中白名单裁剪
→ 本地 SQLite outbox 事务提交
→ 尝试发送
→ 服务确认后标记 acked
→ 立即退出
```

- outbox 与服务 DB 分离，避免服务损坏直接阻塞 Hook。
- `activity` 可合并；attention/error/complete/session_end 不得静默丢弃。
- 网络错误、408、429、5xx 和 `pending_identity` 使用指数退避补报。
- 普通 400/409 标记永久拒绝，不热重试，仅保留枚举诊断。
- 自动补报由 PC 服务的 outbox flusher 负责：服务启动时立即扫描，运行中每 2 秒扫描到期记录，`agent-light outbox flush` 仅作为手动触发；Hook 每次调用也可立即尝试一次，但退出后不依赖自身继续运行。
- flusher 与 CLI 通过 SQLite WAL、短事务和有界 busy timeout 共享 outbox；只有服务最终确认后才标记 acked。`pending_identity` 不标记 acked。
- 服务已应用事件但生产者尚未记录 ACK 时允许重发，由服务端 event_id 去重。
- DB 锁、磁盘错误、JSON 错误和服务不可用均不得让 Hook 输出调试文本。
- 管理命令可用非零退出码；Hook 上报异常退出 0。

### 12.3 wrapper 身份与退出码

1. wrapper 生成 `launch_id + instance_id`，通过环境变量传给子进程。
2. Hook 绑定真实 session_id 到相同 launch/instance。
3. wrapper 先退出、Hook 后绑定时，通过 alias 合并，不创建第二会话。
4. wrapper 透明继承 stdin/stdout/stderr，返回子进程原始退出码。
5. 非零退出映射 `process_exit + abnormal session_end`，但用户取消需按真实信号/原因分类，不能统称模型错误。
6. 上报失败不得改变原始退出码。

### 12.4 隐私

- cwd 首版不采集；确需工作区分组时另用安装级随机密钥 HMAC，不用普通无盐哈希。
- 插件异常日志不得直接序列化上游 error/event 对象。
- 日志设置大小和数量轮转，不保存 token 和请求体。
- 使用唯一 canary 扫描数据库、outbox、日志、USB 和崩溃输出，结果必须为零。

---

## 13. WP20：DSH TypeScript 原生插件

### 13.1 合约门禁

- [ ] 获取真实 DSH 路径、版本、Cordis 版本和包 hash。
- [ ] 从锁定版本类型定义确认 `apply`、事件名、监听器签名、`next()` 和错误传播。
- [ ] 确认 session/turn/request ID 字段，以及 web/headless profile 差异。
- [ ] 用无敏感测试会话采集脱敏真实事件顺序。
- [ ] 找到审批/提问的 open 与 resolve 接缝，二者必须能共享 attention_id。
- [ ] 不能确认时明确阻塞该能力，不虚构事件名。

### 13.2 实施步骤

- [ ] 主逻辑与 `adapter-<locked-version>.ts` 分离。
- [ ] `agent/pre-step` 首次生成 turn_start，后续只生成 activity。
- [ ] `tools/pre-execute/result` 只生成 activity，不读取参数或结果正文。
- [ ] `agent/request-error` 只映射 `model_error`，按真实签名原样传播错误。
- [ ] `session/event` 只消费已核实的回合边界，不遍历或上报 `event.data`。
- [ ] 审批/提问 open 和 resolve 使用同一 attention_id，resolve 不改变原回答。
- [ ] dispose 映射 session_end，并验证其正常/异常语义。
- [ ] reporter 同步调用不得抛出；适配器边界使用 `try/finally` 保证原 `next()` 链。
- [ ] 使用 JSONL segment + ACK checkpoint 持久 outbox；不引入首版不必要的 Windows 原生 Node 模块。
- [ ] 插件启动时先扫描旧 segment，运行中由后台 flusher 周期补报；checkpoint 通过“临时文件写入 + fsync + 原子替换”推进，只有全部确认后才清理 segment。
- [ ] 服务已应用但 checkpoint 未落盘时允许重放，由 event_id 去重；插件崩溃重启后继续从最后完整 checkpoint 恢复。
- [ ] assistant stream 只用于保活，按会话 1 秒节流，不上传 token。

### 13.3 验收

- P0 只强制用户实际选择并启用的 DSH profile；P1 再覆盖承诺支持的 web/headless profile 矩阵。
- 对纳入当前阶段的 profile 运行开始、工具、错误、完成和退出合约；未选择 DSH 时不阻断另一适配器的 P0 交付。
- 等待/解决合约仅对已核实接缝并宣称支持该能力的 profile 强制；无法核实时标为“不支持自动等待恢复”，只验证基本生命周期和明确降级，不得虚构事件，也不阻断另一适配器交付。
- 对支持等待的 profile：open A → activity/新 turn_start 后仍 ATTENTION；resolve B 不解除；resolve A 才解除。
- 安装前后工具决策、错误传播和返回值一致。
- 服务停止、黑洞和插件异常均不阻断 Agent。
- 完成后第二回合、错误后第二回合都能正确进入 RUNNING。

---

## 14. WP21：Codex Hooks 与进程包装器

### 14.1 合约门禁

- [ ] 获取真实 Codex 路径、版本和 `--help`。
- [ ] 从该版本文档/类型/真实输出确认 Hook 名称、stdin/stdout/exit code 合约。
- [ ] 验证 Windows 命令字段、路径转义、信任审核和修改后的重新信任流程。
- [ ] 采集 SessionStart、用户提交、工具前后、权限、Stop、SessionEnd 的脱敏样例。
- [ ] 确认权限解决事件；不能把任意 PreToolUse/PostToolUse 当成审批完成。
- [ ] 无通用 Error Hook 时，明确基础版不能捕获所有内部错误。

### 14.2 实施步骤

- [ ] `agent-light hook codex` 读取限长 stdin，立即裁剪白名单字段。
- [ ] 按锁定版本生成插件和 Hook 配置，不直接照抄未核实示例。
- [ ] SessionStart 创建实例；用户提交创建 turn_start；工具前后只产生 activity。
- [ ] 权限请求产生 attention_open；只有匹配解决事件产生 attention_resolve。
- [ ] Stop 只表示回合结束，不表示业务成功；中断分类必须使用真实原因字段。
- [ ] stdout 输出严格按该版本协议，普通事件不输出内容，不返回 block/decision。
- [ ] `codex exec` 使用 wrapper 补充退出状态；交互式无法覆盖的错误列入限制。
- [ ] Windows 使用安装器生成的用户级绝对 launcher 路径，不写死用户目录。
- [ ] 未经用户确认，不修改现有 Codex 配置；修改前备份，卸载可恢复。

### 14.3 验收

- 真实 Hook 回放和实景运行一致。
- 服务故障时 Hook 不超时、不污染 stdout、不改变 Agent 行为。
- 工具非零退出但 Agent 继续时保持 RUNNING。
- 路径含空格、非交互 PATH、Hook 信任和升级后重审全部通过。
- wrapper 与 Hook 任意先后到达仍只形成一个逻辑实例。

---

## 15. WP30：STM32Cube、Keil 与嵌入式固件

### 15.1 G0：料号和工具核验

在生成工程前，固件 subagent 输出带官方文档版本/页码的核验表：

- 精确料号 `STM32F042F6P6`、32 KB Flash、6 KB SRAM。
- PA11/PA12 USB，PA0/PA1/PA2 定时器 PWM 复用，PA13/PA14 SWD。
- HSI48、CRS、USB 48 MHz 时钟路径和免晶振条件。
- USB D+ 可控上拉是否集成及默认状态。
- 全部供电/地、BOOT0、NRST 外围。
- Flash/RAM、USB 缓冲、栈和应用缓冲预算。
- 与 USB、CRS、复位、低功耗有关的勘误。
- Keil DFP 是否包含精确料号，SWD 和 Flash 编程算法是否可用。

未核实项不得进入冻结配置；不得无依据声称芯片支持或不支持某项能力。

### 15.2 Cube 工程操作清单

用户在 Cube GUI 执行，Agent 提供配置并检查生成结果：

- [ ] 新建精确料号工程，配置 SWD。
- [ ] 启用 USB Full Speed Device 和 CDC ACM，PA11=DM、PA12=DP。
- [ ] 配置 HSI48+CRS 和 48 MHz 时钟，按安装版本和手册确认。
- [ ] 配置三路 PWM，目标 10 kHz；实际 PSC/ARR 由真实定时器时钟计算。
- [ ] PWM 启动前比较值为 0，LED 极性集中在 board 配置。
- [ ] USB 中断只做栈必要处理和字节入队，不解析协议或写 Flash。
- [ ] 生成 MDK-ARM 工程，应用代码放独立 `app/`。
- [ ] Cube 再生成后检查时钟、描述符、中断、内存布局和用户代码差异。

### 15.3 Keil 配置

- [ ] 固定 ARM Compiler 和 Debug/Release C 语言配置。
- [ ] 检查 IROM/IRAM 与精确料号一致，首版无需为配置双槽预留页面。
- [ ] 应用层禁止动态内存；检查 map 中栈、USB 和应用缓冲占用。
- [ ] 配置 ST-LINK/SWD 和正确 Flash 算法。
- [ ] Debug/Release 均 0 error；所有 warning 必须解释。
- [ ] Release 也执行完整 USB、协议和灯效回归。
- [ ] 首次 GUI 构建通过后，再评估是否使用真实 Keil CLI 自动构建，不假定可执行路径。

### 15.4 固件模块

```text
firmware/app/
├─ app_main.c/.h
├─ board.c/.h
├─ cobs.c/.h
├─ crc16.c/.h
├─ protocol.c/.h
├─ protocol_def.h
├─ serial_tx.c/.h
├─ display.c/.h
├─ led_pwm.c/.h
└─ link_watchdog.c/.h
```

缓冲区建议：

| 缓冲区 | 大小 | 规则 |
|---|---:|---|
| USB RX 环形队列 | 256 字节 | ISR 单生产者，主循环单消费者 |
| raw 帧 | 40 字节 | 最大合法 raw 38 字节 |
| COBS/TX 暂存 | 48 字节 | 超限进入丢弃状态 |
| 去重记录 | 1 项 | 保存完整请求指纹和响应 |

- 队列满时丢弃新字节并计数，不覆盖未消费数据。
- 字节丢失后丢弃到下一个 `0x00`，防止后半截被当成新帧。
- 主循环限制单次处理字节/帧数，防止输入饿死 LED 和看门狗。
- 时间比较使用无符号差值，覆盖 tick 回绕。
- `serial_tx` 是唯一 CDC 响应入口。

### 15.5 固件显示模式

| 模式 | 进入 | 灯效与退出 |
|---|---|---|
| BOOT | 上电/复位 | 红黄绿各 100 ms；完成后 WAIT_SYNC |
| WAIT_SYNC | BOOT、USB reset/resume | 黄色 1 Hz；仅合法 SET_STATE 进入 ACTIVE |
| ACTIVE | 接受到合法 SET_STATE | 执行最近状态；看门狗超时进入 LINK_LOST |
| LINK_LOST | ACTIVE 中 5 秒无有效请求 | 黄色 1 Hz；收到最新 SET_STATE 后恢复 |
| SUSPENDED | USB suspend | 全灭并关闭 PWM；resume 后 WAIT_SYNC |

- 心跳只能维持链路，不能单独把 WAIT_SYNC/LINK_LOST 恢复成旧 Agent 状态。
- 坏帧和非法请求不刷新看门狗。
- 设备 reset 后 revision_valid=false，由 PC 重发当前状态。
- COMPLETED 无固件计时器。

### 15.6 固件测试

主机 C 测试：

- COBS、CRC、长度、错误码、seq 去重和 revision 新旧。
- display 模式迁移和固定灯效。
- fake tick 覆盖 5 秒超时和 tick 回绕。
- 随机字节、截断、粘连、超长和连续坏帧。

HIL 测试：

- 冷启动、热插拔、Hub、主机睡眠/唤醒。
- 五态、亮度、2 Hz/1 Hz 实测频率和占空比。
- ACK 丢失幂等、seq 回绕、revision 边界。
- MCU reset 后 WAIT_SYNC，PC 无需 Agent 新事件即可同步。
- 连续 24 小时无协议卡死、内存泄漏和明显灯效漂移。

### 15.7 交付物

- Cube 工程、Keil 工程、版本核验表、map。
- 固件源码、Debug/Release 二进制和 SHA-256。
- 主机 C 测试、HIL 脚本、串口日志和测试报告。
- 已知限制和未通过的硬件角落，不得以开发板结果替代定制板验收。

---

## 16. WP31：嘉立创 EDA 硬件、PCB、打样与 bring-up

### 16.1 原理图分页

建议由单一 EDA 负责人修改源工程，其他 subagent 通过导出 PDF、网表、BOM 和问题清单评审。

| Sheet | 内容 |
|---|---|
| 00 封面 | 硬件版本、精确料号、文档版本、DNP 规则、修改记录 |
| 01 USB/电源 | USB-C、CC、防护、LDO、VBUS、3V3、屏蔽接地选项 |
| 02 MCU | 全部供电脚、去耦、USB、时钟依据、可控上拉 |
| 03 LED | 红/黄/绿独立限流、PWM、极性和装配顺序 |
| 04 调试/产测 | SWD、BOOT0、NRST、3V3、5V、GND 测试点 |

### 16.2 关键电路规则

- CC1、CC2 各自独立 5.1 kΩ/1% 下拉到 GND。
- 连接器 → 低电容 ESD → 约 22 Ω 串阻 → MCU；实际值通过信号完整性复核。
- 每路 VDD 就近 100 nF，MCU 附近 4.7 µF；LDO 电容按具体型号稳定性要求。
- 不用未授权的量产 VID/PID。
- 首版推荐不做额外 VBUS GPIO 检测：整板总线供电，VBUS 存在不代表服务正常，链路由心跳判断。
- BOOT0 默认下拉并预留安全拉高焊盘；NRST 外围按官方指南。
- SWD 3V3 默认作电平参考，是否允许编程器供电必须在产测规程中单独定义。
- SHIELD 预留直连与 `1 MΩ || 1 nF` 调试选项，由实测决定默认装配。

### 16.3 选型计算

每路 LED：

```text
I_LED = (3.3 - V_F) / R
P_R = I_LED² × R
```

- V_F 必须参考目标低电流和温度范围，不直接套用 20 mA 条件。
- 三色可使用不同电阻，准备多个阻值样品调亮度。
- 默认单灯工作电流目标小于 30 mA，同时记录三灯产测模式峰值。

电源：

```text
I_total = I_MCU,max + ΣI_LED + I_other
P_LDO = (VBUS,max - 3.3) × I_total
T_J = T_A + P_LDO × θ_JA
```

LDO 必须核查输入范围、输出电流、压差、精度、电容/ESR 稳定区、启动、短路、过温和实际热阻。

### 16.4 原理图冻结门禁

- [ ] MCU 引脚、电源、USB、时钟、电流、SWD/BOOT 和勘误均有官方证据。
- [ ] 相同精确 MCU 开发板完成 USB CDC、热插拔和睡眠恢复验证。
- [ ] LED 实料完成低电流亮度、颜色和 20% PWM 试验。
- [ ] 连接器封装、焊盘、内部 D+/D- 关系按图纸和实物复核。
- [ ] BOM 每个器件有完整 MPN、封装、数据手册和批准替代规则。
- [ ] MCU 引脚和连接器封装由第二人独立复核。
- [ ] ERC 无未解释错误，结构确认 LED/USB/测试点位置可装配。

### 16.5 BOM 必填字段

- 位号、数量、装配状态、参数、封装。
- 制造商、完整 MPN、嘉立创/LCSC 料号、库存和采购数量。
- 数据手册链接、版本和最后核查日期。
- 电阻精度/功率/温漂；电容介质/耐压/直流偏压。
- LED 颜色、波长/色区、光强、Vf、视角和 bin。
- ESD 工作电压、电容、钳位、通道和 pinout。
- 批准替代料、需重跑测试、硬件/BOM 版本和批准人。

### 16.6 PCB 和结构约束

- 双层板，Bottom 尽量完整地平面；板厚/铜厚与结构、阻抗共同确定。
- 90 Ω 差分线宽/间距必须根据板厂真实层叠计算，不写死通用值。
- ESD 靠近连接器，串阻靠近 MCU，去耦靠近供电脚。
- D+/D- 同层、短、平行、少过孔，保持连续回流，避免长支路。
- LED 红上、黄中、绿下，位置与遮光仓一致。
- USB-C 放背部/底部，预留线缆弯折和插拔空间。
- 测试点不得被外壳遮挡。
- ERC/DRC 无未解释错误，零未布线；Gerber、坐标、旋转和极性逐层复核。

### 16.7 打样、上电和联调

首版建议 3～5 块板，不直接量产。

打样包：原理图 PDF、Gerber、钻孔、制造说明、BOM、CPL、装配图、DNP、版本和校验值。

上电前：

- 显微镜检查 MCU 桥连、LED/LDO 极性、USB-C 连锡。
- 测量 CC1/CC2 独立下拉，检查 VBUS/3V3 异常短路和 D+/D- 互换。
- 清理助焊剂，核对所有 DNP。

分级上电：

1. 通过测试点限流供电，先观察异常电流和温升。
2. 测量 3.3 V、启动和纹波；异常立即断电。
3. 连接 SWD，烧录最小测试固件。
4. 分别点亮红黄绿，测量每路实际电流和 PWM。
5. 撤下实验电源，避免与主机 VBUS 并联，再切换真实 USB-C。
6. 验证枚举、协议、热插拔、看门狗和 24 小时长稳。

### 16.8 交付与回退

- 交付 EDA 源工程、原理图/PCB 导出、BOM、制造包、审查和 bring-up 报告。
- 免晶振、亮度或 USB 稳定性不达标时，回到时钟/LED/布局方案，不靠软件掩盖。
- 核心换料必须解除冻结并重跑对应评审和测试。

---

## 17. WP32：结构与光学

- [ ] 首版只选一种主要安装方式打样，不同时开发磁吸、背胶和弹性夹三套结构。
- [ ] 黑色内骨架形成三个独立遮光仓，乳白扩散片独立出光。
- [ ] 调整 LED 到扩散片距离、遮光壁、扩散片雾度和 LED 角度。
- [ ] 显示器接触面加软质保护，线缆插拔不得把设备拉起。
- [ ] 输出 STEP/STL、装配图和关键尺寸。

验收：

- 办公室照明下约 1 m 可辨红黄绿。
- 20% 亮度无明显频闪、颜色突变或不可控微亮。
- 单灯点亮时其他仓无明显彩色串光。
- 白天可辨、夜间不过亮；摄像条纹按实际使用条件测试，不能仅凭 PWM >1 kHz 宣称无条纹。
- 插拔、轻微跌落和装配后无松动、遮挡或明显结构干涉。

---

## 18. WP40A/WP40B：系统集成、故障注入与验收

- **WP40A（WP41 前）**：单元、虚拟设备、开发板/定制板、真实 Agent、原型安装前 HIL、24 小时原型长稳。
- **WP40B（WP41 后）**：使用实际发布包执行安装、升级、卸载、干净机验证、72 小时 RC 长稳和发布回归。
- WP40B 不得使用开发环境代替安装包，也不得在安装器尚未完成时提前标记 RC 通过。

### 18.1 核心测试矩阵

| 类别 | 必测场景 | 通过条件 |
|---|---|---|
| 等待 | open A → activity/新 turn_start → resolve B | 始终 ATTENTION |
| 等待恢复 | open A → resolve A，重复 resolve A | 第一次恢复，重复幂等 |
| 等待乱序 | turn_complete 先于 attention_open 到达，实例仍 ACTIVE | 建立 OPEN 记录，最终 ATTENTION；匹配 resolve 后恢复 COMPLETED |
| 终态 | error → complete；complete → error | 最终均 ERROR |
| 实例 | 新 instance 后旧 instance 结束/活动到达 | 新代次不受污染 |
| 身份 | wrapper 与 Hook 任意顺序、晚绑定 | 只有一个逻辑实例 |
| 去重 | 同 event_id 同 body；不同 body | 前者幂等，后者 409 |
| 补报 | 服务离线、ACK 丢失、进程崩溃 | 终态补报可恢复，重复不重复改状态 |
| 重启 | 四种 Agent 状态及完成保持中重启 | 精确恢复，deadline 不重置 |
| 显示崩溃 | desired 提交后未发送；设备执行后 ACK 未落库 | 重启后最终一致 |
| 串口 | 第 1/2/3 次 ACK 丢失、NACK、旧 ACK | 不误确认，持续同步最新目标 |
| 序号 | seq 连续 512 次、revision 回绕 | 无误判、无旧状态覆盖 |
| 手动测试 | 测试期间 RUNNING → ERROR | 测试结束显示最新 ERROR |
| 多会话 | 16 会话，另做 32 会话压力 | 零串态、零优先级错误 |
| 隐私 | 各入口注入唯一内容 canary | DB/spool/日志/USB 中零命中 |
| 行为不变 | 有无插件执行同一工具/错误/审批用例 | 决策、输出、退出码完全一致 |
| 真实硬件 | 热插拔、复位、睡眠、串口占用 | 自动恢复最新状态 |

### 18.2 故障点注入

必须在以下位置支持强制终止或故障注入：

- 事件 DB commit 前后。
- FSM 提交后、desired 通知前。
- desired 提交后、串口 write 前。
- 串口 write 后、ACK 接收前。
- ACK 接收后、ACK 落库前。
- override 切换和测试步骤前后。
- 设备 reset、USB data 断开、设备断电和串口占用。

### 18.3 量化验收

| 指标 | 首版通过标准 |
|---|---|
| API 接受到实际灯态 | 正常 1,000 次变化：p95 ≤150 ms，p99 ≤300 ms，max ≤500 ms |
| 真实 Agent 到灯态 | 仅对已选择支持的版本/profile：每个至少 30 个完整回合，p95 ≤300 ms，p99 ≤600 ms，max ≤1 s |
| DSH reporter 同步开销 | 仅在选择 DSH 时强制：正常及故障场景 p95 ≤2 ms，p99 ≤10 ms，max ≤50 ms，不等待 USB |
| Codex Hook 进程 | 仅在选择 Codex 时强制：正常 p95 ≤150 ms、max ≤500 ms；故障 max ≤750 ms 且无 Hook 超时 |
| USB 重连 | 100 次：从端口可打开到最新状态 ACK，p95 ≤3 s，max ≤5 s |
| LINK_LOST | 默认 5 秒配置下，不早于 4.5 s、不晚于 6 s |
| 手动测试恢复 | 结束到最新状态 ACK，max ≤500 ms |
| 多会话 | 16 会话零错误；32 会话压力无死锁和明显资源失控 |
| 原型长稳 | 24 小时零崩溃、零死锁、零错误灯态 |
| 发布长稳 | 72 小时，包含至少 1,000 次 seq 回绕和周期故障注入 |

每次性能报告保留样本数、p50/p95/p99/max、构建号、主机配置和故障场景，不能只给平均值。

### 18.4 隐私与安全验收

- 服务只监听回环；局域网连接失败。
- 无 token、错误 token、跨用户读取配置失败。
- 超大 HTTP/stdin、非法 JSON、字段超长和高频 activity 安全拒绝或节流。
- 原始提示词、代码、路径、工具参数、回答、错误正文设置 canary，全链路扫描为零。
- USB 设备不存在反向触发 Agent 操作的接口。
- 安装/卸载不破坏用户原有 DSH/Codex 配置，备份可恢复。

### 18.5 缺陷与回退

- P0：修改 Agent 决策、泄露内容、开放非回环接口、损坏配置、过热或批量变砖，立即停止集成和发布。
- P1：状态错误、恢复失败、重连超 5 秒、非阻塞超标、崩溃、16 会话串态，阻断当前里程碑。
- 每个 P0/P1 先添加自动复现测试，再修复。
- RC 阶段生产代码变化后，重新开始 72 小时长稳。
- 协议/schema 回退时，固件、PC、CLI 和插件按兼容组合整体回退。

---

## 19. WP41：Windows 原型与发布打包

### 19.1 原型阶段

- 使用 `.venv` 和绝对 CLI 路径验证，不依赖交互式 PATH。
- 用户手动启动 `agent-light serve --foreground` 完成开发验证。
- 不默认写开机启动，不默认修改 Codex/DSH 全局配置。

### 19.2 用户级发布阶段

- 首版采用用户级托盘 + 可选登录启动，不必做成高权限 Windows Service。
- 使用 PyInstaller 或可复制运行环境，锁定打包版本并验证干净机。
- 配置、token、DB、outbox、日志放当前用户应用数据目录，通过 `platformdirs` 获取。
- Windows ACL 仅允许当前用户及必要系统主体。
- 安装器生成真实绝对 launcher 路径，处理空格和非交互环境。
- 安装前备份用户明确选择修改的 DSH profile/Codex 配置。
- 卸载移除本软件启动项和失效 Hook，保留或恢复用户原配置；不得误删其他配置。
- 发布包包含固件/安装包 SHA-256、兼容矩阵、支持版本和回滚说明。

### 19.3 安装验收

在干净、已安装、升级、损坏配置、路径含空格环境分别验证：

- 安装、启动、设备发现、真实 Agent 事件和手动测试。
- 服务异常退出后的恢复。
- 升级后 DB migration 和配置读取。
- 卸载后无后台进程、启动项和失效 Hook 残留。
- 再次安装不重复写入插件配置。

---

## 20. WP42：可选跨平台、升级与量产

### 20.1 macOS/Linux

只有完成以下工作后才能宣称对应平台兼容：

- CDC 设备发现、稳定路径和权限。
- 用户服务、自启动、安装升级卸载。
- 配置 ACL、签名/公证或发行包要求。
- 睡眠恢复、热插拔和真实 Agent 合约。

协议免私有驱动不等于完整产品兼容。

### 20.2 固件升级

- 首版可明确“仅 SWD 维修烧录，无现场升级”。
- 若宣传 USB DFU，必须按精确料号和 AN2606 核实，另行设计完整性、失败恢复和版本兼容。
- 不得在未实现升级路径时宣称可现场回滚固件。

### 20.3 量产可选门禁

- 工厂烧录、回读校验、唯一序列号、配置初始化。
- 每台 USB 枚举、GET_STATUS、五态、LED、全灭和电流测试。
- 保存硬件/固件/工装版本、测试时间、序列号和失败代码。
- 测试限值来自器件规格和黄金样机统计，不得为提高直通率擅自放宽。
- 根据目标市场制定 EMC、ESD、环保和其他适用合规矩阵。
- 预检不等于认证，未测试前不得宣称全温、工业级或认证通过。

---

## 21. 主 Agent 推荐执行顺序

### 第一批：立即并行

1. 集成负责人执行 WP00。
2. 协议 Agent 起草 WP01，但由集成负责人最终冻结。
3. 硬件 Agent 执行精确料号资料核验和开发板准备，不等待 Codex/DSH。
4. DSH/Codex Agent 只执行环境探测；命令不存在时返回阻塞，不编写猜测适配器。

### 第二批：合约冻结后并行

- WP02 模拟器。
- WP10 PC Core。
- WP30 开发板固件。
- WP31 原理图/BOM，WP32 结构原型。

### 第三批：接口可用后并行

- WP11 串口对账。
- WP12 CLI/outbox。
- WP20/WP21 仅在真实版本合约门禁通过后实施。
- WP31 PCB 与结构继续，不等待软件全部完成。

### 第四批：WP40A 原型集成

- PC + 模拟器完成虚拟全链路。
- PC + 开发板完成真实 USB 全链路。
- 接入真实 Agent 后再做端到端验收。
- 定制板 bring-up 通过后，把同一套 HIL 完整重跑。
- 完成 24 小时原型长稳，关闭阻断打包的 P0/P1。

### 第五批：WP41 打包与 WP40B 发布验收

- WP41 先生成实际 Windows 发布包和安装/升级/卸载流程。
- WP40B 再使用该发布包执行安装、升级、卸载、干净机和 72 小时 RC 长稳。
- 完成隐私审计，关闭全部 P0/P1；RC 生产代码变化后重新计时。
- 再决定跨平台、DFU 和量产，不让可选功能阻塞首版原型。

---

## 22. 最终 Definition of Done

### 软件

- [ ] 所有 contracts 有版本，C/Python 使用相同协议语义；选择 DSH 时，Node 适配器也通过相同事件语义合约。
- [ ] FSM 全迁移、乱序、去重、实例代次和终态测试通过。
- [ ] outbox 补报、服务重启和完成 deadline 恢复通过。
- [ ] 单串口写入者、单事务、持续对账和设备重连通过。
- [ ] 至少一个真实 Agent 的锁定版本合约通过，其他能力明确标注。
- [ ] Agent 行为不变和隐私 canary 测试通过。

### 固件与硬件

- [ ] Cube/Keil 版本和精确料号核验记录完整。
- [ ] 固件 Debug/Release 构建和测试通过，map 无资源异常。
- [ ] 真实 USB 五态、链路、复位、挂起恢复和 24 小时长稳通过。
- [ ] 原理图/BOM/PCB/结构评审和实物 bring-up 记录完整。
- [ ] 定制板重新执行完整 HIL，不以开发板结果替代。

### 交付

- [ ] 源码、构建号、固件/安装包哈希和测试报告可一一对应。
- [ ] 支持矩阵明确“已验证/未验证/不支持”，无模糊承诺。
- [ ] 已知限制、回退方法和用户操作说明完整。
- [ ] 无开放 P0/P1；RC 变更后重新执行规定回归。
- [ ] 用户能够在干净 Windows 环境按说明复现安装、运行和验收。

---

## 23. 首版最关键的实施纪律

1. **先冻结合约，再并行编码。**
2. **PC 管业务，固件管显示；不允许两套完成保持计时。**
3. **等待只能由匹配事件解除，不能靠任何活动猜测。**
4. **关键事件先持久化，再上报；失败必须可补报。**
5. **显示以 desired/acked revision 对账，不以“发送过”视为成功。**
6. **真实 Agent 版本和事件未核验前，不写猜测适配器。**
7. **GUI 和实物步骤由用户确认，Agent 不虚构执行结果。**
8. **模拟器用于提速，真实硬件和真实 Agent 用于最终验收。**
