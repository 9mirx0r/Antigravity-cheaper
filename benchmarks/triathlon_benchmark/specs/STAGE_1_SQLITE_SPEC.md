# Stage 1 Specification: Build Your Own SQLite (Pure Binary Engine)

## Objective
Implement a pure-Python SQLite 3 file format reader and table scanner capable of directly reading, navigating, and executing queries on real `.db` files **WITHOUT using `import sqlite3` or any external database library**.

## Architecture & Required Modules (`stage1_sqlite/src/`)

### 1. `db_header.py`
- Class `DatabaseHeader`:
  - `parse(header_bytes: bytes) -> DatabaseHeader`
  - Validates 16-byte magic string: `b"SQLite format 3\x00"`
  - Extracts:
    - `page_size`: 2-byte integer at offset 16 (note: if value is 1, page size is 65536)
    - `write_version`: offset 18
    - `read_version`: offset 19
    - `reserved_space`: offset 20
    - `schema_cookie`: 4-byte integer at offset 40

### 2. `varint.py`
- Functions:
  - `read_varint(buffer: bytes, offset: int = 0) -> Tuple[int, int]`: Reads a variable-length integer (1 to 9 bytes). Returns `(value, bytes_consumed)`. Each byte contributes 7 bits (high bit indicates more bytes), except the 9th byte which contributes all 8 bits.
  - `write_varint(value: int) -> bytes`: Encodes integer into SQLite varint format.

### 3. `btree_page.py`
- Class `BTreePage`:
  - Parse page header:
    - `page_type`: 1 byte (`0x0d` for leaf table b-tree, `0x05` for interior table b-tree, `0x0a` for leaf index, `0x02` for interior index)
    - `first_freeblock`: 2 bytes
    - `cell_count`: 2 bytes
    - `cell_content_offset`: 2 bytes (0 denotes 65536)
    - `rightmost_pointer`: 4 bytes (present only on interior pages `0x05` and `0x02`)
  - Read array of 2-byte cell pointers immediately following the page header (accounting for the 100-byte DB header if page 1).
  - Extract cells from page buffer.

### 4. `record_decoder.py`
- Class `RecordDecoder`:
  - `decode_record(payload_bytes: bytes) -> List[Any]`:
    - Parses record header length (varint).
    - Parses serial types for each column (array of varints).
    - Serial type mappings:
      - 0: `None` (NULL)
      - 1: 8-bit signed integer
      - 2: 16-bit signed integer (big-endian)
      - 3: 24-bit signed integer (big-endian)
      - 4: 32-bit signed integer (big-endian)
      - 5: 48-bit signed integer (big-endian)
      - 6: 64-bit signed integer (big-endian)
      - 7: 64-bit IEEE 754 float (big-endian)
      - 8: constant `0` (integer)
      - 9: constant `1` (integer)
      - N >= 12, N is even: BLOB of length `(N - 12) / 2`
      - N >= 13, N is odd: TEXT (UTF-8 string) of length `(N - 13) / 2`
    - Extracts corresponding values from body.

### 5. `table_scanner.py`
- Class `SQLiteEngine`:
  - `__init__(db_path: str)`: Opens file, parses header and page 1.
  - `get_tables() -> List[Dict[str, Any]]`: Scans root schema table (`sqlite_schema` / `sqlite_master` on page 1) to find all table names and root pages (`tbl_name`, `rootpage`, `sql`).
  - `scan_table(table_name: str, columns: Optional[List[str]] = None, where_col: Optional[str] = None, where_val: Optional[Any] = None) -> List[Dict[str, Any]]`:
    - Resolves `rootpage` of table.
    - Recursively traverses interior B-tree pages down to leaf pages (`0x0d`).
    - Decodes rows and returns list of dictionaries matching query criteria.
