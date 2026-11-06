# 固件模块与依赖接口说明

版本：1.0.0（对应固件基线，不改变 USB 版本编码）；日期：2026-10-28。

本说明基于 `contracts/toolchain.lock.json` 锁定的 STM32CubeF0 v1.11.5、
其附带的 FreeRTOS V10.0.1、USB Device 库及 HAL 源码。接口行为以本地锁定源码为准。
厂商源码保留原注释和许可证；项目自己的包装器、回调在定义处说明参数与限制。

## 阅读与使用顺序

1. `Core/Src/main.c` 的 `main()` 先调用 `BoardInit()`，再调用 `AppStart()`。
2. `app/app_main.c` 静态创建应用任务，先自检，再启动 USB；正常路径不返回。
3. USB OUT → HAL/USBD 回调 → `AppUsbReceive()` → RX 队列 → `ProtocolFeed()`。
4. 协议校验/事务处理 → `DisplaySet()` → `DisplayGetLeds()` → `BoardSetLeds()`。
5. 响应 → `QueueReply()` 复制 → `UsbTransmit()` 借用静态 TX → 完成后释放发送槽。

任务每 5 ms 推进协议/显示，单轮最多消费 64 字节；发送槽占用时暂停消费输入。
USB ISR 不解析协议或延时，只维护 USB 栈、搬运字节、记录事件，挂起时立即停 PWM。
ISR 发布的事件代次用于任务隔离旧会话。接口默认不检查 NULL，只有明确写明可空时才可传空。

无硬件时可运行：

```powershell
.\firmware\build.ps1 Host
py -3.14 firmware/tools/protocol_reference.py --check
.\firmware\build.ps1 Debug
.\firmware\build.ps1 Release
py -3.14 firmware/tools/verify_artifacts.py
```

实板步骤见 `README.md` 与 `docs/cubemx-and-bringup.md`。
`hil.py` 不带 `--port` 只列端口；指定端口后会实际下发灯态。

## FreeRTOS 原生 API

以下任务 API 不得从 ISR 调用。`TickType_t` 是 RTOS tick，本项目 1000 Hz；
栈深度和栈水位的单位是 `StackType_t` 字，本 Cortex-M0 上每字 4 字节。

| 接口 | 参数、返回值与本项目使用约束 |
|---|---|
| `xTaskCreateStatic(code, name, depth, argument, priority, stack, tcb)` | `code` 为非空、不得返回的任务函数；`name` 为任务名，内核复制到 TCB；`depth` 为栈字数；`argument` 透传，可空；`priority` 为任务优先级；`stack`/`tcb` 为调用者持有的静态可写存储，需存活整个任务生命周期。返回任务句柄，失败为空。本项目 depth=384、priority=1，且通过断言检查返回值。 |
| `vTaskStartScheduler()` | 无参数，创建 Idle 并启动调度；正常不返回。使用静态分配钩子，不链接 heap_x；异常返回后应用调用 `BoardFatal()`。 |
| `vTaskDelay(ticks)` | `ticks` 为相对阻塞的 tick 数；无返回值。自检使用 `pdMS_TO_TICKS(100)`，不在 ISR/临界区使用。 |
| `vTaskDelayUntil(previous, increment)` | `previous` 为非空的上次唤醒 tick 指针，首次由 `xTaskGetTickCount()` 初始化，函数原地推进；`increment` 为非零周期 tick 数。无返回值，按绝对周期调度，已错过截止时间时可能直接返回。本项目周期 5 tick。 |
| `xTaskGetTickCount()` | 无参数，返回调度器 tick 计数快照；不是 HAL 毫秒值的替代来源。 |
| `xTaskGetSchedulerState()` | 无参数，返回 NOT_STARTED/RUNNING/SUSPENDED 枚举。SysTick 在 NOT_STARTED 时仅更新 HAL，不调用内核 tick。 |
| `uxTaskGetStackHighWaterMark(task)` | `task` 为空表示当前任务；返回历史最小剩余栈字数，扫描栈有开销。本项目每轮记录到调试变量。 |
| `taskENTER_CRITICAL()` / `taskEXIT_CRITICAL()` | 成对使用，无参数，保护与 USB ISR 共享的索引、TX 提交和 PWM 寄存器操作。Cortex-M0 端口通过 PRIMASK 全局屏蔽中断；不要在区内阻塞、延时或解析整帧。 |
| `pdMS_TO_TICKS(ms)` | 把毫秒换算成 tick 的宏，不阻塞；低 tick 频率下可能截断为零，本项目 1 ms/tick。 |

