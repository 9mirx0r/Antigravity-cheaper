"""Bencode Decoder and Encoder."""

from __future__ import annotations
from typing import Any, Tuple


def _decode_from(data: bytes, offset: int) -> Tuple[Any, int]:
    if offset >= len(data):
        raise ValueError("Unexpected end of bencoded data")

    b = data[offset : offset + 1]

    if b == b"i":
        end = data.find(b"e", offset + 1)
        if end == -1:
            raise ValueError("Unterminated bencoded integer")
        val = int(data[offset + 1 : end])
        return val, end + 1

    elif b == b"l":
        curr = offset + 1
        items = []
        while curr < len(data) and data[curr : curr + 1] != b"e":
            item, curr = _decode_from(data, curr)
            items.append(item)
        if curr >= len(data) or data[curr : curr + 1] != b"e":
            raise ValueError("Unterminated bencoded list")
        return items, curr + 1

    elif b == b"d":
        curr = offset + 1
        d = {}
        while curr < len(data) and data[curr : curr + 1] != b"e":
            key, curr = _decode_from(data, curr)
            val, curr = _decode_from(data, curr)
            d[key] = val
        if curr >= len(data) or data[curr : curr + 1] != b"e":
            raise ValueError("Unterminated bencoded dictionary")
        return d, curr + 1

    elif b.isdigit():
        colon = data.find(b":", offset)
        if colon == -1:
            raise ValueError("Invalid bencoded string length prefix")
        length = int(data[offset:colon])
        start = colon + 1
        end = start + length
        if end > len(data):
            raise ValueError("Bencoded string length exceeds buffer")
        return data[start:end], end

    else:
        raise ValueError(f"Invalid bencoded prefix at offset {offset}: {b!r}")


def bencode_decode(data: bytes) -> Any:
    """Decodes a Bencoded byte sequence into Python primitives."""
    val, _ = _decode_from(data, 0)
    return val


def bencode_encode(data: Any) -> bytes:
    """Encodes Python primitives into a standard Bencoded byte string."""
    if isinstance(data, int):
        return b"i" + str(data).encode("ascii") + b"e"
    elif isinstance(data, bytes):
        return str(len(data)).encode("ascii") + b":" + data
    elif isinstance(data, str):
        raw = data.encode("utf-8")
        return str(len(raw)).encode("ascii") + b":" + raw
    elif isinstance(data, (list, tuple)):
        return b"l" + b"".join(bencode_encode(x) for x in data) + b"e"
    elif isinstance(data, dict):
        items = []
        for k, v in data.items():
            k_bytes = k if isinstance(k, bytes) else str(k).encode("utf-8")
            items.append((k_bytes, v))
        items.sort(key=lambda x: x[0])
        encoded_parts = []
        for k_bytes, v in items:
            encoded_parts.append(bencode_encode(k_bytes))
            encoded_parts.append(bencode_encode(v))
        return b"d" + b"".join(encoded_parts) + b"e"
    else:
        raise TypeError(f"Cannot bencode object of type: {type(data)}")
