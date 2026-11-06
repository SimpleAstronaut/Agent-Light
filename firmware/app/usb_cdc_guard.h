// Copyright 2026 Agent Light Authors
// 文件/模块：CDC EP0 控制请求的无状态白名单校验。
// 版本：1.0.0（固件基线）；日期：2026-10-28。
// 用法：在厂商 CDC Setup 和数据阶段之前调用 UsbCdcRequestValid()。
// 约束：仅校验控制请求字段和就绪条件；不解引用 USB 类存储，不处理业务协议。
#ifndef AGENT_LIGHT_FIRMWARE_APP_USB_CDC_GUARD_H_
#define AGENT_LIGHT_FIRMWARE_APP_USB_CDC_GUARD_H_
#include <stdbool.h>
#include <stdint.h>
// 在 EP0 数据阶段开始前检查 CDC 类请求；拒绝超长请求和错误方向。
// 判定请求是否可交给厂商 CDC Setup，不修改状态，可从 USB ISR 调用。
// 参数：type 为 bmRequestType（0x21 主机到设备，0xa1 设备到主机）；
// request 为 bRequest；value/index/length 分别为 wValue/wIndex/wLength，
// 均为已解码的主机字段，length 单位为字节；ready 表示已配置且类存储非 NULL。
// 返回 true 仅允许接口 0 的 SET/GET_LINE_CODING（7 字节、value=0）、
// SET_CONTROL_LINE_STATE（value<=3、零数据）或 SEND_BREAK（零数据）。
// ready=false、错误方向/接口/长度或未知请求均返回 false；不校验设备指针。
bool UsbCdcRequestValid(uint8_t type, uint8_t request, uint16_t value,
                        uint16_t index, uint16_t length, bool ready);
#endif
