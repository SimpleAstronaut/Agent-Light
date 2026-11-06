"""通过 USB CDC 串口执行实板协议验收，不执行烧录。

版本：1.0.0（固件工具基线）；日期：2026-10-28。
用法：不带参数只列端口；--port COM5 开始验收，--soak-hours 24 长稳测试；
--report firmware/build/hil-report.json 指定报告，端口按实际设备替换。
依赖：pyserial 和同目录 protocol_reference；测试会改变灯态，结束尝试置 IDLE。
限制：协议 ACK/STATUS 不能代替光学、电流、PWM 或 USB 挂起的实物测量。
"""
import argparse
import binascii
import json
import struct
import time
from pathlib import Path

import serial
from serial.tools.list_ports import comports
from protocol_reference import decode, encode, frame


class Device:
    """独占一个 CDC 串口的同步客户端；调用者负责关闭 serial，不支持并发。"""
    def __init__(self, port):
        """打开端口并清空旧输入，为单线程串行事务准备序号。

        Args:
            port: 非空串口名，如 COM5；必须是目标 CDC 设备。
        Raises:
            serial.SerialException: 端口无法打开/配置。

        实例持有 Serial 对象；调用方必须在 finally 中关闭，不支持并发事务。
        """
        self.serial = serial.Serial(port, 115200, timeout=0.1, write_timeout=1)
        self.seq = 0
        self.serial.reset_input_buffer()

    def transact(self, command, payload=b"", expect_error=None):
        """发送一个事务并等待匹配响应，最多三次重发相同 wire/seq。

        Args:
            command: 请求码 1/2/3（错误用例可传其他单字节值）。
            payload: bytes，协议负载通常不超过 32 字节，默认空。
            expect_error: 期望的 NACK 错误码；None 表示期望成功响应。
        Returns:
            已匹配 seq 且通过头/长度/CRC 检查的响应 payload（bytes）。
        Raises:
            TimeoutError: 三轮各一秒仍无匹配响应。
            AssertionError: 响应类型或业务错误码与预期不同。
            ValueError: 收到的 COBS 编码非法（本测试工具直接暴露该错误）。
            serial.SerialException: 串口读写失败。

        每次新调用推进 seq，重试保持 seq；独占串口，不能多线程共享。
        """
        seq = self.seq
        self.seq = (self.seq + 1) & 255
        wire = encode(frame(command, seq, payload))
        for attempt in range(3):
            self.serial.write(wire)
            end = time.monotonic() + 1
            while time.monotonic() < end:
                response = self.serial.read_until(b"\0", 80)
                if not response or response[-1] != 0:
                    continue
                raw = decode(response)
                if len(raw) < 6 or raw[0] != 1 or len(raw) != raw[3] + 6:
                    continue
                if binascii.crc_hqx(raw[:-2], 0xffff) != int.from_bytes(raw[-2:], "little"):
                    continue
                if raw[2] != seq:
                    continue
                if expect_error is not None:
                    assert raw[1] == 0x82 and raw[4:6] == bytes([command, expect_error])
                else:
                    assert raw[1] == (0x83 if command == 3 else 0x81), raw.hex()
                    if command != 3:
                        assert raw[4:6] == bytes([command, 0]), raw.hex()
                return raw[4:-2]
        raise TimeoutError(f"no matching response: command={command} seq={seq}")

    def status(self):
        """读取并解包 GET_STATUS。

        无参数；返回包含 mode/state/revision 等合约字段的 dict，字段单位见协议。
        负载不是 17 字节时断言失败；其他错误沿 transact 传播。
        """
        data = self.transact(3)
        assert len(data) == 17
        fields = struct.unpack("<BBIBBBHIH", data)
        return dict(zip(("mode", "state", "revision", "revision_valid", "brightness",
                         "last_seq", "fw_version", "uptime_s", "crc_drop_count"), fields))

    def set(self, revision, state, brightness=35):
        """发送 SET_STATE 并确认 ACK 回显的 revision。

        Args:
            revision: 状态版本整数，按 uint32_t 取模编码。
            state: 0..4 的业务灯态；越界会被设备 NACK。
            brightness: 20..100 整数百分比，默认 35。
        Returns:
            ACK applied 字节：1 为新 revision，0 为相同 revision 的幂等设置。
        Raises:
            AssertionError: ACK 内容不符或设备拒绝；通信错误沿 transact 传播。
            struct.error: state/brightness 无法编码为 uint8_t。
        """
        payload = struct.pack("<IBB", revision & 0xffffffff, state, brightness)
        data = self.transact(1, payload)
        assert len(data) == 7 and int.from_bytes(data[2:6], "little") == revision & 0xffffffff
        return data[6]


def main():
    """解析命令行，列端口或执行五态、边界、超时和可选长稳验收。

    无参数，使用 argparse 读取命令行；成功返回 None。
    打开设备后在 finally 尝试 IDLE、关闭串口并写 JSON，测试异常继续抛出。
    仅列端口时不创建 Device，也不打开串口或写报告。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", help="例如 COM5；不指定时只列出端口")
    parser.add_argument("--soak-hours", type=float, default=0)
    parser.add_argument("--report", type=Path, default=Path("hil-report.json"))
    args = parser.parse_args()
    if not args.port:
        for port in comports():
            print(port.device, port.description, port.hwid)
        return
    device = Device(args.port)
    report = {"port": args.port, "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
              "result": "FAIL", "checks": [], "limitations":
              "Optical/PWM/current/suspend/hotplug require separate physical measurements."}
    revision = None
    try:
        status = device.status()
        report["initial_status"] = status
        revision = (status["revision"] + 1) & 0xffffffff if status["revision_valid"] else 1
        for state in range(5):
            device.set(revision, state)
            current = device.status()
            assert current["mode"] == 2 and current["state"] == state
            assert current["revision"] == revision and current["brightness"] == 35
            print(f"Observe state {state}: {current}")
            time.sleep(1)
            revision = (revision + 1) & 0xffffffff
        report["checks"].append("five state ACK/STATUS and revision")
        for brightness in (20, 35, 100):
            device.set(revision, 1, brightness)
            assert device.status()["brightness"] == brightness
            revision = (revision + 1) & 0xffffffff
        report["checks"].append("brightness boundaries")
        device.transact(1, struct.pack("<IBB", revision, 1, 19), expect_error=4)
        device.set(revision, 4)
        assert device.set(revision, 4) == 0
        report["checks"].append("invalid value and revision idempotency")
        # 不发送任何请求，确保 GET_STATUS 不会替代 SET 恢复 ACTIVE。
        time.sleep(5.2)
        assert device.status()["mode"] == 3
        device.transact(2)
        assert device.status()["mode"] == 3
        device.set(revision, 4)
        assert device.status()["mode"] == 2
        report["checks"].append("link timeout, heartbeat no restore, identical SET restore")
        for _ in range(768):
            device.transact(2)
        report["checks"].append("768 transactions / seq wrap")
        deadline = time.monotonic() + args.soak_hours * 3600
        samples = 0
        while time.monotonic() < deadline:
            device.transact(2)
            assert device.status()["mode"] == 2
            samples += 1
            time.sleep(1)
        report["soak_samples"] = samples
        report["result"] = "PASS"
    except Exception as error:
        report["error"] = repr(error)
        raise
    finally:
        try:
            if revision is not None:
                device.set((revision + 1) & 0xffffffff, 0)
        finally:
            device.serial.close()
            args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
