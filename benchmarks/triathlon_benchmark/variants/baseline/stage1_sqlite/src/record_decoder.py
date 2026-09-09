"""SQLite Record Decoder."""

from __future__ import annotations
import struct
from typing import Any, List
from src.varint import read_varint


class RecordDecoder:
    """Decodes raw SQLite record payloads into Python values."""

    @staticmethod
    def decode_record(payload_bytes: bytes) -> List[Any]:
        if not payload_bytes:
            return []

        header_len, offset = read_varint(payload_bytes, 0)
        serial_types: List[int] = []

        while offset < header_len:
            stype, consumed = read_varint(payload_bytes, offset)
            serial_types.append(stype)
            offset += consumed

        body_offset = header_len
        values: List[Any] = []

        for stype in serial_types:
            if stype == 0:
                values.append(None)
            elif stype == 1:
                val = struct.unpack(">b", payload_bytes[body_offset : body_offset + 1])[0]
                values.append(val)
                body_offset += 1
            elif stype == 2:
                val = struct.unpack(">h", payload_bytes[body_offset : body_offset + 2])[0]
                values.append(val)
                body_offset += 2
            elif stype == 3:
                val = int.from_bytes(
                    payload_bytes[body_offset : body_offset + 3],
                    byteorder="big",
                    signed=True,
                )
                values.append(val)
                body_offset += 3
            elif stype == 4:
                val = struct.unpack(">i", payload_bytes[body_offset : body_offset + 4])[0]
                values.append(val)
                body_offset += 4
            elif stype == 5:
                val = int.from_bytes(
                    payload_bytes[body_offset : body_offset + 6],
                    byteorder="big",
                    signed=True,
                )
                values.append(val)
                body_offset += 6
            elif stype == 6:
                val = struct.unpack(">q", payload_bytes[body_offset : body_offset + 8])[0]
                values.append(val)
                body_offset += 8
            elif stype == 7:
                val = struct.unpack(">d", payload_bytes[body_offset : body_offset + 8])[0]
                values.append(val)
                body_offset += 8
            elif stype == 8:
                values.append(0)
            elif stype == 9:
                values.append(1)
            elif stype in (10, 11):
                values.append(None)
            elif stype >= 12 and (stype % 2 == 0):
                blob_len = (stype - 12) // 2
                val = payload_bytes[body_offset : body_offset + blob_len]
                values.append(val)
                body_offset += blob_len
            elif stype >= 13 and (stype % 2 == 1):
                text_len = (stype - 13) // 2
                text_bytes = payload_bytes[body_offset : body_offset + text_len]
                val = text_bytes.decode("utf-8", errors="replace")
                values.append(val)
                body_offset += text_len
            else:
                values.append(None)

        return values
