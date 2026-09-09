"""BitTorrent Piece Manager and Block Assembler."""

from __future__ import annotations
import hashlib
from pathlib import Path
from typing import Dict, Tuple, Union

from src.torrent_parser import TorrentMetadata


class PieceManager:
    """Manages downloading, assembling, SHA-1 verification, and disk persistence of torrent pieces."""

    def __init__(self, metadata: TorrentMetadata) -> None:
        self.metadata = metadata
        self.verified_pieces: Dict[int, bytes] = {}

    def assemble_and_verify_piece(
        self, piece_index: int, blocks: Dict[int, bytes]
    ) -> Tuple[bool, bytes]:
        """Assembles blocks ordered by offset and verifies against piece SHA-1 hash."""
        sorted_offsets = sorted(blocks.keys())
        piece_data = b"".join(blocks[offset] for offset in sorted_offsets)

        expected_hash = self.metadata.pieces[piece_index]
        computed_hash = hashlib.sha1(piece_data).digest()

        is_valid = computed_hash == expected_hash
        if is_valid:
            self.verified_pieces[piece_index] = piece_data

        return is_valid, piece_data

    def save_file(self, output_path: Union[str, Path]) -> None:
        """Writes verified pieces sequentially to output file."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            for i in range(len(self.metadata.pieces)):
                f.write(self.verified_pieces.get(i, b""))