应用实现的 `vApplicationGetIdleTaskMemory(tcb, stack, size)` 三个参数均为非空输出指针，
`size` 是字数；`vApplicationIdleHook()` 只执行 WFI；
`vApplicationStackOverflowHook(task, name)` 不解引用出错对象，直接全灭停机。
`configASSERT` 同样停机，不提供错误恢复。`FreeRTOSConfig.h` 中 HAL 的 `USE_RTOS=0`
并不表示禁用应用层 FreeRTOS，它只是不启用 HAL 自身的 RTOS 配置分支。

## USB Device / CDC

本项目只有一个 `USBD_HandleTypeDef`，其 `pData` 与 `PCD_HandleTypeDef` 相互关联；
`pClassData` 指向唯一静态 CDC 存储槽。访问 CDC 字段前必须确认已分配；
应用发送必须同时检查已配置状态。设备初始化从任务运行，之后枚举和传输多在 USB ISR。

| 接口 | 参数、返回值与所有权 |
|---|---|
| `USBD_Init(device, descriptors, id)` | `device` 为非空设备句柄；`descriptors` 为非空、长期有效的描述符回调表；`id` 为设备索引，本项目为 0。初始化句柄并调用 `USBD_LL_Init`，返回 USBD 状态。 |
| `USBD_RegisterClass(device, class)` | 两参数非空，保存类表地址，本项目为全局 `USBD_CDC`；类表必须持续有效。返回 USBD 状态。 |
| `USBD_CDC_RegisterInterface(device, interface)` | 保存非空的接口回调表地址，不复制函数实现；表需长期有效，返回 USBD 状态。 |
| `USBD_Start(device)` | 非空且已初始化的设备句柄；启动外设，返回 USBD 状态。本项目检查以上初始化调用是否均为 `USBD_OK`。 |
| `USBD_CDC_SetRxBuffer(device, buffer)` | `device->pClassData` 必须有效；`buffer` 是供 OUT 接收的可写区，本项目为静态 64 字节。仅保存地址，不复制或分配。该版实现直接解引用类存储。 |
| `USBD_CDC_ReceivePacket(device)` | 以已设置 RX 地址准备下一次接收；FS 按 64 字节包容量使用。返回 OK/FAIL。Receive 回调先复制到应用队列，再重新挂接接收区。 |
| `USBD_CDC_SetTxBuffer(device, data, size)` | `pClassData` 必须有效；`data` 是发送区地址，`size` 是字节数。仅保存地址与长度，不复制；类存储空时该版实现不提供安全保护。 |
| `USBD_CDC_TransmitPacket(device)` | 依据类存储和 TxState 返回 OK/BUSY/FAIL；接受后置 TxState=1，并借用 TX 存储直到完成/撤销。锁定版本忽略 `USBD_LL_Transmit` 的返回值，类层 OK 不能证明底层成功或主机收到。 |
| `USBD_GetString(text, descriptor, size)` | `text` 为 NUL 结尾的 ASCII；`descriptor` 为 UTF-16LE 输出区；`size` 为非空输出总字节数。本地 64 字节区允许最多 31 个 ASCII 字符；接口不接收容量参数，调用者必须保证空间。 |
| `USBD_CtlError(device, request)` | 两个非空借用指针，STALL EP0 拒绝本次请求。包装器必须在厂商按主机长度启动数据阶段前调用。无返回值。 |
| `USBD_CDC.Setup(device, request)` | `request` 含已解析的 bmRequest/bRequest/wValue/wIndex/wLength。保存原函数指针后仅包装一次；重复初始化会造成递归。类请求由白名单校验；合法/标准请求继续转发。返回原处理器状态或防护返回的 FAIL。 |
| `USBD_CDC.GetFSConfigDescriptor(size)` | `size` 非空，输出配置描述符字节数；返回类持有的描述符地址。产品在 USB 启动前把偏移 7 改为 0x80、偏移 8 改为 50，即总线供电、声明最大 100 mA。 |

`ProtocolSend(data, size, context)` 与 `UsbTransmit(data, size)` 的所有权不同：
前者必须在返回前复制，因为输入可能是栈数组；后者异步借用，必须保持数据直到完成。
当前 `Reply()` 忽略 `ProtocolSend` 返回值，不能靠 false 实现背压；应用通过单槽 TX、
暂停 RX 消费，确保每次回调都可接收响应。总线 reset/suspend 后旧响应作废，不继续重放发送槽。

