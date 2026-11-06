# Worker 启动就绪误超时修复 v0.1.3

现场：Web 可监听 3080，但插件报 CAPTURE_DISABLED_Error/worker_start。队列没有活动 owner.lock；checkpoint 和全部59条segment记录的长度/摘要均有效。Worker已推进runtime=5并向PC发送心跳，但未提交新runtime_ready，随后被父线程关闭。因此不是同一个端口冲突或数据损坏问题。

复现：复制既有白名单outbox至临时目录，单独Worker约53ms就绪。父线程阻塞6000ms时，旧启动逻辑报WORKER_START_FAILED；Worker的online/ready消息在父线程恢复后才被分发。旧5000ms定时器先执行，误判已就绪Worker失败。

修复：超时定时器通过setImmediate延后判定，让已排队的MessagePort就绪消息先被处理；settled标志保证只完成一次，清理监听器与定时器。Worker异常/非零退出立即拒绝启动，返回白名单错误码（如OUTBOX_ALREADY_OWNED、CHECKPOINT_CORRUPT、WORKER_ENOENT），不输出原异常文本或路径。已退出Worker不再等待重复关闭。

验证：TypeScript构建通过；7项插件检查通过，含5500ms父线程阻塞及真实owner锁冲突；真实SDK/Loader/PC集成的RUNNING→ATTENTION→COMPLETED通过。完整DSH Web启动出现CAPTURE_READY，PC确认runtime_seq=ready_seq=6、health=healthy、persisted_seq=acked_seq=83，串口ACK空闲revision=33。

操作：验证完成已停止本轮临时后台DSH，交还用户前台启动；上位机保持运行。未删除outbox/checkpoint/token，未改真实DSH profile。npm产物为outputs/packages/agent-light-dsh-0.1.3.tgz。真实聊天灯态此前已联调通过，本轮主要验证Worker启动与交接。
