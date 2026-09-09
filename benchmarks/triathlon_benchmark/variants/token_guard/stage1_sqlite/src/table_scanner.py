from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .db_header import DatabaseHeader
from .btree_page import BTreePage
from .record_decoder import RecordDecoder


def parse_columns_from_sql(sql: str) -> List[Tuple[str, bool]]:
    """Parses column names and detects INTEGER PRIMARY KEY from CREATE TABLE SQL."""
    if not sql:
        return []
    open_idx = sql.find("(")
    close_idx = sql.rfind(")")
    if open_idx == -1 or close_idx == -1:
        return []
    cols_def = sql[open_idx + 1 : close_idx]

    parts: List[str] = []
    current: List[str] = []
    depth = 0
    for char in cols_def:
        if char == "(":
            depth += 1
            current.append(char)
        elif char == ")":
            depth -= 1
            current.append(char)
        elif char == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if current:
        parts.append("".join(current).strip())

    columns: List[Tuple[str, bool]] = []
    for part in parts:
        part_clean = part.strip()
        if not part_clean:
            continue
        tokens = part_clean.split()
        first_token = tokens[0].strip("`\"'[]")
        if first_token.upper() in ("CONSTRAINT", "PRIMARY", "FOREIGN", "CHECK", "UNIQUE"):
            continue

        upper_part = part_clean.upper()
        is_int_pk = False
        if "INTEGER" in upper_part and "PRIMARY" in upper_part and "KEY" in upper_part and "DESC" not in upper_part:
            is_int_pk = True

        columns.append((first_token, is_int_pk))
    return columns


class SQLiteEngine:
    """Pure-Python SQLite 3 database file reader and table scanner."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.file = open(self.db_path, "rb")
        header_bytes = self.file.read(100)
        self.header = DatabaseHeader.parse(header_bytes)

    def close(self):
        if self.file and not self.file.closed:
            self.file.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _get_page(self, page_number: int) -> BTreePage:
        offset = (page_number - 1) * self.header.page_size
        self.file.seek(offset)
        page_bytes = self.file.read(self.header.page_size)
        return BTreePage.parse(page_bytes, page_number)

    def _traverse_table(self, page_number: int) -> List[Tuple[int, bytes]]:
        page = self._get_page(page_number)
        if page.page_type == BTreePage.LEAF_TABLE:
            return [(cell["rowid"], cell["payload"]) for cell in page.cells]
        elif page.page_type == BTreePage.INTERIOR_TABLE:
            rows: List[Tuple[int, bytes]] = []
            for cell in page.cells:
                rows.extend(self._traverse_table(cell["left_child_page"]))
            if page.rightmost_pointer:
                rows.extend(self._traverse_table(page.rightmost_pointer))
            return rows
        return []

    def get_tables(self) -> List[Dict[str, Any]]:
        """Returns metadata for all tables in sqlite_master/sqlite_schema."""
        schema_rows = self._traverse_table(1)
        tables: List[Dict[str, Any]] = []
        for _, payload in schema_rows:
            rec = RecordDecoder.decode_record(payload)
            if len(rec) >= 5 and rec[0] == "table":
                tables.append({
                    "type": rec[0],
                    "name": rec[1],
                    "tbl_name": rec[2],
                    "rootpage": rec[3],
                    "sql": rec[4],
                })
        return tables

    def scan_table(
        self,
        table_name: str,
        columns: Optional[List[str]] = None,
        where_col: Optional[str] = None,
        where_val: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """Scans a table and returns matching row records as dictionaries."""
        tables = self.get_tables()
        table_meta = None
        for t in tables:
            if t["tbl_name"] == table_name or t["name"] == table_name:
                table_meta = t
                break

        if not table_meta:
            raise ValueError(f"Table not found: {table_name}")

        rootpage = table_meta["rootpage"]
        sql = table_meta.get("sql", "")
        col_info = parse_columns_from_sql(sql)

        rows = self._traverse_table(rootpage)
        results: List[Dict[str, Any]] = []

        for rowid, payload in rows:
            decoded = RecordDecoder.decode_record(payload)
            row_dict: Dict[str, Any] = {}
            for i, (col_name, is_int_pk) in enumerate(col_info):
                val = decoded[i] if i < len(decoded) else None
                if is_int_pk and val is None:
                    val = rowid
                row_dict[col_name] = val

            if where_col is not None:
                if row_dict.get(where_col) != where_val:
                    continue

            if columns is not None:
                filtered_row = {c: row_dict[c] for c in columns if c in row_dict}
                results.append(filtered_row)
            else:
                results.append(row_dict)

        return results
