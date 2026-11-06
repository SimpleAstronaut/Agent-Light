"""Frozen USB v1 framing; malformed input never reaches transaction matching."""
import binascii
import struct


def encode(command, seq, payload=b""):
    if len(payload) > 32:
        raise ValueError("payload")
    raw = bytes([1, command, seq, len(payload)]) + payload
    raw += struct.pack("<H", binascii.crc_hqx(raw, 0xffff))
    result = bytearray()
    for block in raw.split(b"\0"):
        result.append(len(block) + 1)
        result.extend(block)
    return bytes(result) + b"\0"


def decode(wire):
    if not wire.endswith(b"\0") or len(wire) > 40:
        raise ValueError("frame")
    data, result, offset = wire[:-1], bytearray(), 0
    while offset < len(data):
        code = data[offset]
        offset += 1
        if not code or offset + code - 1 > len(data):
            raise ValueError("COBS")
        block = data[offset:offset + code - 1]
        if 0 in block:
            raise ValueError("COBS")
        result.extend(block)
        offset += code - 1
        if code < 255 and offset < len(data):
            result.append(0)
    if len(result) < 6 or result[0] != 1 or result[3] > 32 or len(result) != result[3] + 6:
        raise ValueError("length")
    if binascii.crc_hqx(result[:-2], 0xffff) != int.from_bytes(result[-2:], "little"):
        raise ValueError("CRC")
    return result[1], result[2], bytes(result[4:-2])
