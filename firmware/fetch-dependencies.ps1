<#
.SYNOPSIS
获取锁定 STM32CubeF0 v1.11.5 及项目所需子模块。
.DESCRIPTION
版本：1.0.0；日期：2026-10-28。
用法：在项目根运行 .\firmware\fetch-dependencies.ps1；依赖 git 和网络。
无参数；写 vendor/STM32CubeF0。已有 HEAD 不符锁定提交则抛错保留现场。
只检出 CMSIS、HAL、USB 和 FreeRTOS；不修改已有厂商源文件内容。
#>
$ErrorActionPreference = 'Stop'
$vendorPath = Join-Path $PSScriptRoot 'vendor/STM32CubeF0'
$expected = 'e220bfb12a162cfbf3bb65663e987e0d6550e9b4'
<#
.SYNOPSIS
运行 git 并在失败时中止依赖获取。
.PARAMETER Arguments
git 子命令及参数字符串数组，逐项传给 git，不作为 shell 文本解释。
.OUTPUTS
透传 git 输出；非零退出码抛出 Dependency checkout failed。
#>
function Git-Checked([string[]]$Arguments) {
  & git @Arguments
  if ($LASTEXITCODE -ne 0) { throw 'Dependency checkout failed' }
}
if (!(Test-Path -LiteralPath $vendorPath)) {
  Git-Checked @('clone','--depth','1','--branch','v1.11.5','--filter=blob:none',
    '--sparse','https://github.com/STMicroelectronics/STM32CubeF0.git',$vendorPath)
}
$actual = & git -C $vendorPath rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $actual -ne $expected) {
  throw 'Existing dependency differs from lock; preserve it and resolve manually.'
}
Git-Checked @('-C',$vendorPath,'sparse-checkout','set','--skip-checks',
  'Drivers/CMSIS','Drivers/STM32F0xx_HAL_Driver',
  'Middlewares/ST/STM32_USB_Device_Library','Middlewares/Third_Party/FreeRTOS')
Git-Checked @('-C',$vendorPath,'submodule','update','--init','--depth','1',
  'Drivers/CMSIS/Device/ST/STM32F0xx','Drivers/STM32F0xx_HAL_Driver')
