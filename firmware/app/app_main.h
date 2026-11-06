// Copyright 2026 Agent Light Authors
// 文件/模块：应用调度与 USB 收发队列。
// 版本：1.0.0（固件基线）；日期：2026-10-28。
// 用法：先 BoardInit()，再调用一次 AppStart()；USB 回调仅调用 AppUsbReceive/Event。
// 约束：应用任务独占 Protocol/TX；USB ISR 写 RX 和事件，任务用临界区同步。
#ifndef AGENT_LIGHT_FIRMWARE_APP_APP_MAIN_H_
#define AGENT_LIGHT_FIRMWARE_APP_APP_MAIN_H_
#include <stddef.h>
#include <stdint.h>
#include "display.h"
// 创建静态应用任务并启动 FreeRTOS 调度器；仅在 BoardInit() 后调用一次。
// 无参数；正常运行不返回。任务创建或调度启动失败时进入 BoardFatal()。
// 必须从启动上下文调用，不能从 ISR 或已经运行的任务重复调用。
void AppStart(void);
// 从 USB OUT 回调复制收到的字节到静态 RX 环形队列，不保存 data 指针。
// 参数：data 指向至少 size 字节的可读区；size 为字节数，0 时可传 NULL。
// 仅限串行的 USB ISR 调用；不阻塞、不解析协议。队列有效容量 255 字节，
// 溢出时记录 g_rx_overflows，清队列并丢弃到下个 0 分隔符。
void AppUsbReceive(const uint8_t *data, size_t size);
// 记录总线代次变化，并立即清空 RX 队列及丢帧标志。
// 参数：mode 为 kModeWaitSync（reset/resume/断开）或 kModeSuspended。
// 仅限 USB ISR；覆盖此前未消费的事件，任务稍后清 TX/协议缓存。
// 本函数不停止 PWM，挂起调用者必须先执行 BoardPwmSuspend()。
void AppUsbEvent(DisplayMode mode);
// 供调试器读取的应用任务历史最小剩余栈量，单位为 StackType_t 字，非字节。
// 每轮由应用任务更新；不代表当前瞬时空闲栈。
extern volatile uint32_t g_app_stack_free_words;
// 供调试器读取的 RX 队列溢出次数；由 USB ISR 增加，uint32_t 自然回绕。
extern volatile uint32_t g_rx_overflows;
#endif
