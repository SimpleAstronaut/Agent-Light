# DeepSeek Harness 状态灯插件设计

日期：2026-11-06。状态：用户已授权按方案开发；v0.1 产品实现及有限软件检查已交付，真实 Web/实板与完整验收尚未通过。执行记录见 `outputs/pc-dsh-implementation.md`。

## 1. 目标与已确认范围

用户已完成硬件焊接并确认通信测试正常。本阶段先设计 DeepSeek Harness 插件，为后续上位机接入提供明确合约。用户实际入口是 `dsh-web`，已选择“后台 HTTP 上报 + 持久队列”方案 A。

用户进一步要求 Python 上位机预留未来 Codex 插件的接入接口。因此统一接入层、身份隔离、能力声明与多来源聚合属于本期设计范围；真实 Codex 适配器仍留到后续版本核验后实现。

首版让一台电脑上的 Agent Light 显示 DSH Web 的运行、等待用户、最终失败、完成和空闲状态。沿用现有 Python PC 服务设计：PC 负责业务聚合与 USB，插件负责把 DSH 生命周期转换成不含内容的事件。固件和 USB v1 无需因本设计改变。

以下是设计者提出的首版边界，尚不代表用户已批准：

- Windows、一个 `dsh-web` 后端、一个插件实例、多个顶层聊天，正常容量 16 个并发聊天。
- 汇总所有运行中的顶层聊天，不随浏览器当前选中标签切换。
- 子 Agent 不单独形成灯态；可恢复的子任务失败由所属顶层 Agent 的最终结果体现。顶层聊天结束后独立后台子任务不在首版显示范围。
- 插件安装或升级后重启 DSH；首版不支持在已有 Agent 运行时热加载或更换适配器。
- 用户主动停止回合不显示“完成”或“失败”；基础状态回到空闲，仍未回答的限时提问继续显示等待。
- 绿色默认保持 300 秒，亮度默认 35%，均由 PC 配置管理。

非目标：重写 DSH、修改审批决策、读取聊天内容做状态推断、浏览器扩展、Web 前端 UI、真实 Codex 适配器实现、内核驱动、多台主机、发布安装器。预留 Codex 通用接入合约在本期范围内。

失败判据：指示插件改变 Agent 输出/错误传播/审批结果；重试成功却一直红闪；未回答的问题被普通活动解除；旧实例补报覆盖新实例；声称已验证但未运行真实 DSH 合约。

## 2. Approaches：方案选择

| 方案 | 优点 | 代价 | 结论 |
|---|---|---|---|
| A：Cordis 插件后台 HTTP + 持久 outbox | 无逐事件子进程开销，适合流式活动与多个会话 | 需要队列、恢复和幂等合约 | 用户已选择 |
| B：Cordis 插件调用 `agent-light` CLI | 复用 CLI 的上报与 outbox | 进程创建开销、绝对路径部署、输出隔离 | 不采用 |

沿用既有架构：插件不打开 COM 口。多个插件或未来 Codex 共用 PC 服务，只有 PC SerialWorker 能写设备。

## 3. 调研证据及版本边界

### 3.1 本机只读核查

| 项目 | 观察结果 |
|---|---|
| 启动入口 | `D:\deepseek\bin\dsh-web.ps1` 调用 `dsh.cmd web ... --no-open` |
| 实际 DSH CLI | `D:\deepseek\npm-global\node_modules\@deepseek-ai\dsh\lib\bin.js` |
| DSH | `dsh --version` 返回 `0.2.1-rc.2` |
| Cordis | 安装包版本 `4.0.5` |
| Node | 启动脚本选择 `D:\deepseek\runtime\node-v22.23.2-win-x64\node.exe`；不是外部 PATH 的 Node |
| DSH_HOME | 启动脚本设置为 `D:\deepseek\data\dsh` |
| 目标 profile | `D:\deepseek\data\dsh\profiles\web`；bundles 为 `dsh-base`、`dsh-web-app` |
| 项目当前内容 | 已有硬件、固件和 USB 合约；没有 PC 服务、事件 schema 或 DSH 插件实现 |
| Git | `D:\projects\agent-light` 当前不是 Git 仓库；本次仅保存设计文件，不擅自初始化或提交 |

没有读取凭据文件、聊天记录或完整运行配置；没有启动测试聊天、修改 profile 或连接实物。用户的通信测试结果作为当前前提，不扩大为本次执行过硬件验收。

### 3.2 已核实的公开类型及运行代码

下列路径相对 `D:\deepseek\npm-global\node_modules\@deepseek-ai\dsh\node_modules\@deepseek-ai`：

- `dsh-agent/lib/types/runtime-types.d.ts`：`agent/created`、`agent/disposed`、`agent/status`、`agent/request-error`、`agent/assistant-stream`。
- `dsh-agent/lib/types/index.d.ts`：`ctx.agents.get()`、`list()`、`roots()`；必须按运行时所有权辨识顶层 Agent，不能按持久的 `parentSession` 猜测。
- `dsh-session/lib/types/types.d.ts`：`turn/start`、`turn/end` 与结束原因。
- `dsh-user-approval/lib/types/types.d.ts`：`approval/asked` 和 `approval/decided` 共享 `data.id`。
- `dsh-user-questions/lib/types/index.d.ts`、`types.d.ts`、`projection.d.ts`：阻塞提问与限时提问不同；限时提问状态包含 `open`、`continued`。
- `dsh-session-projection/lib/types/index.d.ts`：`onChanged(session,key,value,seq)`、`stateOf(session,key)`、`snapshot()`；缺少 projection 是能力缺失，不能视为没有等待。
- `dsh-tool-ask-user/lib/index.js`：支持 `legacy`/`timed`，包默认 legacy，不能据此推断用户实际 preset 模式。
- `dsh-web-app/cordis.patch.yml`：区分 Host 与 per-agent preset；本插件放 Host，覆盖顶层会话。

