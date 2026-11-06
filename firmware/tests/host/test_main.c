// Copyright 2026 Agent Light Authors
// 文件/模块：协议、编解码、时间和灯态主机回归。
// 版本：1.0.0（固件基线）；日期：2026-10-28。
// 用法：在项目根运行 .\firmware\build.ps1 Host；断言失败即测试失败。
// 约束：仅在主机运行，不能证明实板电气、PWM 时序或 USB 电流符合要求。
// 验证真实协议实现，预期值来自执行方案而非实现内部状态。
#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "cobs.h"
#include "crc16.h"
#include "protocol.h"
#include "usb_cdc_guard.h"
#include "usb_vectors.inc"

static uint8_t response[48];
static size_t response_size;
static unsigned replies;

// 复制响应到测试全局缓冲，并累计响应次数。
// 参数：data 非 NULL，size<=48 字节；context 忽略，可为 NULL；返回 true。
// 仅测试单线程调用；与实际应用一样在回调返回前复制，避免保留栈地址。
static bool Capture(const uint8_t *data, size_t size, void *context) {
  (void)context;
  memcpy(response, data, size);
  response_size = size;
  ++replies;
  return true;
}

// 构造 CRC/COBS 完整请求并追加 0，供合法和非法命令测试复用。
// 参数：version/command/seq 为头字段；payload 指向 length 字节，length=0 可为 NULL；
// length<=32；wire 非 NULL 且至少 48 字节可写；返回写入字节数，不保存指针。
static size_t MakeRequest(uint8_t version, uint8_t command, uint8_t seq,
                          const uint8_t *payload, uint8_t length,
                          uint8_t *wire) {
  uint8_t raw[40] = {version, command, seq, length};
  if (length != 0) memcpy(raw + 4, payload, length);
  uint16_t crc = Crc16(raw, 4u + length);
  raw[4u + length] = (uint8_t)crc;
  raw[5u + length] = (uint8_t)(crc >> 8);
  size_t size = CobsEncode(raw, 6u + length, wire, 47);
  wire[size++] = 0;
  return size;
}

// 把一帧请求按字节喂给协议对象，模拟 CDC 分包和流式输入。
// 参数：p 非 NULL；cmd/seq 为命令和序号；payload 为 length 字节，0 长度可为 NULL；
// length<=32；now 为测试毫秒时刻。响应经 Capture 写全局缓冲。
static void Request(Protocol *p, uint8_t cmd, uint8_t seq,
                    const uint8_t *payload, uint8_t length, uint32_t now) {
  uint8_t wire[48];
  size_t size = MakeRequest(1, cmd, seq, payload, length, wire);
  for (size_t i = 0; i < size; ++i) ProtocolFeed(p, wire[i], now);
}

// 解码最近捕获响应并断言分隔符/CRC 正确；返回 NACK 错误码，成功响应返回 0。
// 无参数；要求之前已有响应，格式不符立即断言失败。
static uint8_t ReplyCode(void) {
  uint8_t raw[40];
  assert(response_size > 0 && response[response_size - 1] == 0);
  size_t size = CobsDecode(response, response_size - 1, raw, sizeof(raw));
  assert(size >= 8);
  assert(Crc16(raw, size - 2) ==
         (uint16_t)(raw[size - 2] | ((uint16_t)raw[size - 1] << 8)));
  return raw[1] == 0x82 ? raw[5] : 0;
}

// 验证 CRC 已知答案、COBS 含零向量、容量不足及截断错误；无参数，失败触发断言。
static void TestCodec(void) {
  assert(Crc16((const uint8_t *)"123456789", 9) == 0x29b1);
  const uint8_t input[] = {0, 1, 0, 2, 3, 0};
  const uint8_t expected[] = {1, 2, 1, 3, 2, 3, 1};
  uint8_t encoded[16], decoded[16];
  assert(CobsEncode(input, sizeof(input), encoded, sizeof(encoded)) == 7);
  assert(memcmp(encoded, expected, 7) == 0);
  assert(CobsDecode(expected, 7, decoded, sizeof(decoded)) == sizeof(input));
  assert(memcmp(input, decoded, sizeof(input)) == 0);
  assert(CobsEncode(input, sizeof(input), encoded, 2) == 0);
  const uint8_t invalid[] = {4, 1};
  assert(CobsDecode(invalid, sizeof(invalid), decoded, sizeof(decoded)) == 0);
}

