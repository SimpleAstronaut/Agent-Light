// Copyright 2026 Agent Light Authors
// 文件/模块：USB 协议 v1 的流解析、事务缓存与显示状态管理。
// 版本：1.0.0（固件基线）；日期：2026-10-28。
// 用法：先 ProtocolInit()；逐字节 Feed，周期 Poll；总线事件调用 Reset/Suspend。
// 约束：单一应用任务独占对象；帧格式和命令详见 contracts/usb-protocol-v1.md。
#ifndef AGENT_LIGHT_FIRMWARE_APP_PROTOCOL_H_
#define AGENT_LIGHT_FIRMWARE_APP_PROTOCOL_H_
#include <stddef.h>
#include "display.h"

// STATUS 对外报告的主/次版本编码 0x0100（1.0）；文件注释使用完整基线 1.0.0。
#define AGENT_LIGHT_FW_VERSION 0x0100u
#define AGENT_LIGHT_WIRE_CAPACITY 40u

// 同步接收一帧待发送数据的回调，在 ProtocolFeed() 内由应用任务调用。
// 参数：data 为非 NULL、含末尾 0 的完整 wire；size 为字节数，最大 40；
// context 原样透传，可为 NULL。data 可能指向栈，回调必须在返回前复制。
// 返回 true 表示已接收；false 表示未接收。但当前协议层忽略返回值，
// 不自动重试或回滚已应用状态，接入者必须预留发送槽（本项目用 QueueReply）。
// 不得阻塞或重入同一个 Protocol；不转移输入缓冲区所有权。
typedef bool (*ProtocolSend)(const uint8_t *data, size_t size, void *context);
// 保存单个 CDC 会话的解析器、显示与最近事务；由单一应用任务独占。
// encoded 不含分隔符；discard 表示已丢字节，需等 0 恢复。
// 缓存只在 cache_valid 时有效；计数饱和到 UINT16_MAX，boot_ms 跨 Reset 保留。
typedef struct {
  Display display;
  ProtocolSend send;
  void *send_context;
  uint8_t encoded[AGENT_LIGHT_WIRE_CAPACITY];
  uint8_t encoded_size;
  bool discard;
  bool cache_valid;
  uint8_t cached_request[38];
  uint8_t cached_request_size;
  uint8_t cached_response[AGENT_LIGHT_WIRE_CAPACITY];
  uint8_t cached_response_size;
  uint8_t last_seq;
  uint16_t crc_drop_count;
  uint16_t frame_drop_count;
  uint32_t boot_ms;
} Protocol;

// 覆盖初始化协议对象、计数器和显示自检状态，并记录启动毫秒值。
// 参数：protocol 为非 NULL 可写对象；send 为非 NULL 同步复制回调；
// context 可为 NULL，作为 send 的上下文原样保存；now 为单调 uint32_t 毫秒。
// 由单一应用任务调用；send 及 context 所指资源必须在对象使用期间保持有效。
void ProtocolInit(Protocol *protocol, ProtocolSend send, void *context,
                  uint32_t now);
// 开始一次总线重新同步：清半帧、丢弃标志、事务缓存及 revision 有效标志。
// 参数：protocol 为非 NULL 已初始化对象；now 为当前单调毫秒值。
// 仅应用任务调用；进入 WAIT_SYNC，将业务状态与 last_seq 置 0xff，
// 保留统计计数、亮度和 boot_ms。调用者另行撤销硬件 TX 并清空应用收发队列。
void ProtocolReset(Protocol *protocol, uint32_t now);
// 将软件显示模式设为 SUSPENDED；不操作 PWM 或清除事务缓存。
// 参数：protocol 为非 NULL 已初始化对象，仅应用任务调用。
// 此模式不显示相位，内部时间起点置 0；挂起 ISR 必须另行立即停 PWM。
// 本项目先 Reset 再 Suspend；恢复通过 Reset 要求主机重新发送 SET_STATE。
void ProtocolSuspend(Protocol *protocol);
// 记录接收丢失，清除已累积半帧并丢弃输入直到下一个 0 分隔符。
// 参数：protocol 为非 NULL 已初始化对象，仅应用任务调用。
// frame_drop_count 饱和加一；分隔符只用于恢复，不作为残缺帧尾解析。
void ProtocolRxLost(Protocol *protocol);
// 消费单个字节并在完整有效帧到达时处理命令、同步调用 send。
// 参数：protocol 为非 NULL 已初始化对象；byte 为 CDC 字节（0 是帧分隔符）；
// now 为当前单调毫秒值，用于有效请求保活、状态相位和 uptime。
// 仅拥有对象的应用任务调用，不得从 ISR 或 send 回调重入。
// COBS/长度/CRC 错误静默丢弃，完整但非法命令返回 NACK；
// 相同事务重放缓存，合法 SET 更新显示。每次调用最多处理一个完整帧。
// 调用前须确保发送槽可用；当前实现不会处理 send 返回的背压。
void ProtocolFeed(Protocol *protocol, uint8_t byte, uint32_t now);
// 推进协议内显示状态机的自检和链路超时，不处理输入或发送响应。
// 参数：protocol 为非 NULL 已初始化对象；now 为与 Feed 同源的单调毫秒值。
// 仅应用任务调用；本项目每 5 ms 轮询，LED 硬件输出由调用者另行更新。
void ProtocolPoll(Protocol *protocol, uint32_t now);
#endif
