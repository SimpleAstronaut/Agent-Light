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

## Windows desktop distribution

The onedir desktop distribution includes CPython 3.14.0 (Python Software
Foundation License), PySide6/shiboken6 and the Qt 6.10.3 Core, Gui, Widgets,
Network and Svg runtime (Qt open-source LGPL-3.0/GPL-3.0 alternatives and the
applicable Qt exceptions), aiohttp and its dependencies, pyserial (BSD),
jsonschema and its dependencies. Exact versions and archive hashes are recorded
in `packaging/windows/runtime-lock.json`. The distribution's `licenses/`
directory carries available dependency notices and the Qt license texts.

Qt DLLs remain separate and replaceable in `_internal/PySide6`; the build does
not statically link Qt. Unused Qt PDF, QML, Quick and Virtual Keyboard components
are excluded from the desktop bundle. Upstream Qt sources and licensing are
available at https://code.qt.io/cgit/qt/ and https://www.qt.io/licensing/.
PySide sources are at https://code.qt.io/cgit/pyside/pyside-setup.git/.
Agent Light build scripts are included in this MIT-licensed repository.

PyInstaller 6.16.0 creates the frozen application; its bootloader distribution
exception applies. Inno Setup 6.7.4 creates the per-user installer and retains
its upstream copyright and license. Node, DSH and Cordis are not bundled.
