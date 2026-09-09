"""SQLite Table Scanner and Query Engine."""

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.db_header import DatabaseHeader
from src.btree_page import BTreePage, PAGE_TYPE_INTERIOR_TABLE, PAGE_TYPE_LEAF_TABLE
from src.record_decoder import RecordDecoder


class SQLiteEngine:
    """Pure-Python SQLite 3 file format reader and table scanner."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self.file = open(self.db_path, "rb")
        self.file.seek(0)
        header_bytes = self.file.read(100)
        self.header = DatabaseHeader.parse(header_bytes)
        self.page_size = self.header.page_size
        self.reserved_space = self.header.reserved_space

    def __del__(self) -> None:
        try:
            if hasattr(self, "file") and not self.file.closed:
                self.file.close()
        except Exception:
            pass

    def read_page(self, page_number: int) -> BTreePage:
        self.file.seek((page_number - 1) * self.page_size)
        page_data = self.file.read(self.page_size)
        return BTreePage(
            page_data=page_data,
            page_number=page_number,
            page_size=self.page_size,
            reserved_space=self.reserved_space,
        )

    def _get_leaf_pages(self, page_number: int) -> List[BTreePage]:
        page = self.read_page(page_number)
        if page.page_type == PAGE_TYPE_LEAF_TABLE:
            return [page]
        elif page.page_type == PAGE_TYPE_INTERIOR_TABLE:
            leaf_pages: List[BTreePage] = []
            for cell in page.cells:
                leaf_pages.extend(self._get_leaf_pages(cell["left_child"]))
            if page.rightmost_pointer:
                leaf_pages.extend(self._get_leaf_pages(page.rightmost_pointer))
            return leaf_pages
        return []

    def get_tables(self) -> List[Dict[str, Any]]:
        """Scans root schema table (sqlite_schema on page 1) to find all tables."""
        leaf_pages = self._get_leaf_pages(1)
        tables: List[Dict[str, Any]] = []

        for page in leaf_pages:
            for cell in page.cells:
                payload = cell.get("payload", b"")
                rec = RecordDecoder.decode_record(payload)
                if len(rec) >= 5:
                    entry_type = rec[0]
                    name = rec[1]
                    tbl_name = rec[2]
                    rootpage = rec[3]
                    sql = rec[4]
                    if entry_type == "table":
                        tables.append({
                            "type": entry_type,
                            "name": name,
                            "tbl_name": tbl_name,
                            "rootpage": rootpage,
                            "sql": sql,
                        })
        return tables

    def _parse_columns(self, sql: Optional[str]) -> Tuple[List[str], Optional[str]]:
        if not sql:
            return [], None

        start = sql.find("(")
        end = sql.rfind(")")
        if start == -1 or end == -1:
            return [], None

        content = sql[start + 1 : end]
        parts: List[str] = []
        current: List[str] = []
        paren_depth = 0
        in_quote = False
        quote_char = ""

        for char in content:
            if char in ("'", '"', "`"):
                if not in_quote:
                    in_quote = True
                    quote_char = char
                elif quote_char == char:
                    in_quote = False
            elif char == "(" and not in_quote:
                paren_depth += 1
            elif char == ")" and not in_quote:
                paren_depth -= 1
            elif char == "," and paren_depth == 0 and not in_quote:
                parts.append("".join(current).strip())
                current = []
                continue
            current.append(char)
        if current:
            parts.append("".join(current).strip())

        columns: List[str] = []
        int_pk_col: Optional[str] = None

        for part in parts:
            tokens = part.split()
            if not tokens:
                continue
            first_upper = tokens[0].upper()
            if first_upper in ("PRIMARY", "FOREIGN", "CONSTRAINT", "UNIQUE", "CHECK"):
                continue

            col_name = tokens[0].strip("\"'`[]")
            columns.append(col_name)

            tokens_upper = [t.upper() for t in tokens]
            if (
                "INTEGER" in tokens_upper
                and "PRIMARY" in tokens_upper
                and "KEY" in tokens_upper
            ):
                int_pk_col = col_name

        return columns, int_pk_col

    def scan_table(
        self,
        table_name: str,
        columns: Optional[List[str]] = None,
        where_col: Optional[str] = None,
        where_val: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """Scans rows from table_name with optional column selection and where filter."""
        tables = self.get_tables()
        matched_table = None
        for t in tables:
            if t["tbl_name"] == table_name or t["name"] == table_name:
                matched_table = t
                break

        if not matched_table:
            raise ValueError(f"Table '{table_name}' not found in database schema")

        rootpage: int = matched_table["rootpage"]
        sql: Optional[str] = matched_table.get("sql")
        col_names, int_pk_col = self._parse_columns(sql)

        leaf_pages = self._get_leaf_pages(rootpage)
        results: List[Dict[str, Any]] = []

        for page in leaf_pages:
            for cell in page.cells:
                payload = cell.get("payload", b"")
                rowid = cell.get("rowid")
                values = RecordDecoder.decode_record(payload)

                row_dict: Dict[str, Any] = {}
                for idx, col in enumerate(col_names):
                    val = values[idx] if idx < len(values) else None
                    if col == int_pk_col and val is None:
                        val = rowid
                    row_dict[col] = val

                if where_col is not None:
                    if row_dict.get(where_col) != where_val:
                        continue

                if columns is not None:
                    row_dict = {k: row_dict[k] for k in columns if k in row_dict}

                results.append(row_dict)

        return results
