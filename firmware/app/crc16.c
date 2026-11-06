// Copyright 2026 Agent Light Authors
// 文件/模块：CRC16-CCITT-FALSE 校验。
// 版本：1.0.0（固件基线）；日期：2026-10-28。
// 用法：对协议头和 payload 调用 Crc16()，再按小端序追加结果。
// 约束：算法无全局状态；多项式 0x1021、初值 0xffff、不反射、不输出异或。
#include "crc16.h"

// 按高位优先逐位计算，使用截断到 16 位的左移模拟多项式余数，不占查表 Flash。
uint16_t Crc16(const uint8_t *data, size_t size) {
  uint16_t crc = 0xffff;
  for (size_t i = 0; i < size; ++i) {
    crc ^= (uint16_t)data[i] << 8;
    for (unsigned bit = 0; bit < 8; ++bit) {
      crc = (uint16_t)((crc & 0x8000) ? (crc << 1) ^ 0x1021 : crc << 1);
    }
  }
  return crc;
}