参考上游说明：[Extension cookbook](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/cookbook/extension-cookbook.md)。上游 master 会变化，实施依据是本机锁定版本，不照抄 master 签名。

核查文件 SHA-256（仅这些文件的指纹，不是 npm 包整体 hash）：

| 文件 | SHA-256 |
|---|---|
| CLI `package.json` | `BEA4288AA88EB54EFE829686553100A75FDF09D11C5E3BF6B329BADB9A0368DD` |
| agent `runtime-types.d.ts` | `7C03F0F92BE4A48CC7960AC02FC040B2088B462AE790EAB1427E50BFE5E74B31` |
| session `types.d.ts` | `8E3B1B7F54D504CA91D3496376F9EA619F99CE1AFE2739D35D9C2F2F69320950` |
| approval `types.d.ts` | `5F39FA9E221D6759ACBB9DC1DB473DB0C431A2BDF48BBD8FFED8AA4194B1345F` |
| questions `projection.d.ts` | `C08CA4620CF8A0122AF7B86EBD54A85297D68C54C8D7920FB7A718DE700C946C` |
| web `cordis.patch.yml` | `3E1F923309612ED8551141127409D662E78758E2D0D125218A3F70514417E472` |

支持矩阵现状：上述能力已完成静态核查；启动装载、真实事件顺序、异常传播、审批、两种提问模式、USB 端到端均未执行。实现阶段将依赖版本与包 integrity 写入 lockfile，并以合约通过为支持依据。

## 4. 架构和模块边界

数据依次经过：DSH Host 观察器 → 版本适配器 → 白名单事件 → Worker outbox → HTTP → Python PC 服务 → USB v1 → 固件。

| 模块 | 责任 |
|---|---|
| `index.ts` | `apply(ctx,config)`、Host 装载、服务注入、释放监听器和 Worker |
| `adapter-0.2.1-rc.2.ts` | 精确版本事件签名、顶层 Agent 过滤、回合/审批/问题识别 |
| `identity.ts` | Agent 对象与实例 UUID、上游 turn、请求 ID 的映射 |
| `normalize.ts` | 按白名单创建新对象；禁止转发原始事件 |
| `reporter.ts` | 同步不抛异常的入队入口、activity 合并、有界内存及故障状态 |
| `worker.ts` | 文件 I/O、顺序号、分段 WAL、恢复、HTTP、重试和 checkpoint |
| `diagnostics.ts` | 能力位、计数、枚举错误；不保存原始异常正文 |
| PC ingress / source contracts | 接受各适配器的统一事件，校验来源身份、schema 和能力声明；不解析厂商原始事件 |
| PC event service | 与 Agent 产品无关的幂等、实例代次、等待集合、完成期限、数据源健康、聚合 |
| PC SerialWorker | 唯一串口写入者、ACK/revision 对账、心跳和重连 |

插件以 ESM TypeScript 包交付，建议包名 `agent-light-dsh`。DSH/Cordis 使用精确验证过的 peer dependency，不把另一份 Cordis 打包进插件。Worker 构建为独立 JS 文件，路径相对模块 URL，支持安装目录含空格。

插件使用 Host 生命周期和公开 session/projection 观察点。需要跨 Agent 接收的 scoped 监听器采用锁定版本支持的全局订阅方式，并显式过滤 `ctx.agents.roots()` 的精确对象。不得 monkey patch `approval.request`、`userQuestions.ask` 或 DSH 私有方法。

## 5. 身份、回合和监听顺序

### 5.1 身份

- `producer_id`：一次插件安装的数据源 UUID，保存在 outbox 元数据；不含目录、账号或机器名。
- `runtime_id`：每次插件启动的新 UUID，用于数据源健康租约；`runtime_seq` 是 Worker 持久化分配的递增启动代次，同时进入事件与心跳。
- `session_id`：该 producer 的随机 HMAC 密钥对 DSH session ID 的摘要，稳定且不包含原始路径。
- `instance_id`：每个实际顶层 Agent 对象生命周期的新 UUID。
- `instance_seq`：同一 producer/session 的单调递增代次，由 Worker 分配、持久化。不要比较 UUID 或墙钟先后。
- `turn_seq`：正常回合取该实例内的 DSH turn 数字；`turn_id` 为实例内的固定字符串映射。初始恢复等待使用保留的 `turn_seq=0, turn_id=bootstrap`。
- `attention_id`：`approval:` 或 `question:` 命名空间加请求 ID 摘要。阻塞旧式问题没有稳定 call ID 时，由观察器在该次 waterfall 进入时创建 UUID。
- `event_id`：一次规范化事件创建时生成，持久重试不重新生成；`producer_seq` 连续递增并持久化，用于同一生产者排序。

单 outbox 单 Worker、单写入者；第二个共享同一 outbox 的插件必须禁用自己的采集并给出枚举诊断，不阻断 DSH。本阶段不支持两个独立 Web 后端共享一个 producer。

