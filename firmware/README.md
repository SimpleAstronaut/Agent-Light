# Agent Light Rev A FreeRTOS 固件

实现对象：STM32F042F6P6，32 KB Flash / 6 KB SRAM，现有 `hardware/eda/` Rev A PCB。应用源代码及注释采用中文，见 [代码约定](docs/coding-style.md)。

项目总览与完整使用手册见 [根目录 README](../README.md)。本文件保留固件构建基线；2026-11-06 已补充实板 HIL 和真实 DSH 控灯联调记录。

注释基线：版本 1.0.0，日期 2026-10-28。关键函数说明状态机、并发和缓冲生命周期；接口说明参数、返回值与调用限制。阅读入口、调用链和 FreeRTOS/HAL/USB 依赖参数见 [模块与依赖接口说明](docs/dependency-interfaces.md)。

## 已实现

- FreeRTOS 原生 API，应用任务 + Idle任务，TCB/栈全静态分配，无 heap_x、malloc 或Flash写配置。
- USB CDC ACM、COBS/CRC16、SET_STATE/HEARTBEAT/GET_STATUS、ACK/NACK、最近事务去重和 revision 模比较。
- 上电红黄绿自检；五态灯效；亮度20–100%；5秒链路看门狗；reset/resume等待重新同步；suspend立即全灭并停止PWM。
- PA0/1/2：TIM2 AF2三路10kHz PWM；PA9/10物理引脚重映射为USB DM/DP；48MHz HSI48+USB SOF CRS。
- EP0控制请求在数据阶段之前校验方向、长度和已配置状态，防止所用ST CDC版本的控制缓冲越界及空指针访问。

业务状态、完成保持、手动测试覆盖由PC负责；固件不会理解Agent或自行退出COMPLETED。USB合约见 [usb-protocol-v1.md](../contracts/usb-protocol-v1.md)。

## 构建与测试

本机已找到ARM GCC 10.3.1、MinGW GCC 14.2.0、CubeMX6.12.1、MDK5.29。首次取依赖：

```powershell
.\firmware\fetch-dependencies.ps1
.\firmware\build.ps1 Host
.\firmware\build.ps1 Debug
.\firmware\build.ps1 Release
py -3.14 .\firmware\tools\protocol_reference.py --check
py -3.14 .\firmware\tools\verify_artifacts.py
```

ARM GCC、objcopy、size和主机gcc需在PATH中。Python只用于参考向量/工程生成/实板脚本，不参与目标固件构建。当前机器使用Python3.14；PC服务已在 `pc/` 实现，详见其 README。

输出：`firmware/build/Debug/`、`firmware/build/Release/` 下的 `agent-light.elf/.hex/.bin/.map`、每个源文件的 `.su` 和 SHA256SUMS。Flash起始 `0x08000000`，不带bootloader；SWD烧录HEX或BIN，BIN需明确起始地址。

主机测试包含协议/灯效/超时/回绕、100000随机字节、17组独立Python黄金向量、所有65536种CDC控制长度，以及执行真实USB Setup包装入口的配置状态/空存储/超长拒绝测试。主机测试不能替代USB电气与板上时序验证。

## CubeMX 与 Keil

- [cubemx/agent_light_peripherals.ioc](cubemx/agent_light_peripherals.ioc) 是外设参考配置，已经过本机CubeMX6.12.1命令行加载和保存往返核验（精确料号、USB重映射、CRS、三路PWM）。它不生成本项目的FreeRTOS应用。
- [MDK-ARM/agent-light.uvprojx](MDK-ARM/agent-light.uvprojx) 使用ARM Compiler5.06u6、RVDS Cortex-M0端口，已用本机µVision完成Debug/Release全量构建，均0错误/0警告；输出位于 `build/MDK-Debug/`、`build/MDK-Release/`。ST-LINK与实板下载尚未验证。
- 不要在 `firmware/` 根目录直接点CubeMX Generate Code覆盖现有Core/USB集成。需要重生成时输出到单独目录，按 [配置检查表](docs/cubemx-and-bringup.md) 迁移外设变化，保留原生FreeRTOS静态分配及EP0防护。
- MDK工程可用 `py -3.14 firmware/tools/generate_mdk.py` 更新；已有工程保留用户设备包和调试设置。当前工程使用用户选择的STM32F0xx_DFP3.1.1。

## 烧录与验收

1. 先按硬件方案检查电源和焊接。SWD：TP1=3V3参考、TP2=SWDIO、TP3=SWCLK、TP4=NRST、TP5=GND，BOOT0保持下拉。默认USB供电，编程器只读取3V3参考，不并联供电。
2. 用ST-LINK通过SWD烧录Release HEX；不修改option bytes或读保护。复位观察三色各100ms，随后黄色1Hz。
3. Windows设备管理器确认CDC端口，运行：

```powershell
py -3.14 firmware/tools/hil.py
py -3.14 firmware/tools/hil.py --port COM5 --report firmware/build/hil-report.json
py -3.14 firmware/tools/hil.py --port COM5 --soak-hours 24 --report firmware/build/soak-24h.json
```

`COM5`替换为真实设备。脚本会测试灯态并最终发送IDLE；可见亮度/频率、USB挂起电流、热插拔、主机睡眠恢复和真实24小时长稳需实物确认。只列端口时不会打开设备。

2026-11-06 的 `build/hil-report-2026-11-06.json` 记录 COM6 实板 HIL PASS，覆盖五态、亮度边界、revision 幂等、链路超时和768次事务/seq回绕；后续真实DSH对话已确认运行黄灯、完成绿灯。COM口会随环境变化，早期“未连接目标板”日志仅代表当时快照。开发描述符使用ST示例0483:5740，发布前换成有权使用的VID/PID。固件暂不进入Stop或切换低频时钟；USB挂起电流合规尚未验证。

详细结果、版本、内存预算和未完成门禁见 [验证记录](docs/verification.md)。