// 验证重试缓存、seq 冲突、revision 回绕/冲突、非法值、断链和恢复；无参数。
static void TestProtocol(void) {
  Protocol p;
  ProtocolInit(&p, Capture, NULL, 0);
  ProtocolPoll(&p, 300);
  assert(p.display.mode == kModeWaitSync);
  uint8_t set[] = {0xfe, 0xff, 0xff, 0xff, 1, 35};
  Request(&p, 1, 0, set, 6, 400);
  assert(ReplyCode() == 0 && p.display.mode == kModeActive);
  uint8_t cached[48];
  size_t cached_size = response_size;
  memcpy(cached, response, response_size);
  Request(&p, 1, 0, set, 6, 500);
  assert(response_size == cached_size &&
         memcmp(cached, response, cached_size) == 0);
  set[4] = 2;
  Request(&p, 1, 0, set, 6, 600);
  assert(ReplyCode() == 7 && p.display.state == 1);
  Request(&p, 1, 1, set, 6, 700);
  assert(ReplyCode() == 6);
  set[0] = 0xff;
  Request(&p, 1, 2, set, 6, 800);
  assert(ReplyCode() == 0);
  memset(set, 0, 4);
  Request(&p, 1, 3, set, 6, 900);
  assert(ReplyCode() == 0);
  set[0] = 1;
  Request(&p, 1, 4, set, 6, 1000);
  assert(ReplyCode() == 0);
  set[0] = 0;
  Request(&p, 1, 5, set, 6, 1100);
  assert(ReplyCode() == 5);
  set[0] = 2; set[5] = 19;
  Request(&p, 1, 6, set, 6, 1200);
  assert(ReplyCode() == 4);
  Request(&p, 1, 7, set, 5, 1300);
  assert(ReplyCode() == 1);
  Request(&p, 0x55, 8, NULL, 0, 1400);
  assert(ReplyCode() == 2);
  ProtocolPoll(&p, 6000);
  assert(p.display.mode == kModeLinkLost);
  Request(&p, 2, 9, NULL, 0, 6100);
  assert(p.display.mode == kModeLinkLost);
  set[0] = 1; set[5] = 35;
  Request(&p, 1, 10, set, 6, 6200);
  assert(ReplyCode() == 0 && p.display.mode == kModeActive);
  ProtocolPoll(&p, 11200);
  Request(&p, 1, 10, set, 6, 11201);
  assert(p.display.mode == kModeActive);
  ProtocolSuspend(&p);
  LedLevels leds = DisplayGetLeds(&p.display, 12000);
  assert(leds.red == 0 && leds.yellow == 0 && leds.green == 0);
  ProtocolReset(&p, 13000);
  assert(!p.display.revision_valid && !p.cache_valid);
  assert(p.display.mode == kModeWaitSync);
  for (unsigned i = 0; i < 768; ++i) {
    Request(&p, 2, (uint8_t)i, NULL, 0, 14000 + i);
    assert(ReplyCode() == 0);
  }
}

// 验证毫秒回绕、过长/损坏帧静默丢弃和 100000 随机字节后的恢复；无参数。
static void TestStreamAndTime(void) {
  Protocol p;
  ProtocolInit(&p, Capture, NULL, 0xfffffff0u);
  ProtocolPoll(&p, 284);
  uint8_t set[] = {1, 0, 0, 0, 3, 35};
  Request(&p, 1, 1, set, 6, 0xffffff00u);
  ProtocolPoll(&p, 4743);
  assert(p.display.mode == kModeActive);
  ProtocolPoll(&p, 4744);
  assert(p.display.mode == kModeLinkLost);
  unsigned before = replies;
  for (unsigned i = 0; i < 300; ++i) ProtocolFeed(&p, 0x55, 5000);
  ProtocolFeed(&p, 0, 5000);
  assert(replies == before);
  Request(&p, 1, 2, set, 6, 5001);
  assert(ReplyCode() == 0 && p.display.mode == kModeActive);
  uint8_t wire[48];
  size_t size = MakeRequest(1, 2, 3, NULL, 0, wire);
  wire[size - 2] ^= 0x80;
  before = replies;
  for (size_t i = 0; i < size; ++i) ProtocolFeed(&p, wire[i], 6000);
  assert(replies == before);
  assert(p.display.last_valid_ms == 5001);
  uint32_t rng = 7;
  for (unsigned i = 0; i < 100000; ++i) {
    rng = rng * 1664525u + 1013904223u;
    ProtocolFeed(&p, (uint8_t)(rng >> 24), 6001);
  }
  ProtocolFeed(&p, 0, 6002);
  Request(&p, 2, 4, NULL, 0, 6003);
  assert(ReplyCode() == 0);
}

