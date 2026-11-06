"""核验实际 ELF/HEX/BIN 的一致性、内存边界与中断向量。

版本：1.0.0（固件工具基线）；日期：2026-10-28。
用法：先构建 Debug/Release，再运行 py -3.14 firmware/tools/verify_artifacts.py。
依赖：标准库、PATH 中的 arm-none-eabi-nm，以及两种配置的已有产物。
副作用：覆盖两组 SHA256SUMS.txt 和 build/artifact-verification.json；
未接触设备，报告中的 hardware 始终为 NOT_RUN。
"""
import hashlib
import json
from pathlib import Path
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    """校验两种构建的向量、内存、禁用符号和 HEX/BIN 一致性并写报告。

    无参数；成功打印报告并返回 None。异常/断言中止，不把旧报告当作本次通过。
    检查 MSP 至少 768 字节、Flash 不超过 32 KB；报告不表示进行过实板测试。
    依赖文件缺失、nm 不可执行、格式错误或约束失败都会直接传播异常。
    """
    configurations = {}
    for name in ("Debug", "Release"):
        directory = ROOT / "build" / name
        elf = directory / "agent-light.elf"
        binary = (directory / "agent-light.bin").read_bytes()
        assert 0 < len(binary) <= 32768
        symbols = {}
        for line in subprocess.check_output(["arm-none-eabi-nm", str(elf)], text=True).splitlines():
            parts = line.split()
            if len(parts) == 3:
                symbols[parts[2]] = int(parts[0], 16)
        for banned in ("malloc", "free", "pvPortMalloc", "vPortFree", "_sbrk", "printf"):
            assert banned not in symbols, (name, banned)
        msp_free = 0x20001800 - symbols["_end"]
        assert msp_free >= 768
        assert struct.unpack_from("<I", binary)[0] == 0x20001800
        for vector, symbol in ((1, "Reset_Handler"), (11, "SVC_Handler"),
                               (14, "PendSV_Handler"), (15, "SysTick_Handler"),
                               (47, "USB_IRQHandler")):
            address = struct.unpack_from("<I", binary, vector * 4)[0]
            assert address == symbols[symbol] | 1, (name, vector, symbol)
        memory = {}
        base = 0
        eof = False
        for line in (directory / "agent-light.hex").read_text().splitlines():
            assert line.startswith(":")
            record = bytes.fromhex(line[1:])
            assert len(record) == record[0] + 5 and sum(record) & 255 == 0
            size, offset, kind = record[0], int.from_bytes(record[1:3], "big"), record[3]
            data = record[4:4 + size]
            if kind == 4:
                base = int.from_bytes(data, "big") << 16
            elif kind == 0:
                for index, byte in enumerate(data):
                    memory[base + offset + index] = byte
            elif kind == 1:
                eof = True
        assert eof and memory and min(memory) == 0x08000000
        reconstructed = bytes(memory.get(address, 0) for address in
                              range(0x08000000, max(memory) + 1))
        assert reconstructed == binary, name
        hashes = {f"agent-light.{extension}": hashlib.sha256(
            (directory / f"agent-light.{extension}").read_bytes()).hexdigest()
                  for extension in ("elf", "bin", "hex")}
        (directory / "SHA256SUMS.txt").write_text(
            "".join(f"{digest}  {filename}\n" for filename, digest in hashes.items()),
            encoding="utf-8")
        configurations[name] = dict(binary_bytes=len(binary),
                                     static_ram_aligned_bytes=symbols["_end"] - 0x20000000,
                                     msp_remaining_bytes=msp_free, sha256=hashes)
    report = dict(date="2026-10-28", result="PASS", configurations=configurations,
                  checks=["ELF vectors", "HEX checksums", "HEX equals BIN", "Flash/RAM bounds",
                          "no dynamic allocator symbols"], hardware="NOT_RUN")
    output = ROOT / "build" / "artifact-verification.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