`USBD_LL_SetupStage`、`DataOutStage`、`DataInStage`、`SOF`、`Reset`、`Suspend`、
`Resume`、`DevConnected`、`DevDisconnected`、`IsoIN/OUTIncomplete` 是从 HAL 回调转发到栈的事件入口。
第一个参数均为 `pcd->pData` 的有效设备句柄；有 `ep` 参数时它是无方向位的端点号；
数据阶段还传 HAL 维护的端点缓冲，Setup 阶段传 8 字节 Setup 包。
它们在 USB ISR 内运行，不转移缓冲所有权，也不在这里调用应用协议解析。
`USBD_LL_SetSpeed(device, USBD_SPEED_FULL)` 在 reset 时设置速度。

## HAL 时钟、GPIO 和 PWM

HAL 配置结构均由调用者提供非空指针，本项目在启动栈上清零后赋值，
HAL 读取配置，不保留这些临时结构地址。HAL 返回状态为 OK/ERROR/BUSY/TIMEOUT；
项目检查时钟/PWM 的关键返回值，失败转 `BoardFatal()`。

| 接口 | 参数含义及本地配置 |
|---|---|
| `HAL_Init()` | 无参数，初始化 HAL 基础设施和 SysTick；在调度前调用。 |
| `HAL_RCC_OscConfig(osc)` | `osc` 描述振荡器开关和 PLL；开启 HSI48，不使用 PLL。返回 HAL 状态。 |
| `HAL_RCC_ClockConfig(clock, latency)` | `clock` 选择 SYSCLK/总线分频；`latency` 为 Flash 等待周期枚举，本项目 `FLASH_LATENCY_1`，不是毫秒。返回 HAL 状态。 |
| `HAL_RCCEx_PeriphCLKConfig(peripheral)` | 选择外设时钟来源，USB 取 HSI48；返回 HAL 状态。 |
| `HAL_RCCEx_CRSConfig(crs)` | `crs` 指定 USB SOF 同步源、预分频、重装载、误差和校准值；本项目以 48 MHz/1 kHz 设置。无返回值。 |
| `HAL_GPIO_Init(GPIOA, gpio)` | 第一个参数是 GPIO 寄存器组基址；`gpio` 指定 PA0/1/2、AF2、推挽、无上下拉和低速。无返回值，不能误把 USB 重映射脚配置成 UART。 |
| `HAL_TIM_PWM_Init(pwm)` | `pwm` 为长期有效的 TIM2 句柄，Init 的 Prescaler=0、Period=4799；48 MHz 下 PWM 10 kHz。返回 HAL 状态。 |
| `HAL_TIM_PWM_ConfigChannel(pwm, channel, id)` | `channel` 为非空输出比较配置（PWM1、高有效、初始 Pulse=0）；`id` 为 `TIM_CHANNEL_1/2/3` 编码，不是普通数组下标。返回 HAL 状态。 |
| `HAL_TIM_PWM_Start(pwm, id)` | 启动指定通道，返回 HAL 状态。只在初始化调用；挂起仅停止 TIM2 CEN，恢复直接置 CEN，避免重复 Start 遇到 HAL_BUSY 状态。 |
| `HAL_GetTick()` / `HAL_IncTick()` | 前者返回 uint32_t 毫秒快照，后者在 SysTick ISR 加一。协议以无符号差值计时，约 49.7 天回绕；运行时间秒数也会随该毫秒差回绕。 |
| `HAL_Delay(ms)` | `ms` 为毫秒，忙等 HAL tick。任务等待使用 RTOS API；USB IRQ 优先级高于 SysTick，不能在 USB ISR 调用 HAL_Delay。 |
| `HAL_NVIC_SetPriority(irq, preempt, sub)` | `irq` 是中断号；本项目 USB_IRQn、优先级 2、子优先级 0；SysTick/PendSV 为 3，数字越小优先级越高。 |
| `HAL_NVIC_EnableIRQ/DisableIRQ(irq)` | 参数为中断号；分别开放/关闭该 IRQ，无返回值。 |

`__HAL_RCC_*_CLK_ENABLE/DISABLE()` 控制外设门控时钟，无参数；
`SET_BIT/CLEAR_BIT(register, mask)` 原地修改寄存器位，不自带并发保护。
`__DMB()` 保证 RX 数据先于写索引发布；`__WFI()` 在 Idle 等待中断；
`__disable_irq()` 只用于致命停机，不作为普通任务锁。

