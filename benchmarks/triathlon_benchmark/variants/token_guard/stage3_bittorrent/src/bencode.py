from __future__ import annotations
from typing import Any, Tuple


def _decode_item(data: bytes, idx: int) -> Tuple[Any, int]:
    if idx >= len(data):
        raise ValueError("Unexpected end of bencoded data")

    char = data[idx : idx + 1]

    if char == b"i":
        end_idx = data.index(b"e", idx + 1)
        val = int(data[idx + 1 : end_idx])
        return val, end_idx + 1

    elif char == b"l":
        items = []
        curr = idx + 1
        while data[curr : curr + 1] != b"e":
            item, curr = _decode_item(data, curr)
            items.append(item)
        return items, curr + 1

    elif char == b"d":
        d = {}
        curr = idx + 1
        while data[curr : curr + 1] != b"e":
            key, curr = _decode_item(data, curr)
            if not isinstance(key, (bytes, str)):
                raise ValueError("Dict key must be string or bytes")
            if isinstance(key, str):
                key = key.encode("utf-8")
            val, curr = _decode_item(data, curr)
            d[key] = val
        return d, curr + 1

    elif char.isdigit():
        colon_idx = data.index(b":", idx)
        length = int(data[idx:colon_idx])
        start = colon_idx + 1
        end = start + length
        return data[start:end], end

    else:
        raise ValueError(f"Invalid bencode token: {char!r} at index {idx}")


def bencode_decode(data: bytes) -> Any:
    """Decodes Bencoded byte data into Python objects."""
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError(f"bencode_decode expects bytes, got {type(data)}")
    val, _ = _decode_item(bytes(data), 0)
    return val


def bencode_encode(data: Any) -> bytes:
    """Encodes Python objects into Bencoded byte strings."""
    if isinstance(data, bool):
        # Must be handled before int because bool is subclass of int
        return bencode_encode(int(data))
    elif isinstance(data, int):
        return f"i{data}e".encode("ascii")
    elif isinstance(data, bytes):
        return f"{len(data)}:".encode("ascii") + data
    elif isinstance(data, str):
        raw = data.encode("utf-8")
        return f"{len(raw)}:".encode("ascii") + raw
    elif isinstance(data, (list, tuple)):
        parts = [b"l"]
        for item in data:
            parts.append(bencode_encode(item))
        parts.append(b"e")
        return b"".join(parts)
    elif isinstance(data, dict):
        def _get_key_bytes(k: Any) -> bytes:
            if isinstance(k, bytes):
                return k
            elif isinstance(k, str):
                return k.encode("utf-8")
            return str(k).encode("utf-8")

        sorted_keys = sorted(data.keys(), key=_get_key_bytes)
        parts = [b"d"]
        for k in sorted_keys:
            kb = _get_key_bytes(k)
            parts.append(bencode_encode(kb))
            parts.append(bencode_encode(data[k]))
        parts.append(b"e")
        return b"".join(parts)
    else:
        raise TypeError(f"Cannot bencode object of type {type(data)}")
