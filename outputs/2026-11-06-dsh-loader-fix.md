# DSH 全灭故障修复 v0.1.1

现场观察：最初上位机 status 为 connected=true、serial_diagnostic=OK、desired=IDLE，sources 与 sessions 均为空；插件 outbox 未创建。

根因：v0.1 的 CLI overlay 生成器把插件目录写入 name。DSH 把它转换为目录 file URL 后交给 ESM 加载器，报 ERR_UNSUPPORTED_DIR_IMPORT，插件未执行。使用本机 DSH boot/Loader 与相同目录入口已复现 inactive。先前的软件 smoke 直接调用 observe，漏掉了部署入口。

修复：生成器检查 dist/index.js 存在，使用该文件的绝对 file URL。现场 outputs/agent-light.local.patch.yml 已备份至同名 .bak 并重新生成。插件释放逻辑同步改为 Cordis ctx.effect disposer，以确保 Worker 在卸载时关闭。

验证：升级 smoke 使用 PC CLI 生成真实 overlay，再通过本机 DSH boot/Loader 装载完整插件。修复前报 PLUGIN_NOT_LOADED；修复后 RUNNING → ATTENTION → COMPLETED 通过，进程退出码 0。TypeScript 构建通过。测试使用隔离服务与合成元数据，不访问真实聊天或占用灯板。

后续现场操作：重新启动上位机和使用该 overlay 的 DSH，再发起对话。最新检查时原上位机已退出，17321 未监听；因此尚未宣称真实聊天控灯已恢复。没有强制停止用户 DSH 或更改真实 profile。

构建产物更新为 outputs/packages 下的 0.1.1 wheel 与 npm tgz。当前项目 editable 安装直接使用修复后的 CLI，无需重新安装；插件 dist 也已重新构建。
