# Agent Light USB 协议 v1

日期：2026-10-28。固件实施基线来自 `outputs/agent-indicator-execution-plan.md` §8；与早期总体设计冲突时以详细执行方案为准。本文件仅冻结 USB 子合约，不代表 PC/Agent 事件合约已完成。

## 传输

USB CDC ACM 字节流；串口波特率仅用于主机 API，无物理 UART。每帧为 `COBS(raw) + 00`，支持分包和粘包。raw 为 `version:u8=1, type:u8, seq:u8, length:u8, payload[length], crc:u16LE`。

Payload 最大 32，raw 最大 38，wire 最大 40 字节。CRC16-CCITT-FALSE 覆盖头和 payload，多项式 0x1021、初值 0xffff、不反射、无输出异或；`123456789 => 29b1`。CRC 低字节在前。

结构、COBS、CRC、超长错误静默丢弃；下一 `00` 恢复。只有结构与 CRC 完整的帧才能返回 NACK。接收溢出清除不完整队列，丢弃至下一个分隔符。空分隔符忽略。

## 命令

| type | 名称 | payload | 成功响应 |
|---|---|---|---|
| 01 | SET_STATE | revision:u32LE, state:u8, brightness:u8 | 81，`01 00 revision:u32LE applied:u8` |
| 02 | HEARTBEAT | 空 | 81，`02 00 uptime_s:u32LE` |
| 03 | GET_STATUS | 空 | 83，见下表 |
| 82 | NACK | command:u8, error:u8 | 不接收主机响应类消息 |

响应 seq 回显请求 seq。SET 请求 raw=12 字节、ACK raw=13 字节。state：0=IDLE、1=RUNNING、2=ATTENTION、3=ERROR、4=COMPLETED；brightness 20–100，默认35，IDLE始终全灭。

错误：1 BAD_LENGTH、2 UNKNOWN_COMMAND、3 UNSUPPORTED_VERSION、4 INVALID_VALUE、5 STALE_REVISION、6 REVISION_CONFLICT、7 SEQ_REUSED、8 NOT_READY、9 INTERNAL_ERROR（保留）。判定优先级：最近 seq 冲突、版本、命令、命令长度、模式就绪、值/revision。

## STATUS payload（17 字节）

| 偏移 | 字段 |
|---|---|
| 0 | mode:u8，0 BOOT、1 WAIT_SYNC、2 ACTIVE、3 LINK_LOST、4 SUSPENDED |
| 1 | display_state:u8，无有效状态为 ff |
| 2 | display_revision:u32LE，仅 revision_valid=1 时有效 |
| 6 | revision_valid:u8 |
| 7 | brightness_pct:u8 |
| 8 | last_seq:u8，本次成功 GET_STATUS 的 seq |
| 9 | fw_version:u16LE，当前 0100（1.0） |
| 11 | uptime_s:u32LE，毫秒计时器换算，约49.7天回绕 |
| 15 | crc_drop_count:u16LE，饱和计数 |

## 可靠性与模式

- PC 同时仅一个未完成事务；新事务 seq 自然递增，重试 seq 不变。
- 设备缓存最近一次已响应请求的完整 raw 和完整 wire 响应（包括 NACK）。完全相同重试逐字节返回缓存；同 seq 不同内容返回7并保留原缓存。坏帧不更新缓存。
- 只有成功请求刷新5秒链路计时，NACK和坏帧不刷新。成功 SET 重试会恢复 ACTIVE，响应仍逐字节重放。
- 相同 revision 同内容 ACK applied=0；同 revision 不同内容 NACK6。新 revision 满足 `0 < (uint32)(new-old) < 80000000`；其他 NACK5。第一条 SET 可接受任意 revision。
- HEARTBEAT/GET_STATUS 维持 ACTIVE 链路，但不能把 WAIT_SYNC/LINK_LOST 恢复成旧状态。
- 上电红黄绿各100ms，随后 WAIT_SYNC；USB reset/resume 清掉事务缓存和 revision_valid，WAIT_SYNC等待重新SET。USB suspend停PWM全灭；不提供远程唤醒。
- PC 负责完成保持，固件不自动退出 COMPLETED，不持久写Flash。
- 链路超时在最后有效请求起5000ms，任务轮询额外延迟≤5ms（不含硬件异常）。时间差为uint32无符号运算。

## 固定灯效

IDLE全灭；RUNNING黄常亮；ATTENTION红常亮；ERROR红2Hz/50%；COMPLETED绿常亮；WAIT_SYNC/LINK_LOST黄1Hz/50%。PWM载波10kHz；闪烁由进入模式/灯态的时刻起算，心跳和幂等SET不重启正常闪烁相位。

开发 VID/PID 为 ST 示例 0483:5740，发布前必须替换为有权使用的标识。序列号为完整96位UID转24位十六进制ASCII。
