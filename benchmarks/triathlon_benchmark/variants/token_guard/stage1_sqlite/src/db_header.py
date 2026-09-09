from __future__ import annotations
import struct
from dataclasses import dataclass


MAGIC_HEADER = b"SQLite format 3\x00"


@dataclass
class DatabaseHeader:
    page_size: int
    write_version: int
    read_version: int
    reserved_space: int
    schema_cookie: int

    @classmethod
    def parse(cls, header_bytes: bytes) -> DatabaseHeader:
        if len(header_bytes) < 100:
            raise ValueError("Header bytes must be at least 100 bytes")
        if header_bytes[:16] != MAGIC_HEADER:
            raise ValueError(f"Invalid SQLite header magic: {header_bytes[:16]}")

        raw_page_size = struct.unpack(">H", header_bytes[16:18])[0]
        page_size = 65536 if raw_page_size == 1 else raw_page_size
        write_version = header_bytes[18]
        read_version = header_bytes[19]
        reserved_space = header_bytes[20]
        schema_cookie = struct.unpack(">I", header_bytes[40:44])[0]

        return cls(
            page_size=page_size,
            write_version=write_version,
            read_version=read_version,
            reserved_space=reserved_space,
            schema_cookie=schema_cookie,
        )
