# 注释补充核验记录

版本：1.0.0；日期：2026-10-28。

本次更新 33 个已有源码/文档文件，新增模块依赖接口说明与本记录。
应用、Core、USB 适配层和主机测试中的 142 处 C 函数声明/定义均有紧邻注释；
该数字包含同一公开函数在头文件与实现中的两个位置，不等于独立函数数。
Python/PowerShell 辅助工具补充函数说明、参数、必要返回值/异常及文件用法。
厂商源码及派生的 ST 启动汇编保留原有说明和许可证。

## 只改注释的核对

以本次开始时保存的本地文件备份为基线：

- C 源文件、头文件和 GCC 链接脚本去除注释后，词法 token 序列一致。
- ARMCC scatter 文件去除注释后，有效配置一致。
- Python 去除模块/类/函数 docstring 后，AST 一致。
- PowerShell 去除帮助注释和空行后，原有效代码行一致；两个脚本均通过原生解析器检查。
- 更新的项目代码/配置文件头均包含版本 1.0.0、日期 2026-10-28 和模块用法。

## 构建与测试

| 检查 | 本次结果 |
|---|---|
| `build.ps1 Host` | 两个测试程序通过，涵盖协议/灯态/恢复/回绕和真实 Setup 包装入口 |
| `protocol_reference.py --check` | 17 组独立黄金向量通过 |
| `build.ps1 Debug` | 构建通过，BIN 24324 字节 |
| `build.ps1 Release` | 构建通过，BIN 20044 字节 |
| `verify_artifacts.py` | 向量、HEX 校验和、HEX/BIN 一致、内存边界和无动态分配符号检查通过 |
| 四个 Python 工具 `py_compile` | 语法检查通过 |

Debug/Release 的 BIN 均与注释修改前逐字节一致，SHA256 分别为：

```text
Debug   112dd1f80f3fe2ed3997a51028b932e3efe12445fd1829e17295f3e3a7d90d7a
Release d55bf4de4c89f5a1c5d51fc114c9ae04e9ecbf3edaef9e43201ce6ecc335828c
```

ELF 包含源码行号等调试信息，因此纯注释修改后其哈希可变化。
本次没有烧录或运行 HIL，未重新执行 Keil 构建；主机与 GCC 结果不代表实板验收。

阅读入口见 [模块与依赖接口说明](dependency-interfaces.md)，注释规范见
[coding-style.md](coding-style.md)。
