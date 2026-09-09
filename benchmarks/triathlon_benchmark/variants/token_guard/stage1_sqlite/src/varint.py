from __future__ import annotations
from typing import Tuple


def read_varint(buffer: bytes, offset: int = 0) -> Tuple[int, int]:
    """Reads a SQLite variable-length integer (1 to 9 bytes).

    Returns (value, bytes_consumed).
    """
    val = 0
    for i in range(8):
        b = buffer[offset + i]
        val = (val << 7) | (b & 0x7F)
        if (b & 0x80) == 0:
            return val, i + 1
    # 9th byte contributes all 8 bits
    b = buffer[offset + 8]
    val = (val << 8) | b
    return val, 9


def write_varint(value: int) -> bytes:
    """Encodes an integer into SQLite varint format (1 to 9 bytes)."""
    if value < 0:
        value &= 0xFFFFFFFFFFFFFFFF

    if value >= (1 << 56):
        out = bytearray(9)
        out[8] = value & 0xFF
        value >>= 8
        for i in range(7, -1, -1):
            out[i] = (value & 0x7F) | 0x80
            value >>= 7
        return bytes(out)

    chunks = [value & 0x7F]
    value >>= 7
    while value > 0:
        chunks.append(value & 0x7F)
        value >>= 7
    chunks.reverse()
    for i in range(len(chunks) - 1):
        chunks[i] |= 0x80
    return bytes(chunks)
