# C 代码与中文注释约定

版本：1.0.0（固件基线）；日期：2026-10-28。

Google 公开的是 [C++ Style Guide](https://google.github.io/styleguide/cppguide)，没有独立公开的官方 C 语言指南。本项目对 C11/C99 采用其中适用的规则；不会把 C++ 专属规则机械套到 C 上。

- 文件 snake_case，函数和 typedef 类型 PascalCase，局部变量/结构成员 snake_case，枚举常量 kName，宏 UPPER_SNAKE_CASE。
- 两空格缩进，不用 Tab，目标80列，头文件使用完整项目路径宏防护。
- 产品源文件使用 UTF-8 中文注释。公开 API 在头文件说明用途、参数边界、返回值、调用线程/ISR 限制和所有权；实现注释解释原因和硬件限制。
- `//` 行注释为主，避免把每行代码复述一遍。厂商 HAL、CMSIS、USB、FreeRTOS 源码保留原注释和许可证。
- 不在运行时分配堆内存，不用 printf/sprintf 或文件系统，不在 ISR 中解析协议或执行延时。
- 保留厂商接口原命名；本地包装和回调内部按本约定。
- ARM GCC 应用代码开启 `-Wall -Wextra -Werror`；厂商文件仅关闭已确认的 unused-parameter 告警，不修改第三方源码来压制警告。

`FreeRTOSConfig.h` 使用原生 API；应用任务独占协议和显示状态，ISR 只写有界队列及总线事件。临界区仅保护队列索引、USB提交和寄存器更新，不包含协议解析。

## 文件、模块和函数注释

遵循 [Google 的 Function Comments](https://google.github.io/styleguide/cppguide.html#Function_Comments)：声明侧说明怎么正确使用接口，定义侧说明复杂实现的原因；内部 static 函数同样需要说明。不要把 API 契约机械复制到实现，也不要逐行复述代码。

- 项目维护的源码和配置头在文件开头说明模块功能、版本、日期和简要用法，保留原版权信息。版本沿用当前固件基线 1.0.0；纯注释更新不改变 USB 对外报告的 0x0100。
- 每个公开接口分别说明参数含义、单位、范围、指针是否可空、输出覆盖方式、返回值、错误条件、调用上下文和缓冲所有权。模块级共同约束可以引用，不要求为 void 生造返回值。
- 关键函数额外说明状态转换、去重/回绕/超时、并发同步与异步缓冲有效期；简单内部函数用短注释解释功能和非显然的参数条件。
- FreeRTOS/HAL/USB 的本地回调或适配实现说明依赖约定；厂商源码不批量改写。集中说明见 [依赖接口文档](dependency-interfaces.md)。
- Python 辅助工具使用 Google 风格的 Args/Returns/Raises docstring；PowerShell 使用原生帮助注释。仅列与实际行为有关的异常和副作用。

示例：

```c
// 将 data 的 size 字节异步提交给设备，调用者保留缓冲所有权。
// data 非 NULL 且至少有 size 字节；完成或明确撤销前保持有效且不变。
// 仅应用任务在屏蔽 USB IRQ 时调用；返回 true 表示接受，非主机已收到。
bool UsbTransmit(uint8_t *data, uint16_t size);
```
