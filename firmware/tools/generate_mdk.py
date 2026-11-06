"""生成/更新 ARM Compiler 5 的 µVision 工程。

版本：1.0.0（固件工具基线）；日期：2026-10-28。
用法：在项目根运行 py -3.14 firmware/tools/generate_mdk.py。
依赖：Python 标准库及已下载的锁定 CubeF0；不修改 vendor。
副作用：写 MDK 工程与派生启动文件；已有工程保留设备包/调试设置。
重新生成启动文件会覆盖该派生文件中的手工注释，模块说明见接口文档。
"""
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
VENDOR = "vendor/STM32CubeF0"
CMSIS = f"{VENDOR}/Drivers/CMSIS"
HAL = f"{VENDOR}/Drivers/STM32F0xx_HAL_Driver"
USB = f"{VENDOR}/Middlewares/ST/STM32_USB_Device_Library"
RTOS = f"{VENDOR}/Middlewares/Third_Party/FreeRTOS/Source"


def element(parent, tag, text):
    """追加一个带文本的 XML 子元素，所有权由 parent 元素树持有。

    Args:
        parent: 非 None 的 Element，原地追加孩子。
        tag: 子元素标签名字符串。
        text: 用 str() 转换为文本的值。
    Returns:
        新建的 Element，可继续追加属性或子元素。
    """
    child = ET.SubElement(parent, tag)
    child.text = str(text)
    return child


def set_controls(parent, misc, defines, includes):
    """覆盖 µVision 的编译/汇编选项，保持规定的 XML 顺序。

    Args:
        parent: 非 None 的 Cads/Aads Element，原地更新 VariousControls。
        misc: 额外选项文本。
        defines: 逗号分隔的宏定义文本。
        includes: 分号分隔的包含目录文本。
    Returns:
        None；空 Undefine 也会写出，避免 µVision5 错读字段顺序。
    """
    controls = parent.find("VariousControls")
    if controls is None:
        controls = ET.SubElement(parent, "VariousControls")
    controls.clear()
    for tag, value in (("MiscControls", misc), ("Define", defines),
                       ("Undefine", ""), ("IncludePath", includes)):
        element(controls, tag, value)