// 验证自检顺序、ERROR 闪烁相位、COMPLETED 长期保持及 IDLE 全灭；无参数。
static void TestLights(void) {
  Display d;
  DisplayInit(&d, 0);
  LedLevels v = DisplayGetLeds(&d, 0);
  assert(v.red == 35 && v.yellow == 0 && v.green == 0);
  v = DisplayGetLeds(&d, 100);
  assert(v.yellow == 35);
  v = DisplayGetLeds(&d, 200);
  assert(v.green == 35);
  DisplaySet(&d, 1, 3, 35, 300);
  v = DisplayGetLeds(&d, 549); assert(v.red == 35);
  v = DisplayGetLeds(&d, 550); assert(v.red == 0);
  v = DisplayGetLeds(&d, 800); assert(v.red == 35);
  DisplaySet(&d, 2, 4, 20, 900);
  v = DisplayGetLeds(&d, 100000); assert(v.green == 20);
  DisplaySet(&d, 3, 0, 100, 100001);
  v = DisplayGetLeds(&d, 100001);
  assert(v.red == 0 && v.yellow == 0 && v.green == 0);
}

// 把偶数长度的十六进制文本转成字节，用于独立黄金向量。
// 参数：hex 为非 NULL 的 NUL 结尾合法文本；bytes 非 NULL 且至少 strlen(hex)/2 字节；
// 返回写入字节数，非法文本触发断言，不保留输入指针。
static size_t FromHex(const char *hex, uint8_t *bytes) {
  size_t size = 0;
  while (*hex != 0) {
    unsigned byte;
    assert(sscanf(hex, "%2x", &byte) == 1);
    bytes[size++] = (uint8_t)byte;
    hex += 2;
  }
  return size;
}

// 独立初始化每组黄金向量并逐字节比对响应；无参数，出错打印向量名并断言。
static void TestGoldenVectors(void) {
  for (size_t i = 0; i < sizeof(kVectors) / sizeof(kVectors[0]); ++i) {
    Protocol p;
    uint8_t wire[48], expected[48];
    size_t size = FromHex(kVectors[i].wire, wire);
    size_t expected_size = FromHex(kVectors[i].response, expected);
    ProtocolInit(&p, Capture, NULL, 0);
    ProtocolPoll(&p, 300);
    response_size = 0;
    for (size_t j = 0; j < size; ++j) ProtocolFeed(&p, wire[j], 400);
    if (response_size != expected_size ||
        memcmp(response, expected, expected_size) != 0) {
      fprintf(stderr, "vector failed: %s\n", kVectors[i].name);
      assert(false);
    }
  }
}

// 运行全部主机用例，穷举 CDC line coding 的 65536 种长度。
// 无参数；成功打印 PASS 并返回 0，任何断言失败终止进程。
int main(void) {
  // 必须在 USB 数据阶段开始前拒绝超长控制请求，否则厂商缓冲区会越界。
  for (unsigned length = 0; length < 65536; ++length) {
    assert(UsbCdcRequestValid(0x21, 0x20, 0, 0, (uint16_t)length, true) ==
           (length == 7));
    assert(UsbCdcRequestValid(0xa1, 0x21, 0, 0, (uint16_t)length, true) ==
           (length == 7));
  }
  assert(UsbCdcRequestValid(0x21, 0x22, 3, 0, 0, true));
  assert(!UsbCdcRequestValid(0x21, 0x22, 0, 0, 1, true));
  assert(!UsbCdcRequestValid(0xa1, 0x20, 0, 0, 7, true));
  assert(!UsbCdcRequestValid(0x21, 0x20, 0, 1, 7, true));
  assert(!UsbCdcRequestValid(0x21, 0xff, 0, 0, 0, true));
  assert(!UsbCdcRequestValid(0x21, 0x20, 0, 0, 7, false));
  assert(!UsbCdcRequestValid(0xa1, 0x21, 0, 0, 7, false));
  TestCodec(); TestProtocol(); TestStreamAndTime(); TestLights();
  TestGoldenVectors();
  puts("PASS: codec, transactions, stream recovery, wraparound, modes, LEDs");
  return 0;
}
