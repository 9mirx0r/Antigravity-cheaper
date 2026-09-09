from __future__ import annotations
import hashlib
from pathlib import Path
from typing import Dict, Optional, Tuple

from .torrent_parser import TorrentMetadata


class PieceManager:
    """Manages BitTorrent piece assembly, verification, and file persistence."""

    def __init__(self, metadata: TorrentMetadata):
        self.metadata = metadata
        self.total_pieces = len(metadata.pieces)
        self.verified_pieces: Dict[int, bytes] = {}

    def assemble_and_verify_piece(
        self,
        piece_index: int,
        blocks: Dict[int, bytes],
    ) -> Tuple[bool, bytes]:
        """Assembles blocks in offset order, validates SHA-1, and caches valid pieces."""
        if piece_index < 0 or piece_index >= self.total_pieces:
            raise IndexError(f"Piece index {piece_index} out of range (0-{self.total_pieces - 1})")

        sorted_offsets = sorted(blocks.keys())
        piece_data = b"".join(blocks[offset] for offset in sorted_offsets)

        expected_hash = self.metadata.pieces[piece_index]
        actual_hash = hashlib.sha1(piece_data).digest()

        is_valid = (actual_hash == expected_hash)
        if is_valid:
            self.verified_pieces[piece_index] = piece_data

        return is_valid, piece_data

    def save_file(self, output_path: str | Path) -> None:
        """Writes all verified pieces sequentially into the output file."""
        full_data = bytearray()
        for i in range(self.total_pieces):
            if i not in self.verified_pieces:
                raise ValueError(f"Cannot save: piece {i} has not been verified")
            full_data.extend(self.verified_pieces[i])

        target_bytes = bytes(full_data[: self.metadata.length])
        Path(output_path).write_bytes(target_bytes)