### 5.2 装载与恢复

1. 启动时检查兼容版本和配置，注册观察器，再接受新的 Agent 创建事件。
2. 若装载时已有 live Agent，首版报 `RESTART_REQUIRED` 并不开始部分追踪；不把截断的历史当完整会话。
3. `agent/created` 后仅为运行时 root 建立实例。Worker 必须把 `session_start` 放在该实例其他事件之前。
4. 过去的历史 `turn/end` 不作为本次完成提醒；resume 初始化为 IDLE。已有 `userQuestions.active` 中的 `continued` 问题重建在 bootstrap 回合，其后仍能由匹配 ID 解除。bootstrap 必须在同一个 `agent/created` 同步监听器中完成：先标记 initializing，读当前官方投影，只选取 ID/state，按 `session_start → bootstrap attention_open → instance_initialized` 的顺序放入本地队列，然后再返回。初始化时的重入通知暂存到有界队列，在上述三步之后处理；DSH 的 created 链返回前不会释放 queued turn。不能把首次 bootstrap 放到普通 projection 的延后差分任务中。

   `instance_initialized` 是插件内部队列屏障，不新增 HTTP 事件。PC 只在 session_start 后且该实例首个真实 turn_start 前接受 turn_seq=0 的 bootstrap open；首个真实回合提交即永久关闭此初始化例外。后续仅允许既有 bootstrap attention 的精确 resolve。读投影失败或缺少所需 key 时标记源 degraded，不补造“空等待”。投影可能懒计算，长历史 resume 的这次内存读取计入 created 同步开销验收；不能以“没有网络 I/O”冒充已满足延迟目标。
5. 新实例 `session_start` 的更大 `instance_seq` 原子替换同 producer/session 的旧实例显示贡献，关闭旧实例等待并保留历史诊断。较小代次事件返回 stale。
6. 同一插件重启先恢复旧 outbox 的完整记录并按顺序发送，再发送新实例事件；重新连接 PC 不重新创建 Agent 实例。
7. `agent/disposed` 只表示离开 registry，不证明进程正常退出。记录 `session_end`，`reason_code=agent_disposed`；PC 关闭该实例等待、撤销 RUNNING，已确定的 ERROR 保留，普通完成按既有 session_end 规则撤销。
8. 不使用插件 unload 伪造所有 Agent 正常结束；被强杀时没有 dispose 事件，由数据源健康机制表明信息失联。

启动交接需要一个明确屏障：Worker 完成恢复后，按同一 FIFO 处理“旧记录 → 当前启动已接受的初始化事件 → runtime_ready 控制记录”。控制记录包含 `runtime_id/runtime_seq`、截至该切点的 `producer_seq` 和该新 runtime 的完整 live instance ID 清单，只存不透明 ID；也先落盘。注册监听器后同步读取 roots 并排入这个屏障，切点之后创建/释放的 Agent 按普通顺序事件处理，不存在跨 await 的枚举空隙。首版禁止带 live Agent 热加载，因此冷启动清单允许为空。

PC 仅在屏障之前的记录全数终局处理且清单引用的 session_start 存在时，原子接受 runtime_ready：切换该 producer 的显示权到新 runtime，撤下旧 runtime 的全部业务显示贡献（包括未恢复会话、等待和错误墓碑），保留其历史；随后才允许新 runtime 的 healthy 心跳撤销 recovering 故障。后续旧 runtime 事件只作 stale 确认，不影响显示。屏障重放必须幂等；低 runtime_seq 屏障不得抢回权力。这是数据源重启的替换规则，不伪造旧聊天成功/正常结束。

创建监听器是 DSH 串行链的一部分，因此只做上述元数据投影读取、白名单提取和有界入队，不等待磁盘、HTTP 或 USB。正常事件不重复扫描历史。所有观察器捕获自身错误，不把 reporter 异常传给 DSH。

## 6. 事件映射与灯态语义

### 6.1 基本生命周期

实现勘误（2026-11-06 联调）：`turn/end.data.reason` 是带 `kind` 判别字段的对象，必须读取 `data.reason.kind`；不能把整个 reason 当作字符串枚举。不得复制其中 error/reason 的正文。测试 fixture 必须沿用该真实结构。

| 已核实输入 | 规范化结果 | 说明 |
|---|---|---|
| `agent/created` | `session_start` | 仅 root；resume 不重放旧完成 |
| `session/event: turn/start` | `turn_start` | 使用 `data.turn`；比 pre-step 更准确，包含零 step 的回合 |
| `step/start`、`step/end`、assistant-stream | `activity` | 仅 ID/枚举，按实例最多每秒一次，不读取 chunk |
| `agent/request-error` | 诊断计数 | 失败 attempt 可能重试成功，不建立终态 ERROR，也不参与 waterfall |
| `turn/end: completed` | `turn_complete` | 只有这个结束原因点绿灯 |
| `turn/end: error` | `error` | `reason_code=turn_failed`；不读取 error.message |
| `turn/end: aborted` | `turn_cancelled` | 标准取消原因枚举；不冒充成功或系统错误 |
| `turn/end: blocked` | `error` | `reason_code=turn_blocked`，表示本轮未完成；不是未解决审批的替代物 |
| `turn/end: max-tokens` | `error` | `reason_code=output_limit`，表示结果未完整完成 |
| 历史 `interrupted`、`forked` | 不当 live 终态上报 | 属于恢复/seed 标记；不借此点亮新的完成提醒 |
| 未识别的结束原因 | 数据源 degraded | 不猜测成功；能力诊断 `UNSUPPORTED_END_REASON` |
| `agent/status` | 活性辅助信息 | idle 不能覆盖完成或等待，不单独等于 turn_complete |
| `agent/disposed` | `session_end` | 不对外宣称正常进程退出 |