## HAL PCD 与端点参数

`PCD_HandleTypeDef *pcd` 必须非空并关联唯一 USB 实例。带端点地址 `ep` 的
HAL/LL 调用使用 bit7=IN 的编码，例如 0x80 为 EP0 IN、0x00 为 EP0 OUT；
HAL 回调里的 `ep` 则是端点号，不能混用。底层不承担应用参数合法性检查。

| 接口 | 参数、返回值和有效期 |
|---|---|
| `HAL_PCD_Init/DeInit/Start/Stop(pcd)` | 初始化、释放、启动、停止外设，返回 HAL 状态；Init/DeInit 会触发 MSP 回调。HAL 句柄必须长期有效。 |
| `HAL_PCD_IRQHandler(pcd)` | 从 USB_IRQHandler 调用，服务硬件标志并触发 HAL 回调；无返回值。 |
| `HAL_PCDEx_PMAConfig(pcd, ep, mode, offset)` | `ep` 含方向；`mode=PCD_SNG_BUF`；`offset` 是 PMA 字节偏移，不是 CPU 指针。本项目分配 0x40/0x80/0xc0/0x100/0x110，并预留 BTABLE。返回 HAL 状态。 |
| `HAL_PCD_EP_Open(pcd, ep, max_packet, type)` | `max_packet` 为最大包字节数，`type` 为端点类型；返回 HAL 状态。注意本地 USBD_LL_OpenEP 参数顺序是 type、size，转发时交换。 |
| `HAL_PCD_EP_Close/Flush/SetStall/ClrStall(pcd, ep)` | 操作指定方向的端点；返回 HAL 状态，适配层映射为 USBD_OK/FAIL。 |
| `HAL_PCD_SetAddress(pcd, address)` | `address` 是已验证的 7 位设备地址，返回 HAL 状态。 |
| `HAL_PCD_EP_Transmit(pcd, ep, data, size)` | `data` 为借用可读区，`size` 为字节数；零长包可用空数据指针。缓冲在传输完成/撤销前有效且不变。返回 HAL 状态。 |
| `HAL_PCD_EP_Receive(pcd, ep, data, size)` | `data` 为借用可写区；`size` 为期望字节数，实际存储需满足 HAL 按 max_packet 取整后的写入空间。CDC FS 固定提供 64 字节。返回 HAL 状态。 |
| `HAL_PCD_EP_GetRxCount(pcd, ep)` | 返回本次 OUT 传输累计收到的字节数，不消费数据。 |
| `HAL_PCD_EP_Abort(pcd, ep)` | 撤销指定端点传输，返回 HAL 状态；挂起路径另清 CTR_TX 硬件标志，再清软件 TxState，最后让任务回收旧 TX 槽。 |
| `PCD_CLEAR_TX_EP_CTR(instance, number)` | `instance` 为 USB 寄存器基址，`number` 为无方向位端点号；清 TX 完成标志，无返回值。 |

## 标准库与主机工具依赖

固件仅使用 `memcpy(dst, src, bytes)`、`memset(dst, value, bytes)`、
`memcmp(a, b, bytes)`，指针范围必须覆盖字节数；memcpy 不支持重叠。
这些调用同步完成，不保存指针；memcmp 只用是否等于零，不依赖具体非零值。
不链接 malloc/free/printf；主机测试可使用 stdio/assert。

`hil.py` 的 `serial.Serial(port, 115200, timeout=0.1, write_timeout=1)`
中 timeout 单位为秒；波特率只是 CDC 配置，不是 MCU 物理 UART。
`write(bytes)` 同步向串口驱动提交，`read_until(b"\0", 80)` 读到分隔符、
80 字节或超时即返回，返回值不保证是一帧；工具另做结构/CRC/seq 校验。
`reset_input_buffer()` 清历史输入，`close()` 释放端口。
`binascii.crc_hqx(data, 0xffff)` 提供独立 CRC；`struct` 格式 `<` 明确小端。
Python 接口自身参数和异常见对应函数 docstring。

## 注释约定来源

函数注释遵循 [Google C++ Style Guide 的 Function Comments](https://google.github.io/styleguide/cppguide.html#Function_Comments)
中适用于 C 的要求：声明说明用途、输入输出、可空条件、状态改变与所有权；
定义解释算法、同步和硬件限制。中文、版本号、日期和模块用法是本项目的附加要求，
不是 Google 强制的格式。详细规则见 `coding-style.md`。
