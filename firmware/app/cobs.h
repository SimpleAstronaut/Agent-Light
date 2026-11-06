// Copyright 2026 Agent Light Authors
// 文件/模块：无动态内存的 COBS 字节流帧编解码。
// 版本：1.0.0（固件基线）；日期：2026-10-28。
// 用法：用 CobsEncode() 编码后自行追加 0；解码前移除帧尾 0。
// 约束：输入输出不得重叠；独立缓冲区可重入，不涉及 USB 或 RTOS。
#ifndef AGENT_LIGHT_FIRMWARE_APP_COBS_H_
#define AGENT_LIGHT_FIRMWARE_APP_COBS_H_
#include <stddef.h>
#include <stdint.h>
// 将原始字节编码为不含 0 分隔符的 COBS 数据。
// 参数：input 指向 size 字节；size==0 时 input 可为 NULL。
// output 指向 capacity 字节可写区；capacity==0 时可为 NULL。
// 两个区域不得重叠；输出从首字节覆盖，不保留指针，可在独立缓冲区上并发调用。
// 返回编码字节数；容量不足返回 0，失败可能已写入部分输出，不可继续发送。
// 空输入编码为单字节 01；调用者另留一字节追加帧尾 0。
// 本实现的安全容量可取 size + size / 254 + 1（还不含分隔符）。
size_t CobsEncode(const uint8_t *input, size_t size, uint8_t *output,
                  size_t capacity);
// 解码一段完整的 COBS 数据；input 中不得包含帧尾 0。
// 参数：input 指向 size 字节；size==0 时可为 NULL，直接返回 0。
// output 指向 capacity 字节可写区；capacity==0 时可为 NULL。
// 输入输出不得重叠；只覆盖解码结果区，不保存指针，不访问共享状态。
// 返回解码字节数；非法编码或容量不足返回 0，输出可能已被部分改写。
// 合法空消息 01 也返回 0，因此本接口不能用返回值区分空消息和错误；
// USB 协议要求 raw 至少 6 字节，不接受空消息。
size_t CobsDecode(const uint8_t *input, size_t size, uint8_t *output,
                  size_t capacity);
#endif