工具的失败结果可能被 Agent 自行处理，因此普通 `tools/result` 不直接映射 ERROR。无需为了采集活动接入 `tools/pre-execute` 决策链。

### 6.2 审批

监听 `session/event` 中 `approval/asked` 与 `approval/decided`，读取 `data.id` 及 outcome 枚举：前者打开等待，后者精确解除同一个等待。

`allowed-once / rejected / cancelled / unavailable` 都表示该请求已经结束，不表示任务成功。拒绝之后 Agent 是否失败由最终 turn/end 决定。机器自动审批也可能产生短暂 open/resolve；首版保持真实顺序，不靠延时猜测是否由人回答。

### 6.3 提问：两条独立适配路径

**两条路径的确定性分类：**本机锁定包的官方 timed 工具总是传 `request.wait.callId`，包括 `timeout=-1`；legacy 工具不传 wait。只根据该元数据分类，不读取问题文本、回答或工具参数。具有 wait 的路径同时使用前台等待观察器和 projection，二者共享同一个 callId attention；不产生第二条等待。自定义第三方问答工具不在首版保证范围。

**timed 模式：**在 `user-questions/request` 进入时立即用 wait.callId 打开等待。这是必要的，因为 PTC 内层调用可能直到返回 pending 后才进入官方 projection。观察器同时监听该请求的 signal：前台 signal 以 `UserQuestionError.code=ASK_TIMED_OUT` 取消，或 next 直接以该 code 拒绝，均立即进入 continued 并解绑前台 signal，保留等待。外层 askTimed 在返回 pending 时会在 finally 执行 wait.close(abortedQuestion())；其随后产生的 ASK_ABORTED 是清理行为，绝不能解除 continued 或生成 resolved tombstone。

仅在仍处于 foreground 时，非超时 signal 取消才撤回等待。`next()` 在 foreground 且 signal 尚未取消时成功返回，解除为 answered；`wait.timed=true` 时 `NO_PROVIDER` 拒绝也必须保留 foreground，因为外层 askTimed 会继续等到超时，并非请求已结束。此时 signal 监听器不能随 waterfall 的 finally 提前移除。其他非超时拒绝解除为 withdrawn；超时或取消后的迟到 answerer 返回不改变状态。只读允许列表内的错误 code，不读取异常正文，原返回值和异常原样传递。`wait.timed` 缺省的无限等待不走 NO_PROVIDER 恢复分支。

每个定时请求有明确的本地阶段：foreground → continued → resolved，或 foreground → resolved；NO_PROVIDER 仍为 foreground，超时变 continued，前台非超时取消变 resolved。continued 的后续解除只能来自投影中的答案/撤回、所述 turn/end 完整核对或实例结束，不再依赖已经结束的前台 signal。清理 signal 监听器时机是 observed settlement、确认超时、signal 实际触发、实例结束或插件卸载，不是无条件 finally。该状态只服务于事件配对，PC 仍是最终灯态权威。

继续观察官方 `userQuestions` projection 的变化，只提取 `active[].callId/state` 和 `settled[].callId`；不复制 questions 或 answers。`open → continued` 不解除等待；进入 settled 生成 `attention_resolve(answered)`。曾经被官方投影接纳的 active ID 消失且不在 settled，按投影终止语义生成 `attention_resolve(withdrawn)`；projection 整体缺失或服务卸载不能当成全部消失，而是数据源 degraded。前台已解除的 ID 保留本实例 tombstone，不能因投影通知稍晚再次打开。

PTC 中仅在前台观察到、尚未进入官方 projection 的 callId，在所属 turn/end 后的有界延后核对中读取完整当前投影：若仍不在 active/settled，则关闭为 withdrawn（本轮未提交可继续回答的问题）；存在 continued 则跨回合保留。投影缺失时不执行这个负面推断，直接 degraded。必须测试外层 run_code 成功、失败、取消和 pending 提问这四种结局。

投影通知可能早于普通 session 监听器：观察器先标记该 session 需要更新，在当前同步事件分发结束后的有界队列中读取最新投影，并对 callId 差分；短暂 open/settled 在同一轮内已结束可以不点红，不得丢失仍在 active 的等待。使用 `seq` 水位抑制旧通知。只有已追踪的 ID 能被差分关闭。

**legacy 阻塞模式：**通过同一公开 waterfall 包装单次等待，进入生成 attention UUID，调用并原样返回 `next()`，成功/抛出时在 finally 中解除对应 ID；signal 取消也解除，不能等待不响应取消的 answerer 才关灯。reporter 的错误必须被独立捕获，保留原返回值和原异常。

Cordis 已核实支持 `prepend:true` 和 `global:true`，观察器用两者先于 Web answerer 接入，且严格只调用一次 next；真实装载顺序仍须合约测试证明。正常 finally、signal、投影三条结束路径共用幂等 finish。缺失必须的 projection 能力时 timed 标记 unsupported，不能退回“finally 一律解除”的错误逻辑。

