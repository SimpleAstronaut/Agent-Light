# agent-light-dsh v0.1.3

仅适配本机核查的 DSH 0.2.1-rc.2 / Cordis 4.0.5；启动检查实际宿主依赖版本和文件 SHA-256。版本不符时停用采集，不阻止 DSH。默认只观察所有顶层 Agent，子 Agent 不独立计灯态。

项目总览与完整使用手册见 [根目录 README](../../README.md)。2026-11-06 已完成真实对话“运行黄灯、完成绿灯”联调；此结果不扩大为全部审批/提问/PTC 与性能验收通过。

构建（项目根目录）：

```powershell
Push-Location plugins/dsh
npm.cmd ci --legacy-peer-deps --ignore-scripts --no-audit --no-fund
npm.cmd run build
npm.cmd run check
npm.cmd pack --ignore-scripts
Pop-Location
```

先按 PC README 初始化配置、启动服务，再生成独立 overlay：

```powershell
pc/.venv/Scripts/agent-light overlay | Set-Content -Encoding utf8 outputs/agent-light.local.patch.yml
```

本机已将默认 overlay 接入 `D:\deepseek\bin\dsh-web.ps1`：上位机启动后，直接执行 `dsh-web` 会自动加载插件；`dsh-web --no-open` 保留不打开浏览器的选项。这个本机包装脚本不在 npm 包内，其他环境可采用下方显式命令。原入口备份为 `D:\deepseek\backups\dsh-web-before-agent-light-20261106.ps1`。

overlay 包含真实 endpoint、tokenFile/dataDir 的绝对路径，不包含 token。插件入口必须是构建文件的 file URL，例如 `file:///D:/projects/agent-light/plugins/dsh/dist/index.js`；ESM 加载器不能直接导入插件目录。生成器会检查构建文件存在并使用这个入口。只有一个固定 Host 节点 id。将此 overlay 用于一次新的、无 live Agent 的 DSH 启动：

```powershell
dsh.cmd --profile web --patch D:/projects/agent-light/outputs/agent-light.local.patch.yml --no-open
```

必须先停止原来的 Web 后端，避免占用同一 web profile/端口。上述命令的 `--patch` 位置以本机 `dsh.cmd --help` 为准。独立 overlay 不修改用户原始 profile；调试阶段使用过后台启动，重新前台启动前需确认旧后端已退出。

若同时看到 `CAPTURE_DISABLED_Error`（worker_start）和 `EADDRINUSE 127.0.0.1:3080`，先排查旧 DSH 后台实例：它可能同时持有 Web 端口和 outbox 锁。关闭浏览器不会退出后端；请核对 PID 后停止旧实例，不要删除仍被活动进程持有的 owner.lock。失败的新实例可能覆盖最近一次 diagnostics.json，因此判断当前活跃来源时应同时查看 PC status 的 health/lease。

如正式通过 `dsh plugin --profile web add <本地包>` 安装 bundle，默认节点禁用。使用 `agent-light overlay --installed` 生成覆盖已有节点的配置，避免重复 insert。卸载临时接入只需下次启动去掉 `--patch`；不要手工修改 DSH 原始包。正式 profile 安装前自行备份选定配置。安装依赖不等于已成功装载。

配置：enabled（默认 true）、endpoint（默认 http://127.0.0.1:17321）、tokenFile/dataDir（必须绝对路径）、requestTimeoutMs（默认 200）、activityIntervalMs（默认 1000）、maxSpoolBytes（默认 64 MiB）。不允许代理、重定向或非 IPv4 loopback 目标。

DSH 回调只创建白名单标量、入队，不等待磁盘/HTTP。Worker fsync 后发送；已落盘记录至少一次重放，服务按 event_id 幂等。activity 每实例每秒至多一次，窗口限制 4096 条/8 MiB；磁盘/队列故障停用采集并标记 degraded。进程被强杀时，Worker 落盘前的尾部事件仍可能丢失。spool 不含问题、回答、参数、路径、错误正文或 token。

故障时仅修复 token、磁盘或冲突原因，然后重启 DSH 重新建立来源基线；不得手工删掉未确认的 segment 来伪装恢复。401/403 暂停，其他协议错误保留隔离记录，不静默跳过。

验证范围：合成生命周期/提问映射、离线落盘重放、畸形 ACK，以及本机 Cordis 的 global/prepend 顺序探针。可运行：

```powershell
node plugins/dsh/tools/verify-host.mjs D:/deepseek/npm-global/node_modules/@deepseek-ai/dsh/lib/bin.js
```

这些检查不等同于真实 Web answerer、PTC 全路径、故障注入/性能或实板 E2E 通过。`contracts/dsh/0.2.1-rc.2/capabilities.json` 因此保留 unverified。

如果设备通信正常却一直全灭，先执行 `agent-light status`。`connected:true` 且 `sources:{}` 表示插件没有向服务登记。检查 DSH 控制台是否出现 `ERR_UNSUPPORTED_DIR_IMPORT`，重新生成 overlay 后重启 DSH。修正已有 overlay 文件不会让正在运行的旧 DSH 自动加载插件。

`tools/smoke.mjs` 现在通过 PC CLI 生成 overlay，再交由真实 DSH boot/Loader 加载整个插件并检查 RUNNING → ATTENTION → COMPLETED；不再直接绕过加载器调用观察器。

v0.1.2 修复冷启动竞态：Worker 初始化期间创建的 root 不再被当成热加载而禁用采集。仅在冷启动阶段通过 DSH 官方串行 created 边界等待 Worker 就绪，在释放首轮前建立实例基线并发送完整 runtime_ready 清单。正常运行的事件回调仍不等待网络或磁盘。`tools/startup-race.mjs <DSH lib/bin.js绝对路径>` 覆盖此时序。

同版修复正常完成后红闪：真实 `turn/end.data.reason` 是 `{kind: 'completed'}` 等判别对象，适配器读取 `reason.kind`；原来的字符串 fixture 会掩盖此错误，已替换，并补充 completed/error/blocked/max-tokens/aborted 的真实结构回归检查。

插件启动/退出会输出固定 `[agent-light]` 诊断，并在 dataDir 的 `diagnostics.json` 写入最近一次 code/phase/time，不保存聊天内容或异常正文。`CAPTURE_READY` 表示观察器注册完成；健康与事件最终确认情况仍以 PC status 为准。

v0.1.3 修复 Worker 就绪的误超时：DSH 启动可能阻塞父线程超过 5 秒，即使 Worker 已发出就绪消息，定时器也可能先被处理。现在超时回调先让消息队列处理就绪，再判定失败；真实 Worker 错误立即返回白名单错误码，不再一律等到通用超时。超时并非主线程阻塞情况下的硬性墙钟上限。`reporter-startup.test.mjs` 覆盖父线程阻塞超过期限、活动 outbox 锁冲突两种情况。
