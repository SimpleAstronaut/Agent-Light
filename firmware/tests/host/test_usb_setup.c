// Copyright 2026 Agent Light Authors
// 文件/模块：真实 CDC Setup 包装入口的主机隔离测试。
// 版本：1.0.0（固件基线）；日期：2026-10-28。
// 用法：在项目根运行 .\firmware\build.ps1 Host；断言失败即测试失败。
// 约束：仅在主机运行，不能证明实板电气、PWM 时序或 USB 电流符合要求。
// 直接执行产品 USB Setup 入口，仅替换主机无法运行的 USB 底层调用。
#include <assert.h>
#include <stdio.h>
#include "usb_device.h"
#include "usbd_core.h"
#include "usbd_ctlreq.h"

static unsigned forwarded, stalled;
// 验证只有已配置且类存储有效的请求到达原处理器，并累计 forwarded。
// 参数：device/request 均为非 NULL 借用指针，request 不解引用；返回 USBD_OK。
static uint8_t OriginalSetup(USBD_HandleTypeDef *device,
                              USBD_SetupReqTypedef *request) {
  (void)request;
  assert(device->dev_state == USBD_STATE_CONFIGURED);
  assert(device->pClassData != NULL);
  ++forwarded;
  return USBD_OK;
}
static uint8_t configuration[] = {9, 2, 9, 0, 2, 1, 0, 0xc0, 50};
// 返回可修改的静态配置描述符；size 为非 NULL 输出字节数指针，不转移所有权。
static uint8_t *GetConfiguration(uint16_t *size) {
  *size = sizeof(configuration); return configuration;
}
USBD_ClassTypeDef USBD_CDC = {.Setup = OriginalSetup,
                             .GetFSConfigDescriptor = GetConfiguration};
// 模拟栈初始化，仅将 device->dev_state 置默认值。
// 参数：device 非 NULL；descriptors/id 忽略；返回 USBD_OK，不访问外设。
USBD_StatusTypeDef USBD_Init(USBD_HandleTypeDef *device,
                             USBD_DescriptorsTypeDef *descriptors, uint8_t id) {
  (void)descriptors; (void)id;
  device->dev_state = USBD_STATE_DEFAULT;
  return USBD_OK;
}
// 模拟保存类表指针，使测试可调用真实 Setup 包装入口。
// 参数：device/class 均非 NULL；保存 class 借用地址，须覆盖测试生命周期；返回 USBD_OK。
USBD_StatusTypeDef USBD_RegisterClass(USBD_HandleTypeDef *device,
                                      USBD_ClassTypeDef *class) {
  device->pClass = class; return USBD_OK;
}
// 模拟启动；device 参数忽略，可为 NULL；始终返回 USBD_OK，不证明硬件可启动。
USBD_StatusTypeDef USBD_Start(USBD_HandleTypeDef *device) {
  (void)device; return USBD_OK;
}
// 模拟接口注册；device/functions 均忽略，不保存；返回 USBD_OK，不执行接口回调。
uint8_t USBD_CDC_RegisterInterface(USBD_HandleTypeDef *device,
                                   USBD_CDC_ItfTypeDef *functions) {
  (void)device; (void)functions; return USBD_OK;
}
// 模拟设置 RX 地址；device/buffer 均忽略，不保存；返回 USBD_OK，不接收数据。
uint8_t USBD_CDC_SetRxBuffer(USBD_HandleTypeDef *device, uint8_t *buffer) {
  (void)device; (void)buffer; return USBD_OK;
}
// 模拟设置 TX 地址；device/buffer/size 均忽略，不保存；返回 USBD_OK，不发送数据。
uint8_t USBD_CDC_SetTxBuffer(USBD_HandleTypeDef *device, uint8_t *buffer,
                             uint16_t size) {
  (void)device; (void)buffer; (void)size; return USBD_OK;
}
// 模拟重新挂接接收；device 忽略；返回 USBD_OK，不访问真实端点。
uint8_t USBD_CDC_ReceivePacket(USBD_HandleTypeDef *device) {
  (void)device; return USBD_OK;
}
// 模拟发送提交；device 忽略；返回 USBD_OK，不模拟 TxState 或完成中断。
uint8_t USBD_CDC_TransmitPacket(USBD_HandleTypeDef *device) {
  (void)device; return USBD_OK;
}
// 模拟字符串生成；text/unicode 忽略；size 非 NULL，覆盖为 0，不写描述符。
void USBD_GetString(uint8_t *text, uint8_t *unicode, uint16_t *size) {
  (void)text; (void)unicode; *size = 0;
}
// 累计被包装器拒绝的请求数 stalled；device/request 忽略，不访问硬件 STALL。
void USBD_CtlError(USBD_HandleTypeDef *device, USBD_SetupReqTypedef *request) {
  (void)device; (void)request; ++stalled;
}
// 使意外初始化故障立即断言失败；无参数，不模拟真实板级停机。
void BoardFatal(void) { assert(false); }
// 满足链接所需的接收桩；data/size 忽略，不复制、不保留指针，不验证 RX 队列。
void AppUsbReceive(const uint8_t *data, size_t size) { (void)data; (void)size; }

// 执行真实 UsbDeviceInit 安装的 Setup 包装器，验证配置条件和全部长度。
// 无参数；成功返回 0 并打印 PASS，任何与预期不符的转发/拒绝触发断言。
int main(void) {
  UsbDeviceInit();
  // 电路由USB供电，配置描述符不能保留ST示例的self-powered位。
  assert(configuration[7] == 0x80 && configuration[8] == 50);
  USBD_SetupReqTypedef request = {.bmRequest = 0x21, .bRequest = 0x20,
                                  .wLength = 7};
  uint8_t storage;
  for (unsigned state = USBD_STATE_DEFAULT; state <= USBD_STATE_CONFIGURED; ++state) {
    g_usb_device.dev_state = (uint8_t)state;
    for (unsigned ready = 0; ready < 2; ++ready) {
      g_usb_device.pClassData = ready ? &storage : NULL;
      unsigned before = forwarded;
      uint8_t result = g_usb_device.pClass->Setup(&g_usb_device, &request);
      bool expected = state == USBD_STATE_CONFIGURED && ready;
      assert((result == USBD_OK) == expected);
      assert(forwarded == before + (expected ? 1u : 0u));
    }
  }
  for (unsigned length = 0; length <= UINT16_MAX; ++length) {
    request.wLength = (uint16_t)length;
    unsigned before = forwarded;
    uint8_t result = g_usb_device.pClass->Setup(&g_usb_device, &request);
    assert((result == USBD_OK) == (length == 7));
    assert(forwarded == before + (length == 7 ? 1u : 0u));
  }
  assert(stalled > 65530);
  puts("PASS: real CDC Setup rejects pre-configuration, null storage, oversized EP0");
  return 0;
}
