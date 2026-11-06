// Copyright 2026 Agent Light Authors
// 文件/模块：无动态内存的 COBS 字节流帧编解码。
// 版本：1.0.0（固件基线）；日期：2026-10-28。
// 用法：用 CobsEncode() 编码后自行追加 0；解码前移除帧尾 0。
// 约束：输入输出不得重叠；独立缓冲区可重入，不涉及 USB 或 RTOS。
#include "cobs.h"

// 用 code_at 回填每段的长度码；遇到原始 0 或 254 个非零字节就开始新段。
// 每次写输出前验证容量；失败不回滚先前写入，因此返回 0 时应舍弃整个结果。
size_t CobsEncode(const uint8_t *input, size_t size, uint8_t *output,
                  size_t capacity) {
  if (capacity == 0) return 0;
  size_t write = 1, code_at = 0;
  uint8_t code = 1;
  for (size_t i = 0; i < size; ++i) {
    if (input[i] == 0) {
      output[code_at] = code;
      if (write >= capacity) return 0;
      code_at = write++;
      code = 1;
    } else {
      if (write >= capacity) return 0;
      output[write++] = input[i];
      if (++code == 0xff) {
        output[code_at] = code;
        if (write >= capacity) return 0;
        code_at = write++;
        code = 1;
      }
    }
  }
  output[code_at] = code;
  return write;
}

// 先验证长度码没有越过输入尾，再拷贝非零段并按规则补回段间的 0。
// 0xff 段不插零；解码失败可能已写出前缀，调用者不能使用部分结果。
size_t CobsDecode(const uint8_t *input, size_t size, uint8_t *output,
                  size_t capacity) {
  size_t read = 0, write = 0;
  if (size == 0) return 0;
  while (read < size) {
    uint8_t code = input[read++];
    if (code == 0 || (size_t)(code - 1) > size - read) return 0;
    for (unsigned i = 1; i < code; ++i) {
      if (write >= capacity || input[read] == 0) return 0;
      output[write++] = input[read++];
    }
    if (code != 0xff && read < size) {
      if (write >= capacity) return 0;
      output[write++] = 0;
    }
  }
  return write;
}
