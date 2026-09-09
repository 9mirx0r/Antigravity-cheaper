# Stage 3 Specification: Build Your Own BitTorrent (Wire Protocol & Block Assembler)

## Objective
Implement a functional BitTorrent P2P client capable of parsing `.torrent` metainfo files, establishing the binary 68-byte handshake, implementing the peer wire state machine, downloading 16KB blocks in pipelined fashion, and validating the cryptographic SHA-1 hashes of each piece.

## Architecture & Required Modules (`stage3_bittorrent/src/`)

### 1. `bencode.py`
- Functions:
  - `bencode_decode(data: bytes) -> Any`:
    - Integer: `b"i42e"` -> `42`, negative `b"i-15e"` -> `-15`
    - Byte String: `b"4:spam"` -> `b"spam"`
    - List: `b"l4:spami42ee"` -> `[b"spam", 42]`
    - Dictionary: `b"d3:bar4:spam3:fooi42ee"` -> `{b"bar": b"spam", b"foo": 42}` (keys sorted lexicographically)
  - `bencode_encode(data: Any) -> bytes`:
    - Converts Python ints, bytes/strings, lists, and dicts back into standard Bencoded byte strings.

### 2. `torrent_parser.py`
- Class `TorrentMetadata`:
  - `announce`: str (Tracker URL)
  - `name`: str
  - `length`: int (Total file size)
  - `piece_length`: int (Size of each piece)
  - `pieces`: List[bytes] (List of 20-byte SHA-1 hashes)
  - `info_hash`: bytes (20-byte SHA-1 digest of the raw Bencoded `info` dictionary)
- Function:
  - `parse_torrent_file(file_path: str | Path) -> TorrentMetadata`

### 3. `peer_wire.py`
- Constants:
  - `PROTOCOL_STRING = b"BitTorrent protocol"`
  - Message IDs:
    - 0: `CHOKE`
    - 1: `UNCHOKE`
    - 2: `INTERESTED`
    - 3: `NOT_INTERESTED`
    - 4: `HAVE`
    - 5: `BITFIELD`
    - 6: `REQUEST`
    - 7: `PIECE`
- Functions:
  - `create_handshake(info_hash: bytes, peer_id: bytes) -> bytes`:
    - Exactly 68 bytes: `\x13` + `BitTorrent protocol` (19 bytes) + 8 zero reserved bytes + 20-byte `info_hash` + 20-byte `peer_id`.
  - `parse_handshake(raw: bytes) -> Tuple[bytes, bytes]`:
    - Validates length and protocol string, returns `(info_hash, peer_id)`.
  - `create_message(msg_id: int, payload: bytes = b"") -> bytes`:
    - 4-byte big-endian length prefix + 1-byte message ID + payload.
  - `create_request(piece_index: int, block_offset: int, block_length: int = 16384) -> bytes`:
    - Creates a `REQUEST` message (ID 6).

### 4. `piece_manager.py`
- Class `PieceManager`:
  - `__init__(metadata: TorrentMetadata)`: Tracks piece states, block requests, downloaded blocks, and verified pieces.
  - `assemble_and_verify_piece(piece_index: int, blocks: Dict[int, bytes]) -> Tuple[bool, bytes]`:
    - Assembles contiguous blocks by offset.
    - Computes SHA-1 hash of the assembled piece data.
    - Compares with expected 20-byte SHA-1 hash from metadata.
    - Returns `(is_valid, piece_data)`.
  - `save_file(output_path: str | Path) -> None`:
    - Writes all verified pieces sequentially into the output file.
