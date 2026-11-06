// Copyright 2026 Agent Light Authors
// 文件/模块：USB 协议 v1 的流解析、事务缓存与显示状态管理。
// 版本：1.0.0（固件基线）；日期：2026-10-28。
// 用法：先 ProtocolInit()；逐字节 Feed，周期 Poll；总线事件调用 Reset/Suspend。
// 约束：单一应用任务独占对象；帧格式和命令详见 contracts/usb-protocol-v1.md。
#include "protocol.h"
#include <string.h>
#include "cobs.h"
#include "crc16.h"

// 读取小端 uint32_t，允许未对齐地址，避免 Cortex-M0 的未对齐字访问。
// 参数：p 为非 NULL 且至少 4 字节可读区；返回组装值，不保存或修改输入。
static uint32_t Read32(const uint8_t *p) {
  return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
         ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
// 将 value 按小端序覆盖到 p 指向的连续 4 字节，不要求地址对齐。
// 参数：p 为非 NULL、至少 4 字节可写区；value 为待写 uint32_t，不保留指针。
static void Write32(uint8_t *p, uint32_t value) {
  for (unsigned i = 0; i < 4; ++i) p[i] = (uint8_t)(value >> (8 * i));
}
// 使丢帧计数饱和加一，防止长期运行后回绕成 0。
// 参数：count 为非 NULL 的可写计数器；仅拥有协议对象的任务调用。
static void CountDrop(uint16_t *count) {
  if (*count != UINT16_MAX) ++*count;
}

// 全量清零保证缓存/流解析标志无效；保存回调上下文，由显示初始化设置上电模式。
void ProtocolInit(Protocol *p, ProtocolSend send, void *context, uint32_t now) {
  memset(p, 0, sizeof(*p));
  p->send = send;
  p->send_context = context;
  p->boot_ms = now;
  DisplayInit(&p->display, now);
}
// 只失效当前会话相关字段，统计与启动时刻跨 reset/resume 保留。
void ProtocolReset(Protocol *p, uint32_t now) {
  p->encoded_size = 0;
  p->discard = false;
  p->cache_valid = false;
  p->display.revision_valid = false;
  p->display.state = 0xff;
  p->last_seq = 0xff;
  DisplayModeSet(&p->display, kModeWaitSync, now);
}
// 挂起时只改变软件模式；硬件停 PWM 在 USB ISR 中立即完成，不能等此处轮询。
void ProtocolSuspend(Protocol *p) {
  DisplayModeSet(&p->display, kModeSuspended, 0);
}
// 先丢掉已缓存字节再进入丢弃模式，避免将丢字节两侧的数据拼成伪合法帧。
void ProtocolRxLost(Protocol *p) {
  p->encoded_size = 0;
  p->discard = true;
  CountDrop(&p->frame_drop_count);
}
// 将协议与时间推进解耦；无输入时应用任务仍需调用，才能触发链路超时。
void ProtocolPoll(Protocol *p, uint32_t now) {
  DisplayPoll(&p->display, now);
}

// 缓存整个响应，重试返回逐字节相同的 ACK，避免重复应用状态。
// 封装 CRC、COBS 和分隔符，按需缓存完整请求/响应，再同步交给发送回调。
// 参数：p 为非 NULL 已初始化对象；request 为通过结构/CRC 验证的 raw，
// 至少 6 字节；request_size 为其长度（<=38）；type 为响应类型；
// payload 为非 NULL、至少 length 字节的响应体，length<=32；
// cache 决定是否替换最近事务。所有指针只在调用中借用，缓存保存副本。
// 仅协议任务调用；发送回调必须复制栈上 wire，且调用前已有可用 TX 槽。
// 忽略 send 返回值，无自动重试；缓存保留完整 wire 保证重复请求逐字节重放。
static void Reply(Protocol *p, const uint8_t *request, size_t request_size,
                  uint8_t type, const uint8_t *payload, uint8_t length,
                  bool cache) {
  uint8_t raw[38] = {1, type, request[2], length};
  uint8_t wire[40];
  memcpy(raw + 4, payload, length);
  uint16_t crc = Crc16(raw, length + 4u);
  raw[length + 4u] = (uint8_t)crc;
  raw[length + 5u] = (uint8_t)(crc >> 8);
  size_t size = CobsEncode(raw, length + 6u, wire, sizeof(wire) - 1);
  wire[size++] = 0;
  if (cache) {
    memcpy(p->cached_request, request, request_size);
    p->cached_request_size = (uint8_t)request_size;
    memcpy(p->cached_response, wire, size);
    p->cached_response_size = (uint8_t)size;
    p->cache_valid = true;
  }
  (void)p->send(wire, size, p->send_context);
}

// 处理已通过结构和 CRC 校验的单帧，按协议规定优先级生成响应。
// 参数：p 为非 NULL 协议对象；raw 为非 NULL 的 size 字节原始帧（6..38），
// 长度字段必须与 size 一致；now 为单调毫秒。输入只在本次调用中借用。
// 仅应用任务内部调用；可能更新显示、保活时间、last_seq 和最近事务缓存。
// 先判最近 seq：内容相同则重放缓存，冲突返回 7 且保留原缓存。
// 之后依次校验版本、命令、长度、模式、值和 revision；NACK 不刷新保活。
// revision 用模 2^32 半区间比较，差为 0x80000000 也判过期；同版本不同值冲突。
// 只有合法 SET（含成功事务重试）恢复 ACTIVE；心跳/查询只刷新保活时间。
static void HandleFrame(Protocol *p, const uint8_t *raw, size_t size,
                        uint32_t now) {
  uint8_t command = raw[1], seq = raw[2], length = raw[3];
  uint8_t error = 0;
  bool seq_conflict = false;
  if (p->cache_valid && seq == p->cached_request[2]) {
    if (size == p->cached_request_size &&
        memcmp(raw, p->cached_request, size) == 0) {
      // 只缓存成功请求才能刷新链路；NACK 重试不能延迟超时。
      if (p->cached_response[0] != 0) {
        uint8_t decoded[38];
        size_t n = CobsDecode(p->cached_response,
                             p->cached_response_size - 1, decoded, sizeof(decoded));
        if (n >= 6 && decoded[1] != 0x82) {
          p->display.last_valid_ms = now;
          if (command == 1) {
            DisplaySet(&p->display, Read32(raw + 4), raw[8], raw[9], now);
          }
        }
      }
      (void)p->send(p->cached_response, p->cached_response_size, p->send_context);
      return;
    }
    error = 7;
    seq_conflict = true;
  } else if (raw[0] != 1) error = 3;
  else if (command != 1 && command != 2 && command != 3) error = 2;
  else if (length != (command == 1 ? 6 : 0)) error = 1;
  else if (p->display.mode == kModeBoot ||
           p->display.mode == kModeSuspended) error = 8;
  else if (command == 1) {
    uint32_t revision = Read32(raw + 4);
    uint32_t diff = revision - p->display.revision;
    if (raw[8] > 4 || raw[9] < 20 || raw[9] > 100) error = 4;
    else if (p->display.revision_valid) {
      if (diff == 0 && (raw[8] != p->display.state ||
                        raw[9] != p->display.brightness)) error = 6;
      else if (diff >= 0x80000000u) error = 5;
    }
  }
  if (error != 0) {
    uint8_t nack[] = {command, error};
    Reply(p, raw, size, 0x82, nack, sizeof(nack), !seq_conflict);
    return;
  }
  p->last_seq = seq;
  p->display.last_valid_ms = now;
  if (command == 1) {
    uint32_t revision = Read32(raw + 4);
    uint8_t applied = !p->display.revision_valid || revision != p->display.revision;
    DisplaySet(&p->display, revision, raw[8], raw[9], now);
    uint8_t ack[7] = {command, 0};
    Write32(ack + 2, revision);
    ack[6] = applied;
    Reply(p, raw, size, 0x81, ack, sizeof(ack), true);
  } else if (command == 2) {
    uint8_t ack[6] = {command, 0};
    Write32(ack + 2, (uint32_t)(now - p->boot_ms) / 1000);
    Reply(p, raw, size, 0x81, ack, sizeof(ack), true);
  } else {
    uint8_t status[17] = {(uint8_t)p->display.mode, p->display.state};
    Write32(status + 2, p->display.revision);
    status[6] = p->display.revision_valid;
    status[7] = p->display.brightness;
    status[8] = p->last_seq;
    status[9] = (uint8_t)AGENT_LIGHT_FW_VERSION;
    status[10] = (uint8_t)(AGENT_LIGHT_FW_VERSION >> 8);
    Write32(status + 11, (uint32_t)(now - p->boot_ms) / 1000);
    status[15] = (uint8_t)p->crc_drop_count;
    status[16] = (uint8_t)(p->crc_drop_count >> 8);
    Reply(p, raw, size, 0x83, status, sizeof(status), true);
  }
}

// 以 0 分隔符建立边界，超长输入进入丢弃模式直到下一分隔符。
// 先解 COBS、验证最小长度/声明长度，再验证 CRC；失败只计数，不回 NACK。
// 只有结构和 CRC 完整的 raw 才交给 HandleFrame，确保后者可安全读头字段。
void ProtocolFeed(Protocol *p, uint8_t byte, uint32_t now) {
  if (byte != 0) {
    if (p->discard) return;
    if (p->encoded_size >= sizeof(p->encoded)) {
      ProtocolRxLost(p);
      return;
    }
    p->encoded[p->encoded_size++] = byte;
    return;
  }
  if (p->discard) {
    p->discard = false;
    p->encoded_size = 0;
    return;
  }
  if (p->encoded_size == 0) return;
  uint8_t raw[38];
  size_t size = CobsDecode(p->encoded, p->encoded_size, raw, sizeof(raw));
  p->encoded_size = 0;
  if (size < 6 || raw[3] > 32 || size != raw[3] + 6u) {
    CountDrop(&p->frame_drop_count);
    return;
  }
  uint16_t expected = (uint16_t)(raw[size - 2] | ((uint16_t)raw[size - 1] << 8));
  if (Crc16(raw, size - 2) != expected) {
    CountDrop(&p->crc_drop_count);
    return;
  }
  HandleFrame(p, raw, size, now);
}