### 6.4 PC 状态规则

- 跨顶层聊天：`ERROR > ATTENTION > RUNNING > COMPLETED > IDLE`。
- 同回合终态单调：`ERROR > COMPLETED > CANCELLED > RUNNING`，ERROR 不被 complete/cancel 覆盖。
- `turn_cancelled` 将该回合基础状态改为 CANCELLED，视觉贡献 IDLE；等待集合独立保留。
- 更高回合开始重置该实例基础状态为 RUNNING，但不解除旧的 continued 等待。
- 解除等待按 `(producer, session, instance, attention_id, origin_turn)` 匹配；允许匹配记录属于已过去的回合。resolve 事件携带原始 turn，而不是回答到达时的新 turn。
- 同 producer 有序上报正常不会先 resolve 后 open；PC 仍保留 resolved tombstone，重复/乱序 open 不得复活已解决的同 ID。
- 新来但旧回合的 attention_open 默认为 stale；resume bootstrap 创建是明确定义的初始化，不借旧事件复活等待。
- COMPLETED deadline 由 PC 在首次有效接收时持久化；重复上报与服务重启不重新开始 300 秒。长时间离线补报的完成提醒仍保持一次 300 秒，此为首版选择。
- LED 与亮度按 USB v1：空闲灭、运行黄常亮、等待红常亮、失败红 2 Hz、完成绿常亮。

## 7. PC HTTP 合约草案

这是待实现的合约，不表示现有项目已有这些端点。统一事件 schema 尚未冻结，因此仍计划使用 `schema_version=1`，同时以本文件明确修订旧草案。

事件公共字段：`schema_version,event_id,agent,channel,producer_id,runtime_id,runtime_seq,producer_seq,session_id,instance_id,instance_seq,turn_id,turn_seq,attention_id,type,occurred_at,reason_code`。`agent` 的首版 schema 预留 `dsh|codex`，`channel` 预留 `plugin|hook|wrapper|cli`；当前 DSH 适配器固定发送 `dsh/plugin`。允许协议标识不等于已经验证该产品适配器。非适用字段为 null；按事件类型定义必填约束，`additionalProperties:false`。ID 最长 128 ASCII 字符，JSON 单事件上限 2 KiB，seq/turn 使用非负 safe integer；超过范围必须停止该源并诊断，不静默溢出。

`runtime_ready` 是同一端点中的独立控制记录变体，字段只有 schema_version/event_id/agent/producer_id/runtime_id/runtime_seq/producer_seq/type/live_instances；不套用业务 session 字段。其请求上限 64 KiB，最多 32 个 live instance，引导时不与业务事件混在 batch 中；正常业务容量仍为 16 个，32 个为压力测试目标。

新增 `turn_cancelled`；`session_end` 增加 `outcome=disposed`，避免把未知的进程退出原因写成 normal。保留旧方案的 normal/abnormal 给有实际进程退出证据的未来 wrapper；disposed 不得降级已有 abnormal/error。

| 端点 | 合约 |
|---|---|
| `GET /v1/health` | 协议/schema 版本、可接受事件类型、来源能力与验证状态、DB 就绪；明确区分预留协议与已验证适配器，不返回 token |
| `POST /v1/events` | 单事件；200 返回 `{event_id,status}`；status 为 applied/duplicate/stale；202 pending_identity 非最终确认 |
| `POST /v1/events/batch` | 最多 32 条且总计 ≤64 KiB；逐条按输入顺序事务提交，返回逐 event_id 的相同语义 |
| `POST /v1/producers/heartbeat` | 独立的小型健康请求，含 agent/producer_id/runtime_id/runtime_seq、健康枚举、已持久化 seq、已最终确认 seq；仅更新源健康，不伪造 session 状态 |
| `GET /v1/status` | 会话聚合、源健康、队列水位、desired/acked revision |

服务必须在 inbox/FSM/display 的 SQLite 事务提交后才返回最终确认。重复相同 event_id/body 返回 duplicate；相同 ID 不同 body 返回 HTTP 409，不能覆盖。stale 是已终局拒绝旧代次，允许消费。pending_identity 必须保留并重试；不能因为记录已存在就返回 duplicate。

HTTP worker 同时一个事件请求，正常立即发送首条并最多合并 20 ms；重试维持相同事件 ID/内容。成功响应仍要校验每个 ID 和枚举，缺项或畸形响应不推进 checkpoint。

错误处理：网络/超时/5xx 重试；429 尊重有界 Retry-After；401/403 暂停事件发送并报告鉴权故障；400/413/422/409 保存为隔离记录并使该 producer degraded，不静默跳过关键事件后继续假装健康。事件请求总超时默认 200 ms，退避 0.25、0.5、1、2 秒后上限 5 秒，加入 ±20% 抖动。

数据源健康：每 2 秒发送心跳，PC 以接收端单调时钟判断 15 秒失联。正常启动先置 recovering，runtime_ready 最终确认后才可转 healthy。degraded/租约失联作为独立诊断故障贡献 ERROR，并保留最后业务状态；不把它写成某个聊天失败，不标正常结束。重新 healthy 后撤销诊断贡献并恢复业务聚合。PC 自己重启后先给已知源 15 秒重新登记窗口，不能用本机重启前单调时间戳直接判定。

