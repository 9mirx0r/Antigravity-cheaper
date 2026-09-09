from __future__ import annotations
import struct
from typing import Any, List

from .varint import read_varint


class RecordDecoder:
    """Decodes SQLite record payloads into Python data types."""

    @classmethod
    def decode_record(cls, payload_bytes: bytes) -> List[Any]:
        if not payload_bytes:
            return []

        header_len, consumed = read_varint(payload_bytes, 0)
        serial_types: List[int] = []
        curr = consumed
        while curr < header_len:
            st, n = read_varint(payload_bytes, curr)
            serial_types.append(st)
            curr += n

        body_offset = header_len
        values: List[Any] = []
        for st in serial_types:
            if st == 0:
                values.append(None)
            elif st == 1:
                val = struct.unpack(">b", payload_bytes[body_offset : body_offset + 1])[0]
                values.append(val)
                body_offset += 1
            elif st == 2:
                val = struct.unpack(">h", payload_bytes[body_offset : body_offset + 2])[0]
                values.append(val)
                body_offset += 2
            elif st == 3:
                val = int.from_bytes(payload_bytes[body_offset : body_offset + 3], "big", signed=True)
                values.append(val)
                body_offset += 3
            elif st == 4:
                val = struct.unpack(">i", payload_bytes[body_offset : body_offset + 4])[0]
                values.append(val)
                body_offset += 4
            elif st == 5:
                val = int.from_bytes(payload_bytes[body_offset : body_offset + 6], "big", signed=True)
                values.append(val)
                body_offset += 6
            elif st == 6:
                val = struct.unpack(">q", payload_bytes[body_offset : body_offset + 8])[0]
                values.append(val)
                body_offset += 8
            elif st == 7:
                val = struct.unpack(">d", payload_bytes[body_offset : body_offset + 8])[0]
                values.append(val)
                body_offset += 8
            elif st == 8:
                values.append(0)
            elif st == 9:
                values.append(1)
            elif st >= 12 and (st % 2 == 0):
                length = (st - 12) // 2
                values.append(payload_bytes[body_offset : body_offset + length])
                body_offset += length
            elif st >= 13 and (st % 2 == 1):
                length = (st - 13) // 2
                raw = payload_bytes[body_offset : body_offset + length]
                values.append(raw.decode("utf-8", errors="replace"))
                body_offset += length
            else:
                values.append(None)

        return values
