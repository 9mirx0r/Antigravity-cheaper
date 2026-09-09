from __future__ import annotations
import struct
from typing import Any, Dict, List, Optional

from .varint import read_varint


class BTreePage:
    """Parses and encapsulates a SQLite B-tree page."""

    LEAF_TABLE = 0x0D
    INTERIOR_TABLE = 0x05
    LEAF_INDEX = 0x0A
    INTERIOR_INDEX = 0x02

    def __init__(
        self,
        page_type: int,
        first_freeblock: int,
        cell_count: int,
        cell_content_offset: int,
        rightmost_pointer: Optional[int],
        cell_pointers: List[int],
        cells: List[Dict[str, Any]],
        page_number: int = 1,
    ):
        self.page_type = page_type
        self.first_freeblock = first_freeblock
        self.cell_count = cell_count
        self.cell_content_offset = cell_content_offset
        self.rightmost_pointer = rightmost_pointer
        self.cell_pointers = cell_pointers
        self.cells = cells
        self.page_number = page_number

    @classmethod
    def parse(cls, page_bytes: bytes, page_number: int = 1) -> BTreePage:
        header_offset = 100 if page_number == 1 else 0

        page_type = page_bytes[header_offset]
        first_freeblock = struct.unpack(">H", page_bytes[header_offset + 1 : header_offset + 3])[0]
        cell_count = struct.unpack(">H", page_bytes[header_offset + 3 : header_offset + 5])[0]
        raw_cell_content = struct.unpack(">H", page_bytes[header_offset + 5 : header_offset + 7])[0]
        cell_content_offset = 65536 if raw_cell_content == 0 else raw_cell_content

        if page_type in (cls.INTERIOR_TABLE, cls.INTERIOR_INDEX):
            rightmost_pointer = struct.unpack(">I", page_bytes[header_offset + 8 : header_offset + 12])[0]
            cell_ptr_start = header_offset + 12
        else:
            rightmost_pointer = None
            cell_ptr_start = header_offset + 8

        cell_pointers: List[int] = []
        for i in range(cell_count):
            ptr_offset = cell_ptr_start + (2 * i)
            ptr = struct.unpack(">H", page_bytes[ptr_offset : ptr_offset + 2])[0]
            cell_pointers.append(ptr)

        cells: List[Dict[str, Any]] = []
        for ptr in cell_pointers:
            if page_type == cls.LEAF_TABLE:
                payload_size, n1 = read_varint(page_bytes, ptr)
                rowid, n2 = read_varint(page_bytes, ptr + n1)
                payload = page_bytes[ptr + n1 + n2 : ptr + n1 + n2 + payload_size]
                cells.append({
                    "payload_size": payload_size,
                    "rowid": rowid,
                    "payload": payload,
                })
            elif page_type == cls.INTERIOR_TABLE:
                left_child = struct.unpack(">I", page_bytes[ptr : ptr + 4])[0]
                rowid, n = read_varint(page_bytes, ptr + 4)
                cells.append({
                    "left_child_page": left_child,
                    "rowid": rowid,
                })
            elif page_type == cls.LEAF_INDEX:
                payload_size, n1 = read_varint(page_bytes, ptr)
                payload = page_bytes[ptr + n1 : ptr + n1 + payload_size]
                cells.append({
                    "payload_size": payload_size,
                    "payload": payload,
                })
            elif page_type == cls.INTERIOR_INDEX:
                left_child = struct.unpack(">I", page_bytes[ptr : ptr + 4])[0]
                payload_size, n1 = read_varint(page_bytes, ptr + 4)
                payload = page_bytes[ptr + 4 + n1 : ptr + 4 + n1 + payload_size]
                cells.append({
                    "left_child_page": left_child,
                    "payload_size": payload_size,
                    "payload": payload,
                })

        return cls(
            page_type=page_type,
            first_freeblock=first_freeblock,
            cell_count=cell_count,
            cell_content_offset=cell_content_offset,
            rightmost_pointer=rightmost_pointer,
            cell_pointers=cell_pointers,
            cells=cells,
            page_number=page_number,
        )
