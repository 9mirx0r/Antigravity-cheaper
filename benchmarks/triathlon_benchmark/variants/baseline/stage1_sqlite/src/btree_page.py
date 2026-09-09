"""SQLite B-Tree Page Parser."""

from __future__ import annotations
import struct
from typing import Any, Dict, List, Optional
from src.varint import read_varint


PAGE_TYPE_INTERIOR_INDEX = 0x02
PAGE_TYPE_INTERIOR_TABLE = 0x05
PAGE_TYPE_LEAF_INDEX = 0x0A
PAGE_TYPE_LEAF_TABLE = 0x0D


class BTreePage:
    """Represents and parses a single SQLite B-tree page."""

    def __init__(
        self,
        page_data: bytes,
        page_number: int = 1,
        page_size: int = 4096,
        reserved_space: int = 0,
    ) -> None:
        self.page_data = page_data
        self.page_number = page_number
        self.page_size = page_size
        self.reserved_space = reserved_space

        header_offset = 100 if page_number == 1 else 0
        self.header_offset = header_offset

        self.page_type: int = page_data[header_offset]
        self.first_freeblock: int = struct.unpack(
            ">H", page_data[header_offset + 1 : header_offset + 3]
        )[0]
        self.cell_count: int = struct.unpack(
            ">H", page_data[header_offset + 3 : header_offset + 5]
        )[0]
        raw_cell_content_offset = struct.unpack(
            ">H", page_data[header_offset + 5 : header_offset + 7]
        )[0]
        self.cell_content_offset: int = (
            65536 if raw_cell_content_offset == 0 else raw_cell_content_offset
        )
        self.fragmented_free_bytes: int = page_data[header_offset + 7]

        if self.page_type in (PAGE_TYPE_INTERIOR_INDEX, PAGE_TYPE_INTERIOR_TABLE):
            self.rightmost_pointer: Optional[int] = struct.unpack(
                ">I", page_data[header_offset + 8 : header_offset + 12]
            )[0]
            header_size = 12
        else:
            self.rightmost_pointer = None
            header_size = 8

        self.header_size = header_size
        cell_ptr_start = header_offset + header_size
        self.cell_pointers: List[int] = [
            struct.unpack(
                ">H",
                page_data[cell_ptr_start + i * 2 : cell_ptr_start + (i + 1) * 2],
            )[0]
            for i in range(self.cell_count)
        ]

        self.cells: List[Dict[str, Any]] = self._parse_cells()

    def _parse_cells(self) -> List[Dict[str, Any]]:
        cells: List[Dict[str, Any]] = []
        for cell_ptr in self.cell_pointers:
            if self.page_type == PAGE_TYPE_LEAF_TABLE:
                payload_size, n1 = read_varint(self.page_data, cell_ptr)
                rowid, n2 = read_varint(self.page_data, cell_ptr + n1)
                payload_start = cell_ptr + n1 + n2
                payload = self.page_data[payload_start : payload_start + payload_size]
                cells.append({
                    "payload_size": payload_size,
                    "rowid": rowid,
                    "payload": payload,
                })
            elif self.page_type == PAGE_TYPE_INTERIOR_TABLE:
                left_child = struct.unpack(
                    ">I", self.page_data[cell_ptr : cell_ptr + 4]
                )[0]
                rowid, _ = read_varint(self.page_data, cell_ptr + 4)
                cells.append({
                    "left_child": left_child,
                    "rowid": rowid,
                })
            elif self.page_type == PAGE_TYPE_LEAF_INDEX:
                payload_size, n1 = read_varint(self.page_data, cell_ptr)
                payload_start = cell_ptr + n1
                payload = self.page_data[payload_start : payload_start + payload_size]
                cells.append({
                    "payload_size": payload_size,
                    "payload": payload,
                })
            elif self.page_type == PAGE_TYPE_INTERIOR_INDEX:
                left_child = struct.unpack(
                    ">I", self.page_data[cell_ptr : cell_ptr + 4]
                )[0]
                payload_size, n1 = read_varint(self.page_data, cell_ptr + 4)
                payload_start = cell_ptr + 4 + n1
                payload = self.page_data[payload_start : payload_start + payload_size]
                cells.append({
                    "left_child": left_child,
                    "payload_size": payload_size,
                    "payload": payload,
                })
        return cells
