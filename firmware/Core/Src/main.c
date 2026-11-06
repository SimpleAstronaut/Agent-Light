// Copyright 2026 Agent Light Authors
// 文件/模块：复位后的 C 入口、系统节拍与异常处理。
// 版本：1.0.0（固件基线）；日期：2026-10-28。
// 用法：由启动文件进入 main；用户无需直接调用异常/中断入口。
#include "app_main.h"
#include "board.h"
#include "FreeRTOS.h"
#include "task.h"

// 声明 FreeRTOS Cortex-M0 端口的节拍入口；由本文件 SysTick_Handler 转发。
// 无参数，由端口实现；只能在调度器启动后的 SysTick ISR 中调用。
void xPortSysTickHandler(void);
// 推进 1 ms HAL 时基，并在调度器启动后驱动 FreeRTOS 节拍。
// 无参数；由向量表在 SysTick ISR 调用。启动前不得调用 RTOS 节拍处理器。
void SysTick_Handler(void) {
  HAL_IncTick();
  if (xTaskGetSchedulerState() != taskSCHEDULER_NOT_STARTED) {
    xPortSysTickHandler();
  }
}
// 在不可屏蔽异常中全灭停机；无参数，不返回，不依赖任务调度。
void NMI_Handler(void) { BoardFatal(); }
// 在硬故障中全灭停机；无参数，不返回，不解析可能损坏的栈。
void HardFault_Handler(void) { BoardFatal(); }
// 初始化 Rev A 板级外设后启动原生 FreeRTOS 应用。
// 无参数；由 Reset_Handler 的 C 运行库调用一次，正常路径不返回。
// 末尾 return 0 仅满足 C 入口签名，AppStart 失败也会进入 BoardFatal。
int main(void) {
  BoardInit();
  AppStart();
  return 0;
}
