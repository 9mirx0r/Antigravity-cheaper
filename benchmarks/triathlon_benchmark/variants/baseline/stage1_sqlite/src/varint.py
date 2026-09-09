"""SQLite Variable-Length Integer (Varint) Reader and Writer."""

from __future__ import annotations
from typing import Tuple


def read_varint(buffer: bytes, offset: int = 0) -> Tuple[int, int]:
    """Reads a variable-length integer (1 to 9 bytes) from buffer starting at offset.

    Returns (value, bytes_consumed).
    """
    val = 0
    for i in range(8):
        if offset + i >= len(buffer):
            raise ValueError("Buffer overrun while reading varint")
        b = buffer[offset + i]
        val = (val << 7) | (b & 0x7F)
        if not (b & 0x80):
            return val, i + 1

    # 9th byte contributes all 8 bits
    if offset + 8 >= len(buffer):
        raise ValueError("Buffer overrun while reading 9th byte of varint")
    b = buffer[offset + 8]
    val = (val << 8) | b
    return val, 9


def write_varint(value: int) -> bytes:
    """Encodes an integer into SQLite varint format (1 to 9 bytes)."""
    if value < 0:
        value &= 0xFFFFFFFFFFFFFFFF

    if value >= (1 << 56):
        # 9 bytes total
        b9 = value & 0xFF
        remaining = value >> 8
        chunks = []
        for _ in range(8):
            chunks.append((remaining & 0x7F) | 0x80)
            remaining >>= 7
        chunks.reverse()
        return bytes(chunks) + bytes([b9])

    chunks = []
    chunks.append(value & 0x7F)
    value >>= 7
    while value > 0:
        chunks.append((value & 0x7F) | 0x80)
        value >>= 7
    chunks.reverse()
    return bytes(chunks)
