// Copyright 2026 Agent Light Authors
// 文件/模块：ST USB Device 栈与 HAL PCD 的静态内存和底层适配。
// 版本：1.0.0（固件基线）；日期：2026-10-28。
// 用法：由 USB 栈调用 USBD_LL_* 和分配接口；HAL 回调转发总线事件。
// 约束：启动阶段由任务调用，枚举/传输回调通常在 USB ISR；不得并发重入。
// USB 栈和 HAL PCD 的适配层。USB 中断中只维护栈、复制字节和记录事件。
#include "usb_device.h"
#include "app_main.h"
#include "board.h"
#include "usbd_core.h"

// 唯一 USB 外设句柄；pData 指向设备栈句柄，由 USB ISR 与栈适配层串行访问。
PCD_HandleTypeDef g_usb_pcd;
// 唯一 CDC 静态类存储；cdc_allocated 防止同一槽被重复借出，不构成通用堆分配器。
static USBD_CDC_HandleTypeDef cdc_storage;
static bool cdc_allocated;

// 静态槽只允许一个所有者；每次重新分配先清零，避免新枚举继承旧的端点状态。
void *UsbStaticAllocate(uint32_t size) {
  if (size > sizeof(cdc_storage) || cdc_allocated) return NULL;
  cdc_allocated = true;
  memset(&cdc_storage, 0, sizeof(cdc_storage));
  return &cdc_storage;
}
// 仅回收本模块的槽标志，忽略无关地址；重新分配时才清零，不访问未知指针。
void UsbStaticFree(void *pointer) {
  if (pointer == &cdc_storage) cdc_allocated = false;
}
// 开启 USB 外设时钟并启用优先级 2 的 USB 中断。
// 参数：pcd 为 HAL 传入的外设句柄，本实现只支持唯一 USB 实例，未解引用该参数。
// 由 HAL_PCD_Init 调用；BoardInit 已完成时钟与引脚重映射，不在此重复配置 GPIO。
void HAL_PCD_MspInit(PCD_HandleTypeDef *pcd) {
  (void)pcd;
  // 重映射后的 USB 专用引脚由 USB 外设接管，不配置为 UART GPIO。
  __HAL_RCC_USB_CLK_ENABLE();
  HAL_NVIC_SetPriority(USB_IRQn, 2, 0);
  HAL_NVIC_EnableIRQ(USB_IRQn);
}
// 禁用 USB 中断和外设时钟，供 HAL 外设反初始化调用。
// 参数：pcd 为 HAL 句柄，本实现未使用；必须已停止传输，不能与 USB ISR 并发执行。
void HAL_PCD_MspDeInit(PCD_HandleTypeDef *pcd) {
  (void)pcd;
  HAL_NVIC_DisableIRQ(USB_IRQn);
  __HAL_RCC_USB_CLK_DISABLE();
}
// 服务唯一 USB 外设中断；无参数，由向量表调用，HAL 分发后续 EP0/收发/总线回调。
void USB_IRQHandler(void) { HAL_PCD_IRQHandler(&g_usb_pcd); }
// 把完整 8 字节 Setup 包交给设备栈，后续类请求经过 CheckedCdcSetup。
// 参数：pcd 为非 NULL HAL 句柄，pData 已关联设备栈，Setup 为当前请求。
// 仅 USB ISR 串行调用；栈在本次回调解析字段，不由应用保存 Setup 指针。
void HAL_PCD_SetupStageCallback(PCD_HandleTypeDef *pcd) {
  USBD_LL_SetupStage(pcd->pData, (uint8_t *)pcd->Setup);
}
// 转发主机到设备的 OUT 完成事件，CDC 最终复制数据到应用队列。
// 参数：pcd 为非 NULL 已关联句柄；ep 为有效端点号（0..7），不含方向位。
// OUT_ep[ep].xfer_buff 为 HAL 管理的借用缓冲；仅 USB ISR 调用。
void HAL_PCD_DataOutStageCallback(PCD_HandleTypeDef *pcd, uint8_t ep) {
  USBD_LL_DataOutStage(pcd->pData, ep, pcd->OUT_ep[ep].xfer_buff);
}
// 转发设备到主机的 IN 完成事件，使 CDC 栈推进传输并最终释放 TxState。
// 参数：pcd 为非 NULL 已关联句柄；ep 为有效端点号（0..7），不含方向位。
// IN_ep[ep].xfer_buff 由栈管理；仅 USB ISR 调用，不由本函数释放应用 TX 槽。
void HAL_PCD_DataInStageCallback(PCD_HandleTypeDef *pcd, uint8_t ep) {
  USBD_LL_DataInStage(pcd->pData, ep, pcd->IN_ep[ep].xfer_buff);
}
// 向设备栈转发 1 ms SOF 帧事件；不解析业务协议。
// 参数：pcd 为非 NULL、pData 已关联的 HAL 句柄；仅 USB ISR 调用。
void HAL_PCD_SOFCallback(PCD_HandleTypeDef *pcd) { USBD_LL_SOF(pcd->pData); }
// 按 Full-Speed 重置栈并通知应用开始新会话，旧请求不能跨总线 reset 生效。
// 参数：pcd 为非 NULL 已关联 HAL 句柄；仅 USB ISR 调用。
// 应用任务随后根据代次清 TX/缓存并恢复 PWM；本回调不运行协议解析。
void HAL_PCD_ResetCallback(PCD_HandleTypeDef *pcd) {
  USBD_LL_SetSpeed(pcd->pData, USBD_SPEED_FULL);
  USBD_LL_Reset(pcd->pData);
  AppUsbEvent(kModeWaitSync);
}
// 挂起栈、撤销旧 IN 传输并立即全灭，避免旧完成中断影响后续会话。
// 参数：pcd 为非 NULL 已关联 HAL 句柄；仅 USB ISR 调用，不执行延时。
// 先 Abort/清硬件 CTR 再将 TxState 清零，之后停 PWM、发布挂起代次；
// 任务消费事件后清软件 TX。这里只停 TIM2，不进入 MCU Stop 或降低系统时钟。
void HAL_PCD_SuspendCallback(PCD_HandleTypeDef *pcd) {
  USBD_LL_Suspend(pcd->pData);
  // 撤销跨挂起周期的旧 IN；清除硬件完成标志后才能释放软件 TX 槽。
  if (g_usb_device.pClassData != NULL) {
    (void)HAL_PCD_EP_Abort(pcd, CDC_IN_EP);
    PCD_CLEAR_TX_EP_CTR(pcd->Instance, CDC_IN_EP & 0x7f);
    USBD_CDC_HandleTypeDef *cdc = g_usb_device.pClassData;
    cdc->TxState = 0;
  }
  BoardPwmSuspend();
  AppUsbEvent(kModeSuspended);
}
// 恢复栈并通知应用 WAIT_SYNC，要求 PC 重新 SET_STATE，不直接复用旧灯态。
// 参数：pcd 为非 NULL 已关联 HAL 句柄；仅 USB ISR 调用，PWM 由任务稍后恢复。
void HAL_PCD_ResumeCallback(PCD_HandleTypeDef *pcd) {
  USBD_LL_Resume(pcd->pData);
  AppUsbEvent(kModeWaitSync);
}
// 向设备栈转发连接事件；不自行初始化应用状态。
// 参数：pcd 为非 NULL 已关联 HAL 句柄；仅 USB ISR 调用。
void HAL_PCD_ConnectCallback(PCD_HandleTypeDef *pcd) {
  USBD_LL_DevConnected(pcd->pData);
}
// 转发断开事件并发布新代次，使应用丢弃旧会话并等待同步。
// 参数：pcd 为非 NULL 已关联 HAL 句柄；仅 USB ISR 调用。
void HAL_PCD_DisconnectCallback(PCD_HandleTypeDef *pcd) {
  USBD_LL_DevDisconnected(pcd->pData);
  AppUsbEvent(kModeWaitSync);
}
// 转发等时 OUT 未完成事件；当前 CDC 不配置等时端点，保留 HAL 适配入口。
// 参数：pcd 为非 NULL 已关联句柄；ep 为有效端点号、不含方向位；USB ISR 调用。
void HAL_PCD_ISOOUTIncompleteCallback(PCD_HandleTypeDef *pcd, uint8_t ep) {
  USBD_LL_IsoOUTIncomplete(pcd->pData, ep);
}
// 转发等时 IN 未完成事件；当前 CDC 不配置等时端点，保留 HAL 适配入口。
// 参数：pcd 为非 NULL 已关联句柄；ep 为有效端点号、不含方向位；USB ISR 调用。
void HAL_PCD_ISOINIncompleteCallback(PCD_HandleTypeDef *pcd, uint8_t ep) {
  USBD_LL_IsoINIncomplete(pcd->pData, ep);
}

