// Copyright 2026 Agent Light Authors
// 文件/模块：CDC EP0 控制请求的无状态白名单校验。
// 版本：1.0.0（固件基线）；日期：2026-10-28。
// 用法：在厂商 CDC Setup 和数据阶段之前调用 UsbCdcRequestValid()。
// 约束：仅校验控制请求字段和就绪条件；不解引用 USB 类存储，不处理业务协议。
#include "usb_cdc_guard.h"

// 先挡住未配置/空类存储和错误接口，再对白名单请求逐项约束方向、值和长度。
bool UsbCdcRequestValid(uint8_t type, uint8_t request, uint16_t value,
                        uint16_t index, uint16_t length, bool ready) {
  if (!ready || index != 0) return false;
  switch (request) {
    case 0x20: return type == 0x21 && value == 0 && length == 7;
    case 0x21: return type == 0xa1 && value == 0 && length == 7;
    case 0x22: return type == 0x21 && value <= 3 && length == 0;
    case 0x23: return type == 0x21 && length == 0;
    default: return false;
  }
}
