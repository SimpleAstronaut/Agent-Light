# CubeMX 配置与实板检查

## 参考工程

打开 `firmware/cubemx/agent_light_peripherals.ioc`。器件STM32F042F6Px，CPN=STM32F042F6P6，TSSOP20，CubeMX6.12.1。依赖固定STM32CubeF0 v1.11.5；不是本机已有的F1包。自定义库路径可指向 `firmware/vendor/STM32CubeF0`。

| 配置 | 数值 |
|---|---|
| SYS Debug | Serial Wire，保留PA13/14 |
| SYS Pin remap | Pins PA11/12 instead of PA9/10 |
| USB | Device FS，PA11=DM/物理17脚，PA12=DP/物理18脚 |
| USB_DEVICE | CDC FS，bus-powered，不启用BCD/LPM/remote wakeup |
| SYSCLK/HCLK/PCLK1 | HSI48，48MHz，不分频 |
| CRS | USB SOF，1kHz，同步不分频，reload47999，默认误差/校准 |
| TIM2_CH1/2/3 | PA0/1/2 AF2，PWM1，高有效，PSC0，ARR4799，初始CCR0 |
| USB IRQ | 优先级2，不调用RTOS API |
| SysTick/PendSV | 优先级3，1ms，Cortex-M0四级优先级 |

产品工程手工维护FreeRTOS原生集成（`app_main.c`/`FreeRTOSConfig.h`），不依赖Cube生成的CMSIS-RTOS defaultTask。应用栈384 words，Idle栈96 words，禁用动态分配、软件定时器和newlib重入。SysTick同时递增HAL tick，仅在调度器启动后调用端口tick。不要再生成同名SysTick/SVC/PendSV实现。

## 首次Keil GUI确认

打开 `firmware/MDK-ARM/agent-light.uvprojx`，确认：

- ARM Compiler5.06u6和C99；MicroLIB；非ARMCLANG端口。若切换Compiler6，必须同步改用对应端口并重新验证，不只切编译器下拉框。
- 选择STM32F042F6Px，F0 DFP支持精确器件；IROM32KB、IRAM6KB；Flash算法 `STM32F0xx_32.FLM`。
- 启动文件MSP0x300，无C堆，散装文件 `agent-light.sct`。
- Debug/Release都构建，检查map中的RAM和所有静态任务栈；不接受超6KB或栈空间被压缩。
- ST-LINK/SWD，必要时Connect under reset，首次建议SWD≤1MHz；不要改RDP/BOOT option bytes。

后续用户已选择F0 DFP3.1.1；修复工程选项后，本机µVision Debug/Release全量构建均0错误/0警告。算法选择与实际SWD下载仍需在板上验证。

## 实板验收表（尚未执行）

- [ ] 上电电压、静态电流、三色自检、LED极性与无异常发热。
- [ ] CDC枚举，完整96位UID序列号；GET_STATUS字段正确。
- [ ] 五态、20/35/100%亮度，载波10kHz，ERROR2Hz和断链1Hz/50%示波器测量。
- [ ] 5秒断链；心跳不恢复旧态；同revision SET恢复；COMPLETED由PC决定保持时间。
- [ ] 复位、USB reset、suspend/resume、未完成ACK时睡眠恢复、拔插和Hub。
- [ ] EP0超长和枚举前类请求被stall，设备不中断；只能在测试主机上做受控USB测试。
- [ ] 连续768事务、revision回绕、ACK丢失/重试、坏CRC、随机输入后恢复。
- [ ] SWD查看 `g_app_stack_free_words` 和 `g_rx_overflows`，记录任务及MSP实际峰值；不要仅凭链接成功通过栈验收。
- [ ] 24小时真实CDC长稳和USB挂起电流；量产前另做72小时及USB/ESD合规门禁。

此固件不实现USB DFU；恢复方式为SWD重新烧录。
