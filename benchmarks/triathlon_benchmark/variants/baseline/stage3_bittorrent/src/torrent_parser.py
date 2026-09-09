"""Torrent Metainfo (.torrent) File Parser."""

from __future__ import annotations
from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import List, Union

from src.bencode import bencode_decode, bencode_encode


@dataclass
class TorrentMetadata:
    announce: str
    name: str
    length: int
    piece_length: int
    pieces: List[bytes]
    info_hash: bytes


def parse_torrent_file(file_path: Union[str, Path]) -> TorrentMetadata:
    """Parses a .torrent file into TorrentMetadata."""
    path = Path(file_path)
    raw_bytes = path.read_bytes()
    decoded = bencode_decode(raw_bytes)

    info_dict = decoded[b"info"]
    info_hash = hashlib.sha1(bencode_encode(info_dict)).digest()

    announce_raw = decoded.get(b"announce", b"")
    announce = (
        announce_raw.decode("utf-8")
        if isinstance(announce_raw, bytes)
        else str(announce_raw)
    )

    name_raw = info_dict[b"name"]
    name = (
        name_raw.decode("utf-8")
        if isinstance(name_raw, bytes)
        else str(name_raw)
    )

    length = info_dict[b"length"]
    piece_length = info_dict[b"piece length"]
    pieces_raw: bytes = info_dict[b"pieces"]

    pieces: List[bytes] = [
        pieces_raw[i : i + 20] for i in range(0, len(pieces_raw), 20)
    ]

    return TorrentMetadata(
        announce=announce,
        name=name,
        length=length,
        piece_length=piece_length,
        pieces=pieces,
        info_hash=info_hash,
    )