// 关联 USBD/PCD 句柄，初始化 Full-Speed USB 和固定 PMA 分区。
// 参数：device 为非 NULL 可写设备句柄，pData 将覆盖为 &g_usb_pcd；
// g_usb_pcd.pData 反向保存 device，句柄须在整个设备运行期有效。
// 返回 USBD_OK 或 HAL 初始化失败时的 USBD_FAIL；仅供单一设备栈串行调用。
// PMA 0x00..0x3f 留给 BTABLE，随后分配 EP0 OUT/IN、CDC IN/CMD/OUT，
// 地址不可重叠；PMAConfig 的端点参数含 bit7 方向，末参数为 PMA 字节偏移。
USBD_StatusTypeDef USBD_LL_Init(USBD_HandleTypeDef *device) {
  g_usb_pcd.Instance = USB;
  g_usb_pcd.Init.dev_endpoints = 8;
  g_usb_pcd.Init.speed = PCD_SPEED_FULL;
  g_usb_pcd.Init.phy_itface = PCD_PHY_EMBEDDED;
  g_usb_pcd.Init.low_power_enable = DISABLE;
  g_usb_pcd.pData = device;
  device->pData = &g_usb_pcd;
  if (HAL_PCD_Init(&g_usb_pcd) != HAL_OK) return USBD_FAIL;
  // PMA 地址互不重叠：BTABLE 0x00–0x3f；总使用量小于 1 KB。
  HAL_PCDEx_PMAConfig(&g_usb_pcd, 0x00, PCD_SNG_BUF, 0x40);
  HAL_PCDEx_PMAConfig(&g_usb_pcd, 0x80, PCD_SNG_BUF, 0x80);
  HAL_PCDEx_PMAConfig(&g_usb_pcd, CDC_IN_EP, PCD_SNG_BUF, 0xc0);
  HAL_PCDEx_PMAConfig(&g_usb_pcd, CDC_CMD_EP, PCD_SNG_BUF, 0x100);
  HAL_PCDEx_PMAConfig(&g_usb_pcd, CDC_OUT_EP, PCD_SNG_BUF, 0x110);
  return USBD_OK;
}

