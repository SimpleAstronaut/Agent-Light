// Copyright 2026 Agent Light Authors
// 文件/模块：FreeRTOS V10.0.1 静态任务与中断配置。
// 版本：1.0.0（固件基线）；日期：2026-10-28。
// 用法：由 FreeRTOS.h 自动包含；增减功能时同步审查 RAM 和原生任务钩子。
// 所有任务静态分配；没有 heap_x、软件定时器或后台动态队列。
#ifndef AGENT_LIGHT_FIRMWARE_FREERTOS_CONFIG_H_
#define AGENT_LIGHT_FIRMWARE_FREERTOS_CONFIG_H_
#include <stdint.h>
extern uint32_t SystemCoreClock;
// 供 configASSERT 调用的致命故障入口；无参数，禁用中断并全灭后不返回。
// 完整使用契约见 app/board.h；此处单独声明以避免配置头循环包含。
void BoardFatal(void);
#define configUSE_PREEMPTION 1
#define configCPU_CLOCK_HZ SystemCoreClock
// RTOS tick 为 1 ms，与 HAL_IncTick 共用 SysTick；应用用 pdMS_TO_TICKS 转换单位。
#define configTICK_RATE_HZ 1000U
#define configMAX_PRIORITIES 3
#define configMINIMAL_STACK_SIZE 96U
#define configMAX_TASK_NAME_LEN 12
#define configUSE_16_BIT_TICKS 0
#define configIDLE_SHOULD_YIELD 0
#define configUSE_IDLE_HOOK 1
#define configUSE_TICK_HOOK 0
#define configUSE_TIMERS 0
#define configUSE_MUTEXES 0
#define configUSE_RECURSIVE_MUTEXES 0
#define configUSE_COUNTING_SEMAPHORES 0
#define configUSE_CO_ROUTINES 0
#define configUSE_TRACE_FACILITY 0
#define configGENERATE_RUN_TIME_STATS 0
#define configSUPPORT_STATIC_ALLOCATION 1
#define configSUPPORT_DYNAMIC_ALLOCATION 0
#define configCHECK_FOR_STACK_OVERFLOW 2
#define configUSE_MALLOC_FAILED_HOOK 0
#define configUSE_PORT_OPTIMISED_TASK_SELECTION 0
#define configUSE_TICKLESS_IDLE 0
// Cortex-M0 使用全局屏蔽实现临界区；USB IRQ=2、SysTick/PendSV=3。
// USB ISR 不调用非 FromISR 的 RTOS API，本项目甚至无需调用队列型 FromISR API。
#define configKERNEL_INTERRUPT_PRIORITY 3
#define INCLUDE_vTaskDelay 1
#define INCLUDE_vTaskDelayUntil 1
#define INCLUDE_vTaskDelete 0
#define INCLUDE_vTaskSuspend 0
#define INCLUDE_uxTaskGetStackHighWaterMark 1
#define INCLUDE_xTaskGetSchedulerState 1
#define configASSERT(expr) do { if (!(expr)) BoardFatal(); } while (0)
#define vPortSVCHandler SVC_Handler
#define xPortPendSVHandler PendSV_Handler
#endif
