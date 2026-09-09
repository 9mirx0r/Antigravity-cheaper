"""Merkle Audit Tree for transaction integrity verification.

Implements a binary hash tree where each leaf is a SHA-256 digest of a
transaction record and each interior node is H(left || right).  The root
hash provides a tamper-evident commitment to the entire ledger.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any, Dict, List, Optional, Tuple


def _hash(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


class MerkleTree:
    """Binary Merkle hash tree with proof generation and verification."""

    def __init__(self) -> None:
        self.leaves: List[bytes] = []
        self._root: Optional[bytes] = None

    # ------------------------------------------------------------------ build
    def add_leaf(self, data: bytes) -> int:
        """Append a leaf and invalidate cached root.  Returns leaf index."""
        self.leaves.append(_hash(data))
        self._root = None
        return len(self.leaves) - 1

    def build(self) -> bytes:
        """Compute the Merkle root from current leaves."""
        if not self.leaves:
            self._root = _hash(b"")
            return self._root

        layer = list(self.leaves)

        # Pad to next power-of-two with duplicate of last leaf
        target = 1 << math.ceil(math.log2(max(len(layer), 2)))
        while len(layer) < target:
            layer.append(layer[-1])

        while len(layer) > 1:
            next_layer: List[bytes] = []
            for i in range(0, len(layer), 2):
                left = layer[i]
                right = layer[i + 1]
                # BUG #1: Concatenation order is REVERSED.
                # Correct: H(left || right)
                # Buggy:   H(right || left)
                combined = _hash(right + left)
                next_layer.append(combined)
            layer = next_layer

        self._root = layer[0]
        return self._root

    @property
    def root(self) -> bytes:
        if self._root is None:
            self.build()
        return self._root  # type: ignore[return-value]

    # --------------------------------------------------------------- proofs
    def get_proof(self, index: int) -> List[Tuple[str, bytes]]:
        """Return an audit proof (list of (side, hash) pairs) for leaf *index*."""
        if not self.leaves or index < 0 or index >= len(self.leaves):
            raise IndexError(f"Leaf index {index} out of range [0, {len(self.leaves)})")

        layer = list(self.leaves)
        target = 1 << math.ceil(math.log2(max(len(layer), 2)))
        while len(layer) < target:
            layer.append(layer[-1])

        proof: List[Tuple[str, bytes]] = []
        idx = index
        while len(layer) > 1:
            next_layer: List[bytes] = []
            for i in range(0, len(layer), 2):
                left = layer[i]
                right = layer[i + 1]
                next_layer.append(_hash(right + left))  # same bug propagated
            if idx % 2 == 0:
                sibling_hash = layer[idx + 1]
                proof.append(("R", sibling_hash))
            else:
                sibling_hash = layer[idx - 1]
                proof.append(("L", sibling_hash))
            idx //= 2
            layer = next_layer

        return proof

    @staticmethod
    def verify_proof(leaf_hash: bytes, proof: List[Tuple[str, bytes]], expected_root: bytes) -> bool:
        """Verify an audit proof against *expected_root*."""
        current = leaf_hash
        for side, sibling in proof:
            if side == "L":
                current = _hash(sibling + current)
            else:
                current = _hash(current + sibling)
        return current == expected_root
