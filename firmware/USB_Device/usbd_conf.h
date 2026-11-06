// Copyright 2026 Agent Light Authors
// 文件/模块：ST USB Device 栈与 HAL PCD 的静态内存和底层适配。
// 版本：1.0.0（固件基线）；日期：2026-10-28。
// 用法：由 USB 栈调用 USBD_LL_* 和分配接口；HAL 回调转发总线事件。
// 约束：启动阶段由任务调用，枚举/传输回调通常在 USB ISR；不得并发重入。
#ifndef AGENT_LIGHT_FIRMWARE_USBD_CONF_H_
#define AGENT_LIGHT_FIRMWARE_USBD_CONF_H_
#include "stm32f0xx_hal.h"
#include <string.h>
#define USBD_MAX_NUM_INTERFACES 2U
#define USBD_MAX_NUM_CONFIGURATION 1U
#define USBD_MAX_STR_DESC_SIZ 64U
#define USBD_SUPPORT_USER_STRING_DESC 0U
#define USBD_SELF_POWERED 0U
#define USBD_DEBUG_LEVEL 0U
#define USBD_LPM_ENABLED 0U
#define USBD_CLASS_USER_STRING_DESC 0U
// 借出唯一的静态 CDC 类存储槽，并将其全部清零。
// 参数：size 为请求字节数，不得超过 sizeof(USBD_CDC_HandleTypeDef)。
// 返回静态槽指针；超容量或槽已借出返回 NULL。size==0 也会占用该槽。
// 由 USBD_malloc 映射供 USB 栈使用；初始化任务/ISR 必须串行，不支持多类实例。
void *UsbStaticAllocate(uint32_t size);
// 释放借出的 CDC 静态槽以供下次初始化复用，不释放堆内存。
// 参数：pointer 应为 UsbStaticAllocate() 返回值；NULL 或其他地址会被忽略。
// 不清零数据，旧引用由调用者停用；与分配串行，由 USBD_free 映射供 USB 栈调用。
void UsbStaticFree(void *pointer);
#define USBD_malloc UsbStaticAllocate
#define USBD_free UsbStaticFree
#define USBD_memset memset
#define USBD_memcpy memcpy
#define USBD_Delay HAL_Delay
#define USBD_UsrLog(...)
#define USBD_ErrLog(...)
#define USBD_DbgLog(...)
#endif
