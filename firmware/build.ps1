<#
.SYNOPSIS
构建 Agent Light 主机测试或 ARM GCC 固件。
.DESCRIPTION
版本：1.0.0；日期：2026-10-28。先获取锁定依赖，工具链需在 PATH。
Host 运行协议与真实 Setup 回归；Debug/Release 生成 ELF/HEX/BIN/MAP。
.PARAMETER Configuration
Debug（默认）、Release 或 Host；输出位于 firmware/build/<配置>。
.EXAMPLE
.\firmware\build.ps1 Host
.EXAMPLE
.\firmware\build.ps1 Release
#>
param([ValidateSet('Debug','Release','Host')][string]$Configuration = 'Debug')
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
<#
.SYNOPSIS
执行一个工具，非零退出码转为终止错误。
.PARAMETER Program
可执行程序名或路径，由当前环境解析；不得为空。
.PARAMETER Arguments
逐项参数字符串数组，可为空数组；不拼接为 shell 命令。
.OUTPUTS
透传子进程的标准输出；失败抛异常，外层 finally 恢复工作目录。
#>
function Run-Checked([string]$Program, [string[]]$Arguments) {
  & $Program @Arguments
  if ($LASTEXITCODE -ne 0) { throw "$Program failed ($LASTEXITCODE)" }
}
$build = Join-Path $PSScriptRoot "build/$Configuration"
New-Item -ItemType Directory -Force $build | Out-Null
$app = @('app/crc16.c','app/cobs.c','app/display.c','app/protocol.c',
  'app/usb_cdc_guard.c')
if ($Configuration -eq 'Host') {
  Run-Checked 'gcc' (@('-std=c11','-Wall','-Wextra','-Werror','-g','-Iapp',
    'tests/host/test_main.c') + $app + @('-o',"$build/test_main.exe"))
  Run-Checked "$build/test_main.exe" @()
  $vendor = 'vendor/STM32CubeF0'
  $hostIncludes = @('app','Core/Inc','USB_Device',
    "$vendor/Drivers/STM32F0xx_HAL_Driver/Inc", "$vendor/Drivers/CMSIS/Include",
    "$vendor/Drivers/CMSIS/Device/ST/STM32F0xx/Include",
    "$vendor/Middlewares/ST/STM32_USB_Device_Library/Core/Inc",
    "$vendor/Middlewares/ST/STM32_USB_Device_Library/Class/CDC/Inc")
  $hostFlags = @('-std=c11','-Wall','-Wextra','-Werror','-Wno-pointer-to-int-cast',
    '-DSTM32F042x6','-DUSE_HAL_DRIVER')
  foreach ($include in $hostIncludes) { $hostFlags += "-I$include" }
  Run-Checked 'gcc' ($hostFlags + @('tests/host/test_usb_setup.c',
    'USB_Device/usb_device.c','app/usb_cdc_guard.c','-o',"$build/test_usb_setup.exe"))
  Run-Checked "$build/test_usb_setup.exe" @()
  exit 0
}
$vendor = 'vendor/STM32CubeF0'
$hal = "$vendor/Drivers/STM32F0xx_HAL_Driver"
$cmsis = "$vendor/Drivers/CMSIS"
$usb = "$vendor/Middlewares/ST/STM32_USB_Device_Library"
$rtos = "$vendor/Middlewares/Third_Party/FreeRTOS/Source"
$includes = @('app','Core/Inc','USB_Device',"$hal/Inc","$cmsis/Include",
  "$cmsis/Device/ST/STM32F0xx/Include","$usb/Core/Inc","$usb/Class/CDC/Inc",
  "$rtos/include","$rtos/portable/GCC/ARM_CM0")
$sources = $app + @('app/board.c','app/app_main.c','Core/Src/main.c',
  'USB_Device/usb_device.c','USB_Device/usbd_conf.c',
  "$cmsis/Device/ST/STM32F0xx/Source/Templates/system_stm32f0xx.c",
  "$cmsis/Device/ST/STM32F0xx/Source/Templates/gcc/startup_stm32f042x6.s",
  "$rtos/tasks.c","$rtos/list.c","$rtos/portable/GCC/ARM_CM0/port.c",
  "$usb/Core/Src/usbd_core.c","$usb/Core/Src/usbd_ctlreq.c",
  "$usb/Core/Src/usbd_ioreq.c","$usb/Class/CDC/Src/usbd_cdc.c")
foreach ($module in @('hal','hal_cortex','hal_gpio','hal_dma','hal_rcc','hal_rcc_ex',
  'hal_flash','hal_flash_ex','hal_pwr','hal_pcd','hal_pcd_ex','ll_usb',
  'hal_tim','hal_tim_ex')) {
  $sources += "$hal/Src/stm32f0xx_$module.c"
}
$common = @('-mcpu=cortex-m0','-mthumb','-mfloat-abi=soft','-std=c11',
  '-g3','-ffunction-sections','-fdata-sections','-fno-common',
  '-fstack-usage','-Wall','-Wextra','-DSTM32F042x6','-DUSE_HAL_DRIVER')
if ($Configuration -eq 'Debug') { $common += '-Og' }
else { $common += @('-Os','-DNDEBUG') }
foreach ($include in $includes) { $common += "-I$include" }
$objects = @()
foreach ($source in $sources) {
  if (!(Test-Path -LiteralPath $source)) { throw "Missing dependency: $source" }
  $object = Join-Path $build (($source -replace '[/\\:.]','_') + '.o')
  $flags = $common
  if ($source -notlike 'vendor/*') { $flags += '-Werror' }
  else { $flags += '-Wno-unused-parameter' }
  Run-Checked 'arm-none-eabi-gcc' ($flags + @('-c',$source,'-o',$object))
  $objects += $object
}
$elf = Join-Path $build 'agent-light.elf'
Run-Checked 'arm-none-eabi-gcc' (@('-mcpu=cortex-m0','-mthumb',
  '-TSTM32F042F6PX_FLASH.ld','--specs=nano.specs','--specs=nosys.specs',
  '-Wl,--gc-sections',"-Wl,-Map=$build/agent-light.map",'-Wl,--print-memory-usage') +
  $objects + @('-o',$elf))
Run-Checked 'arm-none-eabi-size' @($elf)
Run-Checked 'arm-none-eabi-objcopy' @('-O','ihex',$elf,"$build/agent-light.hex")
Run-Checked 'arm-none-eabi-objcopy' @('-O','binary',$elf,"$build/agent-light.bin")
Get-FileHash "$build/agent-light.bin","$build/agent-light.hex" -Algorithm SHA256 |
  ForEach-Object { $_.Hash.ToLowerInvariant() + '  ' + (Split-Path $_.Path -Leaf) } |
  Set-Content "$build/SHA256SUMS.txt"
} finally {
  Pop-Location
}
