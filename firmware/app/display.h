// Copyright 2026 Agent Light Authors
// 文件/模块：纯软件灯态、闪烁相位和链路超时状态机。
// 版本：1.0.0（固件基线）；日期：2026-10-28。
// 用法：先 DisplayInit()，再由单一任务 Set/Poll/GetLeds，并将结果交给板级驱动。
// 约束：所有时间参数均为同一 uint32_t 单调毫秒时基；不访问寄存器。
#ifndef AGENT_LIGHT_FIRMWARE_APP_DISPLAY_H_
#define AGENT_LIGHT_FIRMWARE_APP_DISPLAY_H_
#include <stdbool.h>
#include <stdint.h>

// 定义设备显示模式；与 USB STATUS mode 的 0..4 数值保持一致。
typedef enum {
  kModeBoot, kModeWaitSync, kModeActive, kModeLinkLost, kModeSuspended
} DisplayMode;
// 定义 PC 下发的五种业务灯态；完成保持策略在 PC，不在固件。
typedef enum {
  kStateIdle, kStateRunning, kStateAttention, kStateError, kStateCompleted
} DisplayState;
// 承载三路 0..100 百分比占空比；按值传递给板级驱动，不包含定时器计数。
typedef struct { uint8_t red, yellow, green; } LedLevels;
// 保存一个显示状态机，由应用任务独占；state==0xff 表示尚无有效业务状态。
// revision 仅在 revision_valid 为 true 时有效；时间字段均为 uint32_t 毫秒。
typedef struct {
  DisplayMode mode;
  uint8_t state;
  uint8_t brightness;
  bool revision_valid;
  uint32_t revision;
  uint32_t mode_since_ms;
  uint32_t last_valid_ms;
} Display;

// 所有接口仅由应用任务调用。时间为单调 uint32 毫秒，支持一次回绕。
// 覆盖初始化 display，进入 kModeBoot，默认亮度 35%、状态 0xff、revision 无效。
// 参数：display 为非 NULL 可写对象；now 为当前单调毫秒值。
// 仅由拥有对象的应用任务调用；不分配内存、不保存外部指针。
void DisplayInit(Display *display, uint32_t now);
// 切换显示模式并重置闪烁相位起点，不修改业务状态、revision 或链路时间。
// 参数：display 为非 NULL 已初始化对象；mode 为有效 DisplayMode；now 为当前毫秒值。
// 仅应用任务调用；即使 mode 未变也会重置相位，调用者应避免无意义重复设置。
void DisplayModeSet(Display *display, DisplayMode mode, uint32_t now);
// 输入已经过协议验证。只有 SET_STATE 可以恢复 ACTIVE。
// 应用已验证的状态并刷新有效请求时间，必要时进入 ACTIVE 并重启相位。
// 参数：display 为非 NULL 已初始化对象；revision 为通过新旧判定的 uint32_t 版本；
// state 为 kStateIdle..kStateCompleted；brightness 为 20..100 整数百分比；
// now 为当前毫秒值。此层不校验 revision、状态或亮度，调用者负责验证。
// 仅应用任务调用；相同 ACTIVE 状态下仅变亮度/revision 不重启闪烁相位。
// 将 revision 标为有效；从 WAIT_SYNC/LINK_LOST 恢复必须使用已接受的 SET_STATE。
void DisplaySet(Display *display, uint32_t revision, uint8_t state,
                uint8_t brightness, uint32_t now);
// 推进上电 300 ms 自检结束和 ACTIVE 下 5000 ms 链路超时的模式转换。
// 参数：display 为非 NULL 已初始化对象；now 为当前单调毫秒值。
// 仅应用任务周期调用；无符号差值支持一次 uint32_t 回绕，不能跨整周期不轮询。
// 只更新软件模式，不直接驱动 LED；COMPLETED 的保持时间由 PC 管理。
void DisplayPoll(Display *display, uint32_t now);
// 返回三路 0–100% 占空比；不访问硬件，也不执行完成保持计时。
// 根据显示模式和相位生成三路 LED 占空比，不改变对象或访问硬件。
// 参数：display 为非 NULL 已初始化对象；now 为当前毫秒值，与其他接口同源。
// 返回 red/yellow/green 的 0..100 百分比（要求写入的亮度合法）。
// 仅应用任务调用；WAIT_SYNC/LINK_LOST 黄 1 Hz，ERROR 红 2 Hz，均为 50% 占空比；
// 挂起/IDLE 全灭，自检红黄绿各 100 ms。需先 Poll 才推进超时模式。
LedLevels DisplayGetLeds(const Display *display, uint32_t now);
#endif
