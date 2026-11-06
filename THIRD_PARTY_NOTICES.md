# Third-party components

The root MIT license covers original Agent Light code, documentation and design
contributions. It does not relicense third-party code, libraries, symbols,
footprints, trademarks or referenced documents.

## Included ST startup assembly

`firmware/MDK-ARM/startup_stm32f042x6.s` derives from the STMicroelectronics
CMSIS Device F0 startup template, pinned by the project's STM32CubeF0 v1.11.5
dependency baseline. Copyright (c) 2016 STMicroelectronics. The original copyright
header is retained. Agent Light adjusts application startup settings, including
the stack/heap allocation, for this firmware.

This file is under Apache-2.0, not the root MIT license. The component license is
included in `firmware/MDK-ARM/LICENSE`, copied from the pinned CMSIS Device F0
component's `LICENSE.md`.

## Dependencies fetched separately

The repository does not vendor STM32CubeF0, Python virtual environments or npm
dependencies. `firmware/fetch-dependencies.ps1` fetches the pinned upstream
sources. Keep their license files and notices when distributing firmware or
bundling dependencies. The pinned CubeF0 component inventory identifies CMSIS
and CMSIS Device as Apache-2.0, STM32F0 HAL as BSD-3-Clause, FreeRTOS as MIT, and
the bundled ST USB Device library as ST SLA0044. Check the actual fetched
component license when changing dependencies.

Python and Node dependencies remain under their own licenses. DSH and Cordis
are peer dependencies of the plugin; the DSH installation is not redistributed
here. Package manifests and lockfiles record the selected dependencies.

EDA project packages may contain library symbol/footprint references or assets
from component libraries. Those third-party library assets retain their own
terms; the MIT grant applies to original project contributions. Referenced
manufacturer datasheets are linked rather than republished in this repository.
