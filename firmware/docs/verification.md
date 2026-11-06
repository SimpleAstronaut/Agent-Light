# WP30 固件验证记录

日期2026-10-28，硬件基线Rev A，固件1.0.0，USB协议1。此记录区分交叉构建、主机行为测试和实板验收。

后续状态（2026-11-06）：`../build/hil-report-2026-11-06.json` 已记录 COM6 实板 HIL PASS，真实 DSH 对话也已完成运行黄灯/完成绿灯确认。以下表格为2026-10-28的历史构建记录，其中 NOT RUN 不代表当前仍未连接实板；最新总体状态见 [项目 README](../../README.md)。光学、电流、挂起和长稳等仍需独立验证。

## 实际执行结果

| 项目 | 结果 |
|---|---|
| ARM GCC Debug | PASS，0 error / 0 warning；Flash24324B |
| ARM GCC Release | PASS，0 error / 0 warning；Flash20044B |
| 主机C核心测试 | PASS，协议、显示、随机流、时间/seq/revision回绕 |
| 真实CDC Setup入口主机测试 | PASS，枚举前/空类存储拒绝、全部16位控制长度边界 |
| 独立Python黄金向量 | PASS，17组输入/期望响应与C逐字节一致 |
| CubeMX6.12.1 CLI往返 | PASS，F042F6Px/TSSOP20、6个IP、11个引脚/虚拟信号，USB_DM/DP、PINREMAP、SOF CRS、TIM2三通道保留 |
| Keil ARMCC Debug/Release | PASS，用户首次GUI报错后，修复工程并用本机µVision5.29 CLI全量重建；均0 error / 0 warning |
| SWD烧录、真实USB、示波器、长稳 | NOT RUN，没有目标板连接 |

`build/final-debug.log`、`build/final-release.log`、`build/cubemx-validate.log`为构建/配置日志；Debug/Release目录保留map、ELF、HEX、BIN和源文件栈用量。最终产物哈希见 `build/*/SHA256SUMS.txt`。

Keil日志为 `build/keil-debug.log`、`build/keil-release.log`，输出分别在 `build/MDK-Debug/` 和 `build/MDK-Release/`。修复前实测复现29 errors / 32 warnings，日志 `build/keil-before.log`。

根因：工程生成器省略了 `VariousControls` 中的空字段，µVision5把IncludePath读入Undefine、把汇编Define读入MiscControls。修复为完整有序字段，同时关闭不适用于Cortex-M0的SplitLS选项；保留用户已经配置的DFP3.1.1及调试设置。

ARMCC程序大小：Debug Code27920 / RO284 / RW456 / ZI5640；Release Code18648 / RO276 / RW456 / ZI5640。RAM总6096B（已包含768B主栈），IRAM余48B。此预算不能与GCC不计主栈的RAM栏直接比较；仍需实板栈水位验证。

应用代码 `-Wall -Wextra -Werror`。锁定的ST文件包含4处未使用回调参数（USB ctlreq/CDC、HAL_PWR），仅第三方文件关闭 `-Wunused-parameter`，不覆盖其他告警。没有修改第三方仓库内容。

## Flash/RAM/栈预算

| 配置 | Flash使用（含.data初值） | 静态RAM（链接器报告） | 对齐后_end | MSP及剩余区域 |
|---|---:|---:|---:|---:|
| Debug | 24324 / 32768 B | 5356 B | 0x200014f0 | 784 B |
| Release | 20044 / 32768 B | 5344 B | 0x200014e0 | 800 B |

静态RAM已包含应用任务栈1536B、Idle栈384B、两个TCB、RX环形256B、TX40B、单事务缓存、USB设备/PCD句柄及静态CDC存储。硬件USB PMA不占通用SRAM；PMA BTABLE/EP0/CDC区域不重叠。

链接脚本硬性要求MSP至少768B；没有C堆、FreeRTOS堆或动态队列。最终ELF检查无malloc/free/pvPortMalloc/vPortFree/_sbrk/printf符号。任务栈运行水位由 `g_app_stack_free_words` 提供，应用开启栈溢出检查；**链接预算不是实测栈峰值，仍必须在实板USB压力下验证MSP/任务栈**。

## 独立审查及修复

1. 修正USB reset/resume重复调用 `HAL_TIM_PWM_Start` 时通道BUSY导致错误的问题：首次仅初始化启动，恢复只设置CEN。
2. 在ST CDC Setup转发前验证请求类型、方向、接口、精确长度和设备配置/类存储就绪；防止主机超长EP0读写，以及枚举前合法类请求解引用NULL。新增纯逻辑边界测试和真实Setup入口回归。
3. suspend时先abort旧CDC IN、清硬件CTR_TX，再释放TxState；应用通过总线epoch丢弃待发响应和半帧，resume要求重新SET。
4. 修正ST示例配置描述符写死的self-powered位，实际FS描述符改为bus-powered、最大100mA；真实描述符修改路径加入主机回归。

`build/artifact-verification.json`记录最终ELF/HEX/BIN的SHA-256；自动检查HEX校验和、HEX与BIN相同、Flash/RAM边界、Reset/SVC/PendSV/SysTick/USB向量和无动态分配符号，结果PASS。

协议/显示所有状态由一个任务独占，USB ISR只处理栈与字节队列。每轮最多64字节，5ms周期；输入洪泛时有界丢弃，不阻塞灯效和看门狗。实板吞吐与所有中断交错组合尚未验证。

## G0 料号与资料核验

- [ST数据手册DocID025832 Rev5](https://www.st.com/resource/en/datasheet/stm32f042f6.pdf)：p1说明48MHz/32KB/6KB及晶振省略USB能力；p32–36为封装和引脚表（物理17/18的PA11/12重映射）；p37表14确认PA0/1/2 AF2=TIM2_CH1/2/3；PA13/14为SWD。
- 重映射位 `SYSCFG_CFGR1_PA11_PA12_RMP` 和48MHz/CRS配置已与锁定的官方CMSIS/HAL头文件核对。SYSCLK/PCLK1=48MHz，USB直接选HSI48，CRS使用SOF1000Hz，reload47999。USB上拉由HAL PCD内置外设连接机制控制，硬件无额外1.5k电阻。
- [ES0243 Rev4，2020-12](https://www.st.com/resource/en/errata_sheet/es0243-stm32f042x4x6-device-errata-stmicroelectronics.pdf)，p19–20：APB至少10MHz，本工程48MHz；ESOF远程恢复限制因未实现remote wakeup不进入该路径；不读取PMA里的CRC校验字节；BCD/DCD未启用。
- MCU供电/去耦、NRST、BOOT0和SWD依据硬件导出网表/README核对；嘉立创MCP确认当前打开 `Agent-Light-v1`/Board1/PCB1，与目录基线名称一致，未修改PCB。
- 首轮仅找到DFP2.0.0索引；用户随后将工程配置为STM32F0xx_DFP3.1.1，修复后已实际构建通过。Flash算法仍未在目标板上验证。
- RM0091完整官方PDF本轮网页提取因文件大小限制未读完；未虚构该手册版本/页码。首次GUI冻结/硬件评审前仍应对完整手册、电气角落、硅版本做复核。

## 当前边界

这次交付为可交叉构建、经过主机回归的固件实现及实板验收工具，不是WP30所有实物门禁通过。尚无板上运行、温度、ESD、USB挂起电流、频率、热插拔、睡眠恢复和24小时测试证据。保留48MHz时钟，不宣称低功耗或USB认证合规。USB描述符标识仅用于开发，产品发布前需授权VID/PID。

没有实现PC服务或Agent适配器；本次仅按用户要求完成嵌入式开发部分。