同一 producer 新 runtime 心跳替换旧 runtime 的健康租约，但在新 runtime_ready 提交前不得拒收 Worker 正在顺序回放的旧 runtime 事件。业务会话新旧由 instance_seq 判断，整次启动交接由 runtime_ready/runtime_seq 判断。旧 runtime 心跳不得抢回当前租约：PC 分别保存最高已注册 runtime_seq 和最高已完成屏障 runtime_seq，healthy 必须匹配后者；不允许新心跳提前充当屏障。

### 7.1 为 Codex 预留的通用接入边界

Python 上位机的核心入口是统一事件协议，而不是 DSH 专用 API。未来数据流为“Codex 版本适配器 → 相同 /v1/events 或 batch → 相同 FSM/聚合 → 相同 SerialWorker”。适配器可以由外部插件、Hook bridge 或 CLI 组成，选择必须等目标 Codex 版本核查；这里不假定当前 Codex 已提供某个 Hook 或插件接口。

PC 端规划三个明确的内部边界：

| 边界 | 输入/输出 | 不承担的工作 |
|---|---|---|
| `SourceContract` | agent、adapter_version、schema_version、能力位、健康模式、验证状态 | 不写入厂商聊天内容，不自动信任任意声明 |
| `EventIngress.accept` | 校验后的统一事件 → applied/duplicate/stale/pending_identity | 不解析 DSH/Codex 原始 payload，不猜审批结果 |
| `StateReducer.apply` / 聚合器 | 统一事件与已登记的来源能力 → 会话状态与目标灯态 | 不根据 agent 名称写厂商专用分支，不直接操作串口 |

SourceContract 由受控配置与版本适配器的合约结果登记；能力位至少包含 session lifecycle、turn outcome、attention open/resolve 配对、cancellation、liveness。预留字段不代表对应能力已经实现。缺少明确审批解决事件的适配器不能宣称自动等待恢复，普通 activity 不得补造 resolve；没有可靠最终结果也不能把任意停止通知转成成功。

所有表和控制操作采用完整来源作用域：producer 主键为 `(agent,producer_id)`；实例为 `(agent,producer_id,session_id,instance_id)`；runtime_seq/instance_seq、等待记录、健康租约、runtime_ready、清理与重放均限定在这个作用域。事件去重键为 `(agent,producer_id,event_id)`，同键不同 body 仍冲突。DSH 重启只撤下对应 DSH producer 的贡献，不能清空 Codex 或另一来源。`channel` 仅标注传输方式，不把同一任务拆成多个实例；未来 hook/wrapper 共用持久身份映射。

健康租约是“采集源是否在线”，不是“每个聊天是否还活着”。未来若采用短命 Hook 进程，心跳、outbox、runtime 与实例身份由持续运行的 bridge/collector 维护；每次 Hook 执行不得新建 runtime、触发 runtime_ready 或令聊天 session_end。collector 自身重启时，必须先恢复/核对其仍负责的实际会话基线，再提交 runtime_ready；不完整就保持 recovering，不能套用 DSH 冷启动的空清单清理活跃的外部任务。

DSH 和未来 Codex 可同时向服务上报。默认跨来源使用同一优先级 `ERROR > ATTENTION > RUNNING > COMPLETED > IDLE`；`GET /v1/status` 既返回各来源摘要，也返回总灯态。当前 16 个正常并发实例的容量预算是上位机全局预算，不能每接入一个新来源就隐式倍增承诺。

协议兼容规则：/v1 下保持已发布字段与事件语义兼容；新增可选能力通过 SourceContract/health 声明，未知事件明确拒绝。未来若需要改变身份、终态或等待的含义，使用新的 schema/API 版本并提供兼容适配，不让升级 Codex 插件迫使已安装 DSH 插件或 USB 固件同时升级。首版只定义和验证通用边界，不搭建动态 Python 插件加载框架。

## 8. outbox、非阻塞与真实保证

### 8.1 两个不同边界

DSH 回调只复制白名单标量并向 Worker 入队，不 await。**回调返回不代表事件已落盘。** Worker 将记录 append 到 JSONL segment 并 fsync 后，才允许发送 HTTP；只有服务最终确认且 checkpoint 持久化后才能回收记录。

保证范围是“成功落盘记录的至少一次投递 + PC 幂等处理”，不是整个 DSH 回调的零丢失，也不是 exactly-once。DSH 在回调后、Worker fsync 前被强杀，最后一批可能丢失；同样，断电下 DSH 自己的历史也未必已持久化。首版不通过同步 fsync 阻塞 Agent 来掩盖该边界。

### 8.2 容量和磁盘

- 主线程待确认入队窗口最多 4096 条、8 MiB（取先达到者），Worker credit 控制，不利用无界 MessagePort 当隐藏队列。
- activity 在入队前按实例合并，每秒最多一条；关键事件不得挤掉另一个已接受的关键事件。
- 达到容量先抛弃/合并 activity；仍无法容纳关键事件则立即标记 `CAPTURE_OVERFLOW`，数据源 degraded，停止宣称可靠采集。故障状态通过独立、固定大小控制槽传给 Worker；Worker 本身失效则由心跳失联体现。DSH 继续运行。
- 单 segment 目标 1 MiB；spool 默认上限 64 MiB。已持久化未确认数据不因上限被删除。磁盘写失败/空间不足采用相同 degraded 策略，需修复后重启采集并重新建立会话基线，不能悄悄跨过缺口。
- 关键事件驱动立即落盘，activity 可 100 ms 合并落盘；Worker fsync 可把同一批关键记录一起提交。正常回调路径目标 p95 ≤2 ms、p99 ≤10 ms、max ≤50 ms；这是需测量的验收目标，不是 OS 最坏时延保证。

