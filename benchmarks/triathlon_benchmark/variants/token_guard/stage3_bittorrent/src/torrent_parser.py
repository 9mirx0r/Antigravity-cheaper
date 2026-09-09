from __future__ import annotations
from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import List

from .bencode import bencode_decode, bencode_encode


@dataclass
class TorrentMetadata:
    announce: str
    name: str
    length: int
    piece_length: int
    pieces: List[bytes]
    info_hash: bytes


def parse_torrent_file(file_path: str | Path) -> TorrentMetadata:
    path = Path(file_path)
    raw = path.read_bytes()
    meta = bencode_decode(raw)

    raw_announce = meta.get(b"announce", b"")
    announce = raw_announce.decode("utf-8", errors="replace") if isinstance(raw_announce, bytes) else str(raw_announce)

    info = meta[b"info"]
    raw_name = info.get(b"name", b"")
    name = raw_name.decode("utf-8", errors="replace") if isinstance(raw_name, bytes) else str(raw_name)

    length = int(info[b"length"])
    piece_length = int(info[b"piece length"])

    raw_pieces = info[b"pieces"]
    pieces = [raw_pieces[i : i + 20] for i in range(0, len(raw_pieces), 20)]

    # Compute 20-byte SHA-1 digest of canonical bencoded info dict
    info_encoded = bencode_encode(info)
    info_hash = hashlib.sha1(info_encoded).digest()

    return TorrentMetadata(
        announce=announce,
        name=name,
        length=length,
        piece_length=piece_length,
        pieces=pieces,
        info_hash=info_hash,
    )
