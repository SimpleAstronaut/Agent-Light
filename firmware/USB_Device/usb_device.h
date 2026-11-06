// Copyright 2026 Agent Light Authors
// 文件/模块：USB CDC 描述符、控制入口防护与异步收发接口。
// 版本：1.0.0（固件基线）；日期：2026-10-28。
// 用法：BoardInit() 后在任务中调用一次 UsbDeviceInit()；发送前屏蔽 USB IRQ。
// 约束：CDC 数据转入应用 RX 队列；发送缓冲区由调用者持有直至完成或撤销。
#ifndef AGENT_LIGHT_FIRMWARE_USB_DEVICE_H_
#define AGENT_LIGHT_FIRMWARE_USB_DEVICE_H_
#include <stdbool.h>
#include "usbd_cdc.h"
// 唯一 USB Device 栈句柄；由本模块持有，PCD 通过 pData 与它互指。
extern USBD_HandleTypeDef g_usb_device;
// 唯一 HAL PCD 句柄；由 usbd_conf.c 初始化，USB_IRQHandler 使用它服务中断。
extern PCD_HandleTypeDef g_usb_pcd;
// 安装 CDC Setup 防护、修正总线供电描述符，并启动唯一 USB CDC 设备。
// 无参数；BoardInit() 后从应用任务调用且全生命周期只能调用一次。
// 重复调用会把包装器保存为 original_setup 并递归，因此不能作为恢复接口。
// 初始化失败进入 BoardFatal()，不返回；成功后 USB ISR 可立即到达。
void UsbDeviceInit(void);
// 向 CDC IN 异步提交数据，不复制调用者缓冲区。
// 参数：data 为非 NULL、至少 size 字节且发送期间不变的缓冲区；size 为字节数，
// 本项目响应最大 40 字节。缓冲区在完成或总线层明确撤销前必须有效。
// 仅应用任务调用，并须在临界区屏蔽 USB IRQ，连同 Busy 检查和缓冲区管理串行化。
// 返回 true 表示 USB 栈已接受提交，并非主机已收到；false 表示未配置、忙或提交失败。
// 成功后通过 UsbTransmitBusy() 等待完成；失败可在缓冲仍有效时下轮重试。
bool UsbTransmit(uint8_t *data, uint16_t size);
// 查询 CDC 类存储不存在或 TxState 非零，即不能复用发送缓冲区。
// 无参数；返回 true 表示不可复用，false 表示该时刻无发送占用。
// 仅应用任务在屏蔽 USB IRQ 的临界区调用；不代表设备一定已配置，
// 也不保证主机已经消费数据，后续提交仍需检查 UsbTransmit() 返回值。
bool UsbTransmitBusy(void);
#endif
