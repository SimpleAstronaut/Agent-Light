// Copyright 2026 Agent Light Authors
// 文件/模块：CRC16-CCITT-FALSE 校验。
// 版本：1.0.0（固件基线）；日期：2026-10-28。
// 用法：对协议头和 payload 调用 Crc16()，再按小端序追加结果。
// 约束：算法无全局状态；多项式 0x1021、初值 0xffff、不反射、不输出异或。
#ifndef AGENT_LIGHT_FIRMWARE_APP_CRC16_H_
#define AGENT_LIGHT_FIRMWARE_APP_CRC16_H_
#include <stddef.h>
#include <stdint.h>
// 计算 data 的 CRC16-CCITT-FALSE，不修改输入、不保存指针。
// 参数：data 指向至少 size 字节可读区；size 单位为字节，0 时 data 可为 NULL。
// 返回 16 位 CRC；空输入返回 0xffff。返回整数的存储字节序由调用者决定。
// 可重入，无共享状态；协议覆盖头和 payload，不包含 CRC 自身与 COBS 分隔符。
uint16_t Crc16(const uint8_t *data, size_t size);
#endif
