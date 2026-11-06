/* 模块：ARM GCC 链接布局；版本：1.0.0；日期：2026-10-28。
 * 用法：由 build.ps1 的 -T 参数载入，启动地址为 0x08000000。
 * .data 的 Flash 装载地址由 _sidata 交给启动文件，.bss 在复位时清零。
 * _end 到 RAM 顶端必须至少留 768 字节 MSP；任务栈已计入静态 .bss。
 */
/* 32 KB Flash / 6 KB RAM，MSP 预留 768 字节；任务栈包含在 .bss。 */
ENTRY(Reset_Handler)
MEMORY {
  FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 32K
  RAM (xrw) : ORIGIN = 0x20000000, LENGTH = 6K
}
_estack = ORIGIN(RAM) + LENGTH(RAM);
_Min_Stack_Size = 768;
SECTIONS {
  .isr_vector : { . = ALIGN(4); KEEP(*(.isr_vector)) . = ALIGN(4); } >FLASH
  .text : { . = ALIGN(4); *(.text*) *(.rodata*) KEEP(*(.init)) KEEP(*(.fini))
    . = ALIGN(4); _etext = .; } >FLASH
  .ARM.extab : { *(.ARM.extab*) } >FLASH
  .ARM.exidx : { __exidx_start = .; *(.ARM.exidx*) __exidx_end = .; } >FLASH
  .preinit_array : { PROVIDE_HIDDEN(__preinit_array_start = .);
    KEEP(*(.preinit_array*)) PROVIDE_HIDDEN(__preinit_array_end = .); } >FLASH
  .init_array : { PROVIDE_HIDDEN(__init_array_start = .);
    KEEP(*(SORT(.init_array.*))) KEEP(*(.init_array*))
    PROVIDE_HIDDEN(__init_array_end = .); } >FLASH
  .fini_array : { PROVIDE_HIDDEN(__fini_array_start = .);
    KEEP(*(SORT(.fini_array.*))) KEEP(*(.fini_array*))
    PROVIDE_HIDDEN(__fini_array_end = .); } >FLASH
  _sidata = LOADADDR(.data);
  .data : { . = ALIGN(4); _sdata = .; *(.data*) . = ALIGN(4); _edata = .; } >RAM AT>FLASH
  .bss (NOLOAD) : { . = ALIGN(4); _sbss = .; __bss_start__ = .;
    *(.bss*) *(COMMON) . = ALIGN(4); _ebss = .; __bss_end__ = .; } >RAM
  . = ALIGN(8); _end = .; end = .;
  ASSERT(_estack - _end >= _Min_Stack_Size, "RAM overflow: MSP < 768 bytes")
  /DISCARD/ : { *(.note.GNU-stack) }
}