def main():
    """从锁定依赖生成启动文件，并更新已有工程或创建两配置工程。

    无参数；从 ROOT 定位输入，不依赖进程当前目录。返回 None。
    已有工程只更新编译/汇编选项；文件缺失、XML 错误或写入失败直接抛异常。
    会覆盖派生启动文件，因此不应在该文件保存需长期维护的自定义逻辑。
    """
    destination = ROOT / "MDK-ARM"
    destination.mkdir(exist_ok=True)
    startup = ROOT / CMSIS / "Device/ST/STM32F0xx/Source/Templates/arm/startup_stm32f042x6.s"
    text = startup.read_text(encoding="utf-8")
    text = text.replace("Stack_Size      EQU     0x00000400", "Stack_Size      EQU     0x00000300")
    text = text.replace("Heap_Size       EQU     0x00000200", "Heap_Size       EQU     0x00000000")
    (destination / "startup_stm32f042x6.s").write_text(text, encoding="utf-8")
    modules = ["hal", "hal_cortex", "hal_gpio", "hal_dma", "hal_rcc", "hal_rcc_ex",
               "hal_flash", "hal_flash_ex", "hal_pwr", "hal_pcd", "hal_pcd_ex",
               "ll_usb", "hal_tim", "hal_tim_ex"]
    groups = {
        "Application": [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / "app").glob("*.c"))],
        "Core": ["Core/Src/main.c", "MDK-ARM/startup_stm32f042x6.s",
                 f"{CMSIS}/Device/ST/STM32F0xx/Source/Templates/system_stm32f0xx.c"],
        "USB": ["USB_Device/usb_device.c", "USB_Device/usbd_conf.c",
                f"{USB}/Core/Src/usbd_core.c", f"{USB}/Core/Src/usbd_ctlreq.c",
                f"{USB}/Core/Src/usbd_ioreq.c", f"{USB}/Class/CDC/Src/usbd_cdc.c"],
        "FreeRTOS": [f"{RTOS}/tasks.c", f"{RTOS}/list.c", f"{RTOS}/portable/RVDS/ARM_CM0/port.c"],
        "HAL": [f"{HAL}/Src/stm32f0xx_{module}.c" for module in modules],
    }
    includes = ["app", "Core/Inc", "USB_Device", f"{HAL}/Inc", f"{CMSIS}/Include",
                f"{CMSIS}/Device/ST/STM32F0xx/Include", f"{USB}/Core/Inc",
                f"{USB}/Class/CDC/Inc", f"{RTOS}/include", f"{RTOS}/portable/RVDS/ARM_CM0"]
    include_paths = ";".join("..\\" + p.replace("/", "\\") for p in includes)
    project_path = destination / "agent-light.uvprojx"
    if project_path.exists():
        # 已有工程仅修复编译选项，保留用户的DFP、SWD、Flash和其他GUI设置。
        tree = ET.parse(project_path)
        for target in tree.findall("./Targets/Target"):
            name = target.findtext("TargetName")
            arm = target.find("./TargetOption/TargetArmAds")
            cads = arm.find("Cads")
            cads.find("SplitLS").text = "0"
            set_controls(cads, "--c99 --split_sections",
                         "USE_HAL_DRIVER,STM32F042x6" + (",NDEBUG" if name == "Release" else ""),
                         include_paths)
            set_controls(arm.find("Aads"), "", "__MICROLIB", "")
        ET.indent(tree, "  ")
        tree.write(project_path, encoding="utf-8", xml_declaration=True)
        print("Updated MDK compiler/assembler settings; retained device/debug configuration.")
        return
    project = ET.Element("Project", {"xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
                                    "xsi:noNamespaceSchemaLocation": "project_projx.xsd"})
    element(project, "SchemaVersion", "2.1")
    element(project, "Header", "### uVision Project, (C) Keil Software")
    targets = ET.SubElement(project, "Targets")
    for name in ("Debug", "Release"):
        target = ET.SubElement(targets, "Target")
        element(target, "TargetName", name)
        element(target, "ToolsetNumber", "0x4")
        element(target, "ToolsetName", "ARM-ADS")
        element(target, "pCCUsed", "5060750::V5.06 update 6 (build 750)::ARMCC")
        element(target, "uAC6", "0")
        options = ET.SubElement(target, "TargetOption")
        common = ET.SubElement(options, "TargetCommonOption")
        for key, value in dict(Device="STM32F042F6Px", Vendor="STMicroelectronics",
                               Cpu='IRAM(0x20000000,0x1800) IROM(0x08000000,0x8000) CPUTYPE("Cortex-M0") CLOCK(48000000) ELITTLE',
                               OutputDirectory=f"..\\build\\MDK-{name}\\", OutputName="agent-light",
                               CreateExecutable=1, CreateHexFile=1, DebugInformation=1,
                               BrowseInformation=0, ListingPath=f"..\\build\\MDK-{name}\\").items():
            element(common, key, value)
        arm = ET.SubElement(options, "TargetArmAds")
        ads = ET.SubElement(arm, "ArmAdsMisc")
        for key, value in dict(GenerateListings=0, asHll=1, asAsm=1, asMacX=1,
                               adsALst=1, adsACrf=1, adsLmap=1, adsLcgr=1,
                               adsLsym=1, adsLxref=1, adsLinfo=1, adsLcall=1,
                               adsLdbg=1, adsLsta=1, adsLcod=1, adsLsumm=1,
                               useUlib=1).items():
            element(ads, key, value)
        cads = ET.SubElement(arm, "Cads")
        for key, value in dict(Optim=1 if name == "Debug" else 4, oTime=0,
                               SplitLS=0, OneElfS=1, wLevel=2, uC99=1, EnumInt=0,
                               PlainCh=0, v6Lang=1, v6LangP=1).items():
            element(cads, key, value)
        set_controls(cads, "--c99 --split_sections",
                     "USE_HAL_DRIVER,STM32F042x6" + (",NDEBUG" if name == "Release" else ""),
                     include_paths)
        assembler = ET.SubElement(arm, "Aads")
        set_controls(assembler, "", "__MICROLIB", "")
        linker = ET.SubElement(arm, "LDads")
        for key, value in dict(umfTarg=0, Ropi=0, Rwpi=0, noStLib=0,
                               RepFail=1, useFile=1, ScatterFile=".\\agent-light.sct").items():
            element(linker, key, value)
        group_list = ET.SubElement(target, "Groups")
        for label, paths in groups.items():
            group = ET.SubElement(group_list, "Group")
            element(group, "GroupName", label)
            files = ET.SubElement(group, "Files")
            for path in paths:
                assert (ROOT / path).is_file(), path
                file = ET.SubElement(files, "File")
                element(file, "FileName", Path(path).name)
                element(file, "FileType", 2 if path.endswith(".s") else 1)
                element(file, "FilePath", "..\\" + path.replace("/", "\\"))
    ET.indent(project, "  ")
    ET.ElementTree(project).write(destination / "agent-light.uvprojx", encoding="utf-8", xml_declaration=True)
    print("Generated MDK-ARM/agent-light.uvprojx; GUI build and SWD setup pending.")


if __name__ == "__main__":
    main()
