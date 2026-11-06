# DSH 持续红闪修复 v0.1.2

现场：USB connected=true/serial_diagnostic=OK，业务 sessions 为空；来源 runtime_seq=1/2、ready_seq=-1、persisted_seq=acked_seq=0，心跳过期。红闪为独立的采集源健康故障，非聊天最终错误。

修复启动期间的 root 竞态：在 Worker await 前注册冷启动 created 屏障；新 root 在官方 serial 创建边界等待初始化完成。Worker 就绪后先建立 root/bootstrap 基线，再按 FIFO 发送包含完整实例清单的 runtime_ready，最后释放首轮。保留真正热加载已有 live Agent 时的 RESTART_REQUIRED。冷启动最多受 Worker 5 秒超时限制；正常事件路径不等待磁盘/网络。

新增白名单启动诊断，仅 code/phase/time。修订 smoke 使用真实 AgentRegistry、Session、SessionProjectionRegistry、正式 question 投影以及 PluginPackages 路由；生命周期通过 Session.append 生成。新增 startup-race probe，确认 Worker 启动期间创建的 root 依次发送 session_start → runtime_ready → turn_start → turn_complete。

随后真实对话发现第二处缺陷：运行黄灯、结束后红闪；来源进入 degraded，spool 只有 session_start/turn_start/activity，没有终态。核对 SDK 的 TurnEndReasonMap 确认 reason 是 `{kind: 'completed'}` 等对象，原适配器误按字符串索引，触发 UNSUPPORTED_END_REASON。已改为仅读取 reason.kind；不读取/复制其错误正文。原 fixture 和 smoke 同步改为真实判别对象，并增加五类终态回归。

验证：TypeScript 构建通过、5 项检查通过、真实服务 smoke 的 RUNNING → ATTENTION → COMPLETED 通过、startup-race probe 通过。

最终现场确认：用户完成真实第 3 回合后反馈“完成后绿灯”。PC status 同时确认 base=desired=COMPLETED、source health=healthy、lease_expired=false、persisted_seq=acked_seq=81、desired revision=acked_revision=21、connected=true。此为真实 DSH 对话 → 插件 → 上位机 → 灯板的一次运行黄/结束绿验证，不扩大为完整验收矩阵通过。

现场于 2026-11-06 17:30（Asia/Shanghai）重新启动 DSH 后，来源 runtime_seq=ready_seq=3，health=healthy，启动记录 persisted_seq=acked_seq=1，lease_expired=false；设备 ACK IDLE revision=11。已解除持续红闪并恢复在线。真实用户回合继续观察，不把合成测试当实板聊天验收。

本轮为了捕获现场启动状态，将原测试 DSH 后端重启为隐藏后台进程。启动脚本位于 outputs/dev-runtime/diagnose/launch-dsh.ps1，只保留 [agent-light] 白名单行；不保存启动 URL/token 或聊天输出。上位机未重启，用户真实 profile 未修改，outbox 未删除。

本次后台 DSH Node PID 为 38300；需要停止时可在核对该 PID 仍属于本次 DSH 后执行 `Stop-Process -Id 38300`，然后照原命令在自己的终端启动。上位机仍由用户原终端控制。v0.1.2 npm 构建产物已更新。