// HAL 返回值必须传回 USB 栈，避免将底层失败当作传输成功。
// 把 HAL 状态转换为 USB 栈状态；不保留 HAL_BUSY 与 HAL_TIMEOUT 的差别。
// 参数：result 为底层调用返回值；HAL_OK 返回 USBD_OK，其余一律 USBD_FAIL。
static USBD_StatusTypeDef UsbResult(HAL_StatusTypeDef result) {
  return result == HAL_OK ? USBD_OK : USBD_FAIL;
}
// 反初始化 PCD 并通过 MSP 回调关闭 USB IRQ/时钟。
// 参数：d 为非 NULL 设备句柄，pData 必须已关联有效 PCD；设备栈串行调用。
// 返回 USBD_OK（HAL_OK）或 USBD_FAIL（其余 HAL 状态），不负责应用队列清理。
USBD_StatusTypeDef USBD_LL_DeInit(USBD_HandleTypeDef *d) {
  return UsbResult(HAL_PCD_DeInit(d->pData));
}
// 启动 USB 外设并连接总线。
// 参数：d 为非 NULL 设备句柄，pData 必须已关联有效 PCD；设备栈串行调用。
// 返回 USBD_OK（HAL_OK）或 USBD_FAIL（其余 HAL 状态），不负责应用队列清理。
USBD_StatusTypeDef USBD_LL_Start(USBD_HandleTypeDef *d) {
  return UsbResult(HAL_PCD_Start(d->pData));
}
// 停止 USB 外设。
// 参数：d 为非 NULL 设备句柄，pData 必须已关联有效 PCD；设备栈串行调用。
// 返回 USBD_OK（HAL_OK）或 USBD_FAIL（其余 HAL 状态），不负责应用队列清理。
USBD_StatusTypeDef USBD_LL_Stop(USBD_HandleTypeDef *d) {
  return UsbResult(HAL_PCD_Stop(d->pData));
}
// 打开给定地址的端点，并将 HAL 失败转换为 USBD_FAIL。
// 参数：d 非 NULL 且 pData 已关联 PCD；ep 为端点地址，bit7=1 为 IN，低位为端点号；
// type 为 EP_TYPE_CTRL/BULK/INTR/ISOC；size 为最大包字节数，本项目 FS 数据包为 64。
// 由 USB 栈串行调用，成功返回 USBD_OK，不在本层校验参数。
USBD_StatusTypeDef USBD_LL_OpenEP(USBD_HandleTypeDef *d, uint8_t ep,
                                 uint8_t type, uint16_t size) {
  return UsbResult(HAL_PCD_EP_Open(d->pData, ep, size, type));
}
// 关闭指定方向的端点；不直接修改业务协议状态。
// 参数：d 非 NULL 且 pData 已关联 PCD；ep 为有效端点地址，bit7=1 表示 IN。
// 由设备栈串行调用，不校验端点范围；返回 USBD_OK 或 USBD_FAIL。
USBD_StatusTypeDef USBD_LL_CloseEP(USBD_HandleTypeDef *d, uint8_t ep) {
  return UsbResult(HAL_PCD_EP_Close(d->pData, ep));
}
// 清空指定方向的端点；不直接修改业务协议状态。
// 参数：d 非 NULL 且 pData 已关联 PCD；ep 为有效端点地址，bit7=1 表示 IN。
// 由设备栈串行调用，不校验端点范围；返回 USBD_OK 或 USBD_FAIL。
USBD_StatusTypeDef USBD_LL_FlushEP(USBD_HandleTypeDef *d, uint8_t ep) {
  return UsbResult(HAL_PCD_EP_Flush(d->pData, ep));
}
// 停顿指定方向的端点；不直接修改业务协议状态。
// 参数：d 非 NULL 且 pData 已关联 PCD；ep 为有效端点地址，bit7=1 表示 IN。
// 由设备栈串行调用，不校验端点范围；返回 USBD_OK 或 USBD_FAIL。
USBD_StatusTypeDef USBD_LL_StallEP(USBD_HandleTypeDef *d, uint8_t ep) {
  return UsbResult(HAL_PCD_EP_SetStall(d->pData, ep));
}
// 解除停顿指定方向的端点；不直接修改业务协议状态。
// 参数：d 非 NULL 且 pData 已关联 PCD；ep 为有效端点地址，bit7=1 表示 IN。
// 由设备栈串行调用，不校验端点范围；返回 USBD_OK 或 USBD_FAIL。
USBD_StatusTypeDef USBD_LL_ClearStallEP(USBD_HandleTypeDef *d, uint8_t ep) {
  return UsbResult(HAL_PCD_EP_ClrStall(d->pData, ep));
}
// 查询选定方向端点的软件 STALL 标志，不清除状态。
// 参数：d 非 NULL 且 pData 已关联 PCD；ep 为有效端点地址，bit7 指示 IN。
// 返回该端点 is_stall（0 未停顿，非零已停顿）；仅设备栈串行调用，不检查越界。
uint8_t USBD_LL_IsStallEP(USBD_HandleTypeDef *d, uint8_t ep) {
  PCD_HandleTypeDef *pcd = d->pData;
  return (uint8_t)((ep & 0x80) ? pcd->IN_ep[ep & 0x7f].is_stall :
                                pcd->OUT_ep[ep & 0x7f].is_stall);
}
// 将 USB 设备地址写到底层，具体生效时机由 HAL 实现。
// 参数：d 非 NULL 且 pData 已关联 PCD；address 为协议已验证的 0..127 地址。
// 由 USB 栈串行调用；返回 USBD_OK 或 USBD_FAIL。
USBD_StatusTypeDef USBD_LL_SetUSBAddress(USBD_HandleTypeDef *d, uint8_t address) {
  return UsbResult(HAL_PCD_SetAddress(d->pData, address));
}
// 把 IN 传输缓冲区交给 HAL，不复制或释放调用者存储。
// 参数：d 非 NULL 且已关联 PCD；ep 为含 IN 方向位的有效端点地址；
// data 在 size>0 时非 NULL 且至少有 size 字节可读数据，size 单位为字节；
// size==0 为零长包，data 可为 NULL。数据在完成/明确撤销前保持有效且不变。
// 由 USB 栈串行调用，返回 USBD_OK 或 USBD_FAIL；成功仅表示底层接受传输。
USBD_StatusTypeDef USBD_LL_Transmit(USBD_HandleTypeDef *d, uint8_t ep,
                                   uint8_t *data, uint16_t size) {
  return UsbResult(HAL_PCD_EP_Transmit(d->pData, ep, data, size));
}
// 把 OUT 接收缓冲区交给 HAL，准备异步接收，不复制或分配存储。
// 参数：d 非 NULL 且已关联 PCD；ep 为无 IN 方向位的有效 OUT 端点地址；
// data 为非 NULL 可写区，在接收完成/撤销前保持有效；size 为期望字节数。
// 调用者还须按 HAL 的端点包大小取整要求提供足够空间（CDC FS 用 64 字节）。
// 由设备栈串行调用，返回 USBD_OK 或 USBD_FAIL；不代表数据已到达。
USBD_StatusTypeDef USBD_LL_PrepareReceive(USBD_HandleTypeDef *d, uint8_t ep,
                                         uint8_t *data, uint16_t size) {
  return UsbResult(HAL_PCD_EP_Receive(d->pData, ep, data, size));
}
// 查询最近一次 OUT 传输累计收到的字节数。
// 参数：d 为非 NULL 已关联设备句柄；ep 为有效 OUT 端点地址。
// 由设备栈串行调用；返回 HAL 记录的接收字节数，不复制或消费缓冲区。
uint32_t USBD_LL_GetRxDataSize(USBD_HandleTypeDef *d, uint8_t ep) {
  return HAL_PCD_EP_GetRxCount(d->pData, ep);
}
// 执行 HAL 毫秒忙等待，仅供栈的允许阻塞路径使用。
// 参数：delay 为等待毫秒数；依赖 HAL SysTick 前进，不能在阻挡 SysTick 的 ISR
// 或临界区调用。当前 USB IRQ 优先级高于 SysTick，禁止在 USB 回调中使用。
void USBD_LL_Delay(uint32_t delay) { HAL_Delay(delay); }
