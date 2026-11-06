// Copyright 2026 Agent Light Authors
// 文件/模块：Rev A 时钟、USB 引脚映射和三色 PWM 板级驱动。
// 版本：1.0.0（固件基线）；日期：2026-10-28。
// 用法：启动时调用 BoardInit()；任务用 BoardSetLeds() 更新三路百分比占空比。
// 约束：挂起/恢复只控制 TIM2 计数器；异常统一经 BoardFatal() 全灭停机。
#ifndef AGENT_LIGHT_FIRMWARE_APP_BOARD_H_
#define AGENT_LIGHT_FIRMWARE_APP_BOARD_H_
#include "display.h"
#include "stm32f0xx_hal.h"
// 初始化 HAL、48 MHz HSI48/USB CRS、引脚映射和初始全灭的 10 kHz PWM。
// 无参数；启动阶段、调度器运行前调用一次。时钟/PWM 配置失败不返回，
// 转入 BoardFatal()。需使用 STM32F042F6P6 Rev A 的 PA0/1/2 接线。
void BoardInit(void);
// 覆盖 TIM2 三路占空比；BoardInit() 成功后使用。
// 参数：levels.red/yellow/green 分别为红/黄/绿的 0..100 整数百分比。
// 不校验或钳位越界输入；比较值随预装载更新生效，不自行恢复已停计数器。
// 任务与 USB 挂起 ISR 共享寄存器；任务调用时必须屏蔽 USB IRQ。
void BoardSetLeds(LedLevels levels);
// 禁用中断、清零并禁用已使能的 TIM2 输出，随后永久等待，不返回。
// 无参数；可从启动、任务、ISR 或异常上下文调用，不依赖调度器或延时。
// 不尝试重启，也不写 Flash；用于配置失败、断言及栈溢出等致命故障。
void BoardFatal(void);
// 在 BoardInit() 后立即全灭并停止 TIM2 计数器。
// 无参数；供 USB 挂起 ISR 使用。强制装载零比较值，避免停表时留下高电平。
// 任务若调用，须与 USB ISR 串行；不改变 HAL 通道状态或软件业务状态。
void BoardPwmSuspend(void);
// 在 BoardInit() 后重新使能 TIM2 计数器，允许重复调用。
// 无参数；应用任务在总线 reset/resume 后调用，并须屏蔽 USB IRQ。
// 不重新启动 HAL 通道、不恢复旧亮度；随后由 BoardSetLeds() 写新灯态。
void BoardPwmResume(void);
#endif