### 8.3 恢复与回收

记录封套包含格式版本、固定白名单事件、长度和校验摘要；JSONL 末尾半行在恢复时截断到最后完整且校验通过的记录，中间损坏隔离并 degraded，不跨损坏继续投递。

checkpoint 保存已最终确认的连续前缀、producer/instance/runtime 计数器和格式版本，采用临时文件写入、fsync、原子替换。保留上一版校验有效的 checkpoint；Windows 上替换/目录元数据耐久边界通过故障注入确认，不声称断电时任意文件系统都原子耐久。可以重放重复，不能越过未确认记录删除。

segment 仅在其全部事件终局确认、覆盖它的 checkpoint 已持久化后删除。删除前必须保证最新身份计数器已独立保存在有效 checkpoint，不能因清空 outbox 重用 instance_seq。ACK 后、checkpoint 前崩溃只造成重放，不改变事件 body。

干净卸载停止新观察、提交剩余队列，最多等待 500 ms 的本地落盘；不等待网络 drain，不阻塞 DSH 无限退出。窗口内未完成落盘的尾部风险明确计数。强杀依靠已有 segment 恢复，不承诺能执行退出回调。

## 9. 配置、路径与隐私

首版配置建议：`enabled,endpoint,tokenFile,dataDir,requestTimeoutMs,activityIntervalMs,maxSpoolBytes`；endpoint 默认 `http://127.0.0.1:17321`，端口冲突允许配置。只允许 IPv4 loopback literal，禁用重定向和代理转发，token 不发送到重定向目标。

认证使用 PC 生成的随机 Bearer token。插件保存 tokenFile 绝对路径，Worker 读取；token 不进入事件、spool、diagnostics 或安装示例。PC 只绑定 loopback，限制请求体和请求速率。

`dsh.cmd` 改写 APPDATA/LOCALAPPDATA/HOME，所以不能让插件与 PC 分别猜默认用户目录。PC 配置初始化时生成真实绝对 `tokenFile` 和 `dataDir`，安装引导把同一组路径写入用户选择的 web overlay。ACL 限制当前用户和必要系统主体；插件无需管理员权限。

事件与文件不保存：prompt、message、chunk、tool arguments/result、问题与回答、error.message/stack、cwd、文件路径、模型输出、Bearer token。投影读取只在进程内选择 ID/state；严禁 JSON.stringify 原始 event/projection/error。诊断仅白名单枚举、计数、时间和不透明 ID。

## 10. 配置接入与支持策略

生成包的 `cordis.patch.yml` 只向 web 的 Host 插入一个插件节点，唯一固定 id，配置引用上述绝对路径。必须验证包 manifest 的 `dsh.bundle.patch` 及实际 profile 装载规则，再生成安装命令；`dsh plugin --profile web add <本地包>` 仅是已由 CLI help 验证的命令形式，不把“安装依赖”误当“成功加载 Host 插件”。

开发先使用用户可审阅的独立 overlay 与 `--patch` 形式，在受控测试 profile 检查装载一次；正式启用才备份并修改用户选定的 web 配置。安装路径含空格、重复启用、禁用恢复必须验证。当前设计任务不修改这些文件。

不匹配验证过的 DSH/Cordis 版本时 fail-open for DSH：禁用采集并诊断 `UNSUPPORTED_VERSION`。兼容性不能只检查 CLI semver，还需确认目标依赖解出的版本/签名；升级必须重跑合约，不能自动落回猜测事件。

## 11. 对既有方案的明确修订

批准本设计后，下列内容替代 `outputs/agent-indicator-design.md` §8 及 execution-plan 的相应 DSH 条款；USB 合约不变：

1. 用真实 `turn/start` 代替以首次 pre-step 猜回合起点。
2. request-error 仅记录重试诊断，以最终 turn/end.reason 判断失败。
3. 按 completed/aborted/error/blocked/max-tokens 分流，增加 turn_cancelled。
4. attention_resolve 可匹配仍存在的旧回合等待，以支持 continued 提问；不因新回合自动解除。
5. agent dispose 仅提供 disposed 生命周期事实，不提供正常/异常进程退出证据。
6. 增加 instance_seq、runtime_seq 和源健康租约，明确崩溃/网络故障与任务失败的区别。
7. 修订“所有事件先持久化”的精确含义：发送 HTTP 前持久化，DSH 回调到 Worker fsync 存在有限易失窗口。
8. 容量耗尽导致可见的采集故障；不承诺在有限内存、磁盘失效且不阻塞 Agent 时仍绝不丢事件。

上述修订必须同步写入后续 event-schema 与 FSM，不能只改插件而让 PC 继续按旧语义运行。

## 12. 交付物与实现依赖

设计批准后才能编写实现计划。建议后续交付结构：

```text
contracts/
  event-schema.json
  fsm-transitions.md
  source-contract.schema.json
  dsh/0.2.1-rc.2/capabilities.json
  dsh/0.2.1-rc.2/sanitized-fixtures/
plugins/dsh/
  package.json + package-lock.json
  cordis.patch.yml + tsconfig.json
  src/{index,adapter-0.2.1-rc.2,identity,normalize,reporter,worker,diagnostics}.ts
  tests/{contract,mapping,outbox,privacy}/
  README.md
pc/agent_light/
  ingress/       # 与来源无关的校验和接收入口
  sources/       # 来源能力、健康和身份作用域
  core/          # 状态机与跨来源聚合
  transport/     # 唯一 USB/串口 worker
```

