// Copyright 2026 Agent Light Authors
// 文件/模块：USB CDC 描述符、控制入口防护与异步收发接口。
// 版本：1.0.0（固件基线）；日期：2026-10-28。
// 用法：BoardInit() 后在任务中调用一次 UsbDeviceInit()；发送前屏蔽 USB IRQ。
// 约束：CDC 数据转入应用 RX 队列；发送缓冲区由调用者持有直至完成或撤销。
#include "usb_device.h"
#include "app_main.h"
#include "board.h"
#include "usbd_core.h"
#include "usbd_ctlreq.h"
#include "usb_cdc_guard.h"

// 唯一设备栈实例；CDC 类状态由 usbd_conf.c 的静态槽提供。
USBD_HandleTypeDef g_usb_device;
// Full-Speed OUT 的 64 字节永久接收缓冲；回调复制完数据才重新挂接。
static uint8_t rx_packet[64];
// 共享字符串工作区；控制传输串行使用，下次字符串请求可能覆盖内容。
static uint8_t string_descriptor[64];
// 完整 96 位 UID 的 24 个 UTF-16LE 十六进制字符，加 2 字节描述符头。
static uint8_t serial_descriptor[50];
// 支持 en-US（语言 ID 0x0409）的静态语言列表。
static uint8_t language_descriptor[] = {4, USB_DESC_TYPE_STRING, 9, 4};
// 实验室开发使用 ST 示例 VID/PID。发布产品前必须取得有权使用的标识。
static uint8_t device_descriptor[] = {
  18, USB_DESC_TYPE_DEVICE, 0, 2, 2, 0, 0, 64,
  0x83, 0x04, 0x40, 0x57, 0, 1, 1, 2, 3, 1
};
// 返回静态设备描述符，不转移所有权。
// 参数：speed 为栈传入的速度，此 Full-Speed 实现忽略；size 为非 NULL 输出字节数。
// 由 USB 栈串行调用；返回地址在固件整个运行期有效。
static uint8_t *DeviceDescriptor(USBD_SpeedTypeDef speed, uint16_t *size) {
  (void)speed; *size = sizeof(device_descriptor); return device_descriptor;
}
// 返回静态语言 ID 描述符；调用者不得释放。
// 参数：speed 未使用；size 为非 NULL 输出指针，覆盖为描述符字节数。
static uint8_t *LanguageDescriptor(USBD_SpeedTypeDef speed, uint16_t *size) {
  (void)speed; *size = sizeof(language_descriptor); return language_descriptor;
}
// 将短 ASCII 文本转成 UTF-16LE USB 字符串，写入共享静态工作区。
// 参数：text 为非 NULL、NUL 结尾的 ASCII，最多 31 字符；size 非 NULL，输出总字节数。
// 返回借用地址，下次调用可能覆盖；仅 USB 栈串行使用，不可并发或保存作长期副本。
static uint8_t *StringDescriptor(const char *text, uint16_t *size) {
  USBD_GetString((uint8_t *)text, string_descriptor, size);
  return string_descriptor;
}
// 返回厂家名的共享字符串描述符，借用地址在下次字符串生成前有效。
// 参数：speed 未使用；size 为非 NULL 输出指针，覆盖为 UTF-16LE 描述符字节数。
static uint8_t *ManufacturerDescriptor(USBD_SpeedTypeDef speed, uint16_t *size) {
  (void)speed; return StringDescriptor("Agent Light", size);
}
// 返回产品名的共享字符串描述符，借用地址在下次字符串生成前有效。
// 参数：speed 未使用；size 为非 NULL 输出指针，覆盖为 UTF-16LE 描述符字节数。
static uint8_t *ProductDescriptor(USBD_SpeedTypeDef speed, uint16_t *size) {
  (void)speed; return StringDescriptor("Agent Light Rev A", size);
}
// 生成芯片唯一序列号描述符，用完整 12 字节 UID 减少设备路径碰撞。
// 参数：speed 未使用；size 为非 NULL 输出指针，覆盖为 50 字节。
// 返回独立静态缓冲，不转移所有权；必须在目标芯片运行，主机测试不能执行 UID 读取。
static uint8_t *SerialDescriptor(USBD_SpeedTypeDef speed, uint16_t *size) {
  (void)speed;
  // 完整 96 位芯片 UID，固定 24 个十六进制字符，避免设备路径碰撞。
  const uint8_t *uid = (const uint8_t *)UID_BASE;
  const char hex[] = "0123456789ABCDEF";
  serial_descriptor[0] = sizeof(serial_descriptor);
  serial_descriptor[1] = USB_DESC_TYPE_STRING;
  for (unsigned i = 0; i < 12; ++i) {
    serial_descriptor[2 + i * 4] = (uint8_t)hex[uid[i] >> 4];
    serial_descriptor[3 + i * 4] = 0;
    serial_descriptor[4 + i * 4] = (uint8_t)hex[uid[i] & 15];
    serial_descriptor[5 + i * 4] = 0;
  }
  *size = sizeof(serial_descriptor);
  return serial_descriptor;
}
// 返回配置名称字符串（不是配置描述符主体）的共享字符串描述符，借用地址在下次字符串生成前有效。
// 参数：speed 未使用；size 为非 NULL 输出指针，覆盖为 UTF-16LE 描述符字节数。
static uint8_t *ConfigurationDescriptor(USBD_SpeedTypeDef speed, uint16_t *size) {
  (void)speed; return StringDescriptor("CDC Configuration", size);
}
// 返回接口名称字符串的共享字符串描述符，借用地址在下次字符串生成前有效。
// 参数：speed 未使用；size 为非 NULL 输出指针，覆盖为 UTF-16LE 描述符字节数。
static uint8_t *InterfaceDescriptor(USBD_SpeedTypeDef speed, uint16_t *size) {
  (void)speed; return StringDescriptor("Agent Light CDC", size);
}
static USBD_DescriptorsTypeDef descriptors = {
  DeviceDescriptor, LanguageDescriptor, ManufacturerDescriptor,
  ProductDescriptor, SerialDescriptor, ConfigurationDescriptor,
  InterfaceDescriptor
};
// 把永久接收区挂到 CDC 类，供首次 OUT 接收使用；无参数，返回 USBD_OK。
// 由 USB 栈在类存储建立后串行调用；本项目无需创建动态资源。
static int8_t CdcInit(void) {
  USBD_CDC_SetRxBuffer(&g_usb_device, rx_packet);
  return USBD_OK;
}
// 结束 CDC 接口；无参数，无应用资源需释放，返回 USBD_OK，类存储由栈另行释放。
static int8_t CdcDeInit(void) { return USBD_OK; }
// 保存/查询虚拟串口 line coding；DTR/RTS 与 BREAK 不改变灯态。
// 参数：cmd 为 CDC 请求码；size 为数据字节数；对 SET/GET_LINE_CODING，
// data 必须非 NULL 且可访问 7 字节（SET 读、GET 写）。零数据控制请求中，
// data 可能是 Setup 结构地址，本函数不解引用；所有指针仅在调用中借用。
// 由 USB 栈串行调用，返回 USBD_OK；前置 CheckedCdcSetup 已限制字段及就绪条件。
// 静态 line_coding 跨 reset 保留；115200/8N1 只是 CDC 信息，不配置物理 UART。
static int8_t CdcControl(uint8_t cmd, uint8_t *data, uint16_t size) {
  static uint8_t line_coding[7] = {0, 0xc2, 1, 0, 0, 0, 8};
  if (cmd == CDC_SET_LINE_CODING && size == 7) memcpy(line_coding, data, 7);
  else if (cmd == CDC_GET_LINE_CODING && size == 7) memcpy(data, line_coding, 7);
  // DTR/RTS 仅为虚拟串口控制信息，不改变业务灯态。
  return USBD_OK;
}
// 将本次 OUT 数据复制到应用队列，然后重新挂接接收区并启动下一包。
// 参数：data 为非 NULL、至少 *size 字节的借用接收区；size 为非 NULL 长度指针，
// 由 Full-Speed CDC 提供，*size<=64 字节，本函数不修改它。
// 仅 USB ISR 调用；返回 USBD_OK。重挂接前 AppUsbReceive 已完成复制，不保留旧包。
static int8_t CdcReceive(uint8_t *data, uint32_t *size) {
  AppUsbReceive(data, *size);
  USBD_CDC_SetRxBuffer(&g_usb_device, rx_packet);
  USBD_CDC_ReceivePacket(&g_usb_device);
  return USBD_OK;
}
static USBD_CDC_ItfTypeDef interface = {
  CdcInit, CdcDeInit, CdcControl, CdcReceive
};
// 保存原厂类 Setup 入口；仅 UsbDeviceInit 写一次，CheckedCdcSetup 用它转发。
static uint8_t (*original_setup)(USBD_HandleTypeDef *, USBD_SetupReqTypedef *);
// 在厂商代码接触 EP0 数据缓冲前拦截非法类请求。
// 参数：device 为非 NULL 设备句柄；request 为非 NULL 已解析 Setup 字段，
// 两者均只借用，由 USB 栈串行调用（通常在 USB ISR）。
// 类请求未配置、无类存储或字段越界时使 EP0 STALL 并返回 USBD_FAIL；
// 其余请求返回原 Setup 的状态。标准请求仍交由原处理器按 USB 栈语义检查。
static uint8_t CheckedCdcSetup(USBD_HandleTypeDef *device,
                               USBD_SetupReqTypedef *request) {
  if ((request->bmRequest & USB_REQ_TYPE_MASK) == USB_REQ_TYPE_CLASS &&
      !UsbCdcRequestValid(request->bmRequest, request->bRequest,
                          request->wValue, request->wIndex, request->wLength,
                          device->dev_state == USBD_STATE_CONFIGURED &&
                          device->pClassData != NULL)) {
    USBD_CtlError(device, request);
    return USBD_FAIL;
  }
  return original_setup(device, request);
}
// 先安装防护再启动设备，避免主机在枚举早期触达未校验的 CDC Setup。
void UsbDeviceInit(void) {
  // ST 的此版 CDC 在 Setup 中直接使用主机长度，需在接收数据前设边界。
  // 只替换函数指针，不复制整张类表，以节约 STM32F042 的有限 SRAM。
  original_setup = USBD_CDC.Setup;
  USBD_CDC.Setup = CheckedCdcSetup;
  // 此版ST CDC配置描述符写死self-powered，须与Rev A实际供电一致。
  uint16_t configuration_size;
  uint8_t *configuration = USBD_CDC.GetFSConfigDescriptor(&configuration_size);
  if (configuration_size < 9) BoardFatal();
  configuration[7] = 0x80;  // 总线供电，无远程唤醒。
  configuration[8] = 50;    // 最大声明100mA；实际电流仍需实测。
  if (USBD_Init(&g_usb_device, &descriptors, 0) != USBD_OK ||
      USBD_RegisterClass(&g_usb_device, &USBD_CDC) != USBD_OK ||
      USBD_CDC_RegisterInterface(&g_usb_device, &interface) != USBD_OK ||
      USBD_Start(&g_usb_device) != USBD_OK) BoardFatal();
}
// 先检查类存储是否存在，防止 reset/枚举期间解引用尚未建立的 CDC 句柄。
bool UsbTransmitBusy(void) {
  USBD_CDC_HandleTypeDef *cdc = g_usb_device.pClassData;
  return cdc == NULL || cdc->TxState != 0;
}
// 检查配置状态和 TxState 后把调用者地址借给栈，不复制数据。
// 该版 ST TransmitPacket 不向上传递 USBD_LL_Transmit 的失败；true 仅表示类层接受。
bool UsbTransmit(uint8_t *data, uint16_t size) {
  if (g_usb_device.dev_state != USBD_STATE_CONFIGURED || UsbTransmitBusy()) {
    return false;
  }
  USBD_CDC_SetTxBuffer(&g_usb_device, data, size);
  return USBD_CDC_TransmitPacket(&g_usb_device) == USBD_OK;
}
