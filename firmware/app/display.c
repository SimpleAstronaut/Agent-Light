// Copyright 2026 Agent Light Authors
// 文件/模块：纯软件灯态、闪烁相位和链路超时状态机。
// 版本：1.0.0（固件基线）；日期：2026-10-28。
// 用法：先 DisplayInit()，再由单一任务 Set/Poll/GetLeds，并将结果交给板级驱动。
// 约束：所有时间参数均为同一 uint32_t 单调毫秒时基；不访问寄存器。
#include "display.h"
#include <string.h>

// 清零后 mode 自然为枚举首项 kModeBoot；0xff 表示尚无来自 PC 的业务状态。
void DisplayInit(Display *display, uint32_t now) {
  memset(display, 0, sizeof(*display));
  display->brightness = 35;
  display->state = 0xff;
  display->mode_since_ms = now;
  display->last_valid_ms = now;
}

// 统一记录模式的进入时刻，使等待、断链和错误灯效以同一相位规则计算。
void DisplayModeSet(Display *display, DisplayMode mode, uint32_t now) {
  display->mode = mode;
  display->mode_since_ms = now;
}

// 仅模式或业务状态改变才重置相位；重复 SET 与亮度变化不会让闪烁重新开始。
// 链路恢复时模式已不是 ACTIVE，因此即使业务内容相同也会重新进入 ACTIVE。
void DisplaySet(Display *display, uint32_t revision, uint8_t state,
                uint8_t brightness, uint32_t now) {
  bool changed = display->mode != kModeActive || display->state != state;
  display->revision = revision;
  display->revision_valid = true;
  display->state = state;
  display->brightness = brightness;
  display->last_valid_ms = now;
  if (changed) DisplayModeSet(display, kModeActive, now);
}

// 以 uint32_t 差值判定持续时间，避免直接比较绝对截止时间在计数器回绕时失效。
void DisplayPoll(Display *display, uint32_t now) {
  if (display->mode == kModeBoot &&
      (uint32_t)(now - display->mode_since_ms) >= 300) {
    DisplayModeSet(display, kModeWaitSync, now);
  }
  if (display->mode == kModeActive &&
      (uint32_t)(now - display->last_valid_ms) >= 5000) {
    DisplayModeSet(display, kModeLinkLost, now);
  }
}

// 先处理挂起/自检/等待等模式，再映射业务状态；未识别状态也保持全灭。
LedLevels DisplayGetLeds(const Display *display, uint32_t now) {
  LedLevels result = {0, 0, 0};
  uint32_t elapsed = now - display->mode_since_ms;
  if (display->mode == kModeSuspended) return result;
  if (display->mode == kModeBoot) {
    if (elapsed < 100) result.red = 35;
    else if (elapsed < 200) result.yellow = 35;
    else if (elapsed < 300) result.green = 35;
    return result;
  }
  if (display->mode == kModeWaitSync || display->mode == kModeLinkLost) {
    if (elapsed % 1000 < 500) result.yellow = display->brightness;
    return result;
  }
  switch (display->state) {
    case kStateRunning: result.yellow = display->brightness; break;
    case kStateAttention: result.red = display->brightness; break;
    case kStateError:
      if (elapsed % 500 < 250) result.red = display->brightness;
      break;
    case kStateCompleted: result.green = display->brightness; break;
    default: break;
  }
  return result;
}
