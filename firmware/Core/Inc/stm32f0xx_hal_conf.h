// Copyright 2026 Agent Light Authors
// 文件/模块：STM32F0 HAL 模块、晶振常量与节拍配置。
// 版本：1.0.0（固件基线）；日期：2026-10-28。
// 用法：通过 USE_HAL_DRIVER 引入；启用新模块时同步增加包含和构建源文件。
#ifndef AGENT_LIGHT_FIRMWARE_HAL_CONF_H_
#define AGENT_LIGHT_FIRMWARE_HAL_CONF_H_
#define HAL_MODULE_ENABLED
#define HAL_CORTEX_MODULE_ENABLED
#define HAL_GPIO_MODULE_ENABLED
#define HAL_DMA_MODULE_ENABLED
#define HAL_RCC_MODULE_ENABLED
#define HAL_PCD_MODULE_ENABLED
#define HAL_TIM_MODULE_ENABLED
#define HAL_FLASH_MODULE_ENABLED
#define HAL_PWR_MODULE_ENABLED
#define HSE_VALUE 8000000U
#define HSE_STARTUP_TIMEOUT 100U
#define HSI_VALUE 8000000U
#define HSI48_VALUE 48000000U
#define HSI14_VALUE 14000000U
#define LSI_VALUE 40000U
#define LSE_VALUE 32768U
#define LSE_STARTUP_TIMEOUT 5000U
#define VDD_VALUE 3300U
#define TICK_INT_PRIORITY 3U
// 这是 HAL 内部配置开关，不代表未使用 FreeRTOS；调度由原生任务层管理。
// HAL_Delay 仍为忙等待，任务周期用 vTaskDelay/Until，中断中禁止延时。
#define USE_RTOS 0U
#define PREFETCH_ENABLE 1U
#define INSTRUCTION_CACHE_ENABLE 0U
#define USE_SPI_CRC 0U
#include "stm32f0xx_hal_rcc.h"
#include "stm32f0xx_hal_gpio.h"
#include "stm32f0xx_hal_dma.h"
#include "stm32f0xx_hal_cortex.h"
#include "stm32f0xx_hal_flash.h"
#include "stm32f0xx_hal_pwr.h"
#include "stm32f0xx_hal_pcd.h"
#include "stm32f0xx_hal_tim.h"
#define assert_param(expr) ((void)0U)
#endif