插件的单元/真实包合约可用伪 HTTP receiver 独立开发。真实控灯还依赖 Python PC Core、上述 HTTP/FSM、SQLite 和串口 worker；不能把“插件能加载”宣称为“上位机完成”。GUI、托盘、开机启动和发布打包另列后续工作。

由实现者决定：测试框架、内部类名、构建工具、模块细分、可靠进程锁实现及日志轮转细节。不能自行改变：A 方案、内容隐私、灯态/取消语义、持久化边界、单串口权威、版本门禁及首版追踪范围。

## 13. 验收矩阵

| 层级 | 必测内容 | 成功标准 |
|---|---|---|
| 真实包合约 | Cordis Host 插入、全局 scoped 监听、created/disposed、projection 顺序、legacy 包装顺序 | 锁定包内无猜测签名；仅装载一次；与 Web answerer 的顺序有执行证据 |
| 生命周期 | 无工具完成、连续两轮、零 step 结束、失败后新轮、重试后成功、取消 | 黄→绿；最终失败红闪；重试恢复不粘住红灯；取消不点绿 |
| 审批 | asked A、活动、decided B、decided A；自动允许、拒绝、取消 | 仅 A 能解除 A；原批准/拒绝行为不变 |
| 提问 | legacy 成功/异常/取消；timed open→continued→新轮回答；NO_PROVIDER 继续等待；answerer 抛 ASK_TIMED_OUT 后 wait.close 发 ASK_ABORTED；PTC 外层成功/失败/取消；多问题并存、projection 卸载 | 超时、清理 abort 和新轮不解除等待；只解除匹配 ID；未知能力不伪造答案 |
| 身份 | 恢复同 session、新 instance、迟到旧 instance、已有 lineage 的 root、普通 child；强杀后不恢复旧聊天；bootstrap 后立即新轮 | 不串态；不把 child 独立完成当 root 成功；旧 runtime 贡献在屏障后撤销；bootstrap 不被首轮吞掉 |
| 通用来源接口 | 模拟 dsh/codex 事件使用相同 session/event ID；一个源重启或失联；不同 channel 共享实例 | 跨来源无键冲突、清理不越界、全局优先级正确；仅证明通用合约，不能宣称真实 Codex 支持 |
| 服务/重放 | PC 离线、ACK 丢失、重复、pending_identity、畸形 ACK、409、401、429、5xx | 已持久化关键记录保留；连续前缀正确；故障可见 |
| 故障注入 | append/fsync/HTTP/ACK/checkpoint/segment GC 前后 kill；半行、磁盘满、Worker 退出 | fsync 后记录可恢复；不推进过未确认记录；采集缺口不能假装 healthy |
| 行为不变 | 相同输入在有无插件下的工具、审批、异常、回答结果 | 业务返回值/原异常/退出码不变；无未处理 rejection |
| 隐私 | 原始内容各域注入不同 canary | 插件 spool、HTTP、日志、PC DB、USB 里零命中 |
| 性能 | 正常与服务黑洞时 16 root 并发，32 root 压测 | 同步开销 p95≤2ms/p99≤10ms/max≤50ms；稳定内存；无回调等待磁盘/网络 |
| E2E | 真实 DSH Web + PC + 用户实板 | 30 个完整回合；Agent→灯 p95≤300ms/p99≤600ms/max≤1s；16 会话聚合正确 |

真实 DSH 用无敏感测试数据，先用可控 provider/answerer 完成错误与取消用例，再做真实 Web 交互。fixture 只收元数据与枚举，不录制原始内容再事后脱敏。合约未通过的能力在 capabilities 中标记 unverified/unsupported，不能标 supported。

## 14. 交付时需向用户突出说明的选择

1. 首版追踪全部顶层聊天，子 Agent 不单独计灯态。
2. 用户取消不显示绿色；未回答的 continued 提问仍保持等待。
3. 采集源失联/故障显示红闪，并在上位机诊断中与聊天失败区分。
4. 回调不阻塞；强杀发生在 Worker 落盘前时可能丢失尾部事件，已落盘记录可补报。
5. 绿色 300 秒、亮度 35%；PC 服务尚需另行实现才能实际控灯。
6. 用户要求的 Codex 接口已纳入：统一事件入口、来源能力声明、来源隔离与混合聚合；真实 Codex 插件后续单独核验和实现。

设计审批前不创建产品代码、安装依赖或修改运行中的 DSH profile。

## 15. 设计检查记录

已按 Superpowers builder-check 由独立审阅者检查可实施性，并修订：新 runtime 的完整交接屏障、timed/PTC 提问前台与投影交接、bootstrap 的同步初始化顺序，以及 ASK_TIMED_OUT 后清理 abort 不得误解除等待。以上是文档审阅和已安装源代码静态核查；不是构建、合约测试或实板验证通过记录。

用户随后要求预留 Codex 接入，已在 §7.1 补充通用接口并同步公共字段、控制消息、作用域和验收矩阵。本轮补充完成文档一致性检查，尚未执行真实 Codex 接口核验或运行测试。
