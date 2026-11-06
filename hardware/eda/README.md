# Agent Light Rev A 硬件原理图

按 `outputs/agent-indicator-design.md` 和 `outputs/agent-indicator-execution-plan.md` 的 WP31 绘制，日期 2026-10-27，编辑器为嘉立创 EDA 专业版 4.1.78。

项目总览与使用手册见 [根目录 README](../../README.md)。本文件中的DRC和制造边界是设计交付记录；2026-11-06 用户已焊接实板，并完成USB HIL和真实DSH控灯的基础联调，但这不代表下述制造冻结、阻抗、ESD等项目全部完成。

## 打开工程

`Agent-Light-v1.epro2` 是完整、可编辑的嘉立创 EDA 专业版工程包，包含原理图、符号、器件和封装。使用 EDA 的“导入 → 嘉立创EDA专业版”导入该文件，再按需保存成本地工程。不要将 `.epro2` 直接改名为 `.eprj`。当前编辑器中也保留了绘制完成的工程。

原理图原始交付保留在 `Agent-Light-v1.epro2`。后续 PCB 布局布线初版见 `Agent-Light-v1-layout.epro2`，详情见 [PCB-Layout-RevA.md](PCB-Layout-RevA.md)。PCB 为 12×40 mm 双层板，最终 PCB DRC 返回空数组；附制造初稿，但 USB 90 Ω 阻抗和实际板厂层叠尚未确认，不能视为已完成制造冻结。

## 文件

- `Agent-Light-v1.epro2`：完整工程包，优先使用。
- `Agent-Light-v1.net`：由 EDA 导出的 Protel2 网表。
- `BOM-RevA.csv`：35 个位号，25 个装配器件、2 个 DNP、8 个裸测试焊盘；含完整 MPN、封装和数据手册链接。采购数量为 0，未查询实时库存，也未下单。
- `previews/`、`schematic-previews.zip`：五页 2400 像素宽的原理图预览。
- `sources/`：五页原理图原生文本源码备份；其依赖库包含于完整工程包。
- `verification.json`：一次集中检查的结果。

## 分页

1. 00 封面：基线、版本、装配规则和范围。
2. 01 USB与电源：TYPE-C-31-M-12、CC1/CC2 各 5.1kΩ、ST USBLC6-2SC6、22Ω 串阻、0.5A PTC、ME6211C33M5G-N 及屏蔽接地选项。
3. 02 MCU：STM32F042F6P6 TSSOP-20、两路 100nF 去耦和 4.7µF 储能、USB 重映射、TIM2 PWM。
4. 03 LED：KT-0805R/Y/G，分别串 680Ω，GPIO 高电平点亮；红上、黄中、绿下。
5. 04 调试与产测：SWD、NRST 10kΩ/100nF、BOOT0 10kΩ 下拉、1kΩ 安全拉高支路和八个裸测试点。

## 关键实施事项

- **USB_DM 接物理 17 脚 PA9[PA11]，USB_DP 接物理 18 脚 PA10[PA12]。** 固件须启用 SYSCFG 时钟并设置 `SYSCFG_CFGR1.PA11_PA12_RMP`，使用 HSI48 + CRS。芯片集成 USB 上拉，不另加 1.5kΩ。
- PA0/PA1/PA2 使用 AF2、TIM2_CH1/CH2/CH3，分别驱动红/黄/绿；PWM 建议大于 1kHz。
- 默认装 R5=0Ω，**R6=1MΩ、C3=1nF 不装**，并已从默认装配 BOM 排除。尝试屏蔽 RC 接地时，拆 R5，同时装 R6、C3。
- TP1=3V3参考，TP2=SWDIO，TP3=SWCLK，TP4=NRST，TP5=GND，TP6=VBUS，TP7=BOOT0，TP8=BOOT_HI。测试点采用单引脚排针的镀通孔焊盘，**不装排针**；PCB 阶段可按工装改成裸圆焊盘。
- SWD 的 3V3 为参考电压，默认由 USB 供电，勿将编程器电源与 USB/LDO 输出并联。
- 进入系统引导模式时将 TP7 与 TP8 短接后复位；完成后移除短接。R12=1kΩ 与 R11=10kΩ 分压，BOOT0 约为 3.0V；若 PB8 输出低电平，拉高支路电流约 3.3mA。
- 低电流 LED 亮度尚待实料校准；680Ω 在 Vf=0 的极限计算为每路 4.85mA，三路共 14.6mA。此值不代表整机实测电流。

## 已完成检查与后续边界

EDA 原理图 DRC 返回空数组；导出的网表中 24 个网络、90 个已连接引脚全部与预期连接表一致，11 个引脚明确不连接，位号无重复。检查覆盖 USB 正负线、独立 CC 下拉、全部 MCU 电源、LED 极性、复位与 SWD/BOOT。

这不替代执行计划中的实物冻结门禁：精确 MCU 的 USB CDC/热插拔/睡眠恢复、LED 实料低亮度试验、连接器实物匹配、第二人引脚/封装复核、PCB 阻抗与布局、ESD、打样上电和联调仍待后续执行。PCB 目标约 40×12mm、双层，实际边框和阻抗须结合结构及板厂层叠确定。

## 主要资料

- ST STM32F042x4/x6 数据手册：https://www.st.com/resource/en/datasheet/stm32f042f6.pdf
- ST RM0091 参考手册：https://www.st.com/resource/en/reference_manual/rm0091-stm32f0x1stm32f0x2stm32f0x8-advanced-armbased-32bit-mcus-stmicroelectronics.pdf
- ST USBLC6-2 数据手册：https://www.st.com/resource/en/datasheet/usblc6-2.pdf
- 其余器件资料链接见 BOM；替代器件未批准，不能只凭同名封装直接替换。
