"""Cryptographic signature module for message authentication.

Implements a simplified HMAC-based signature scheme for signing
and verifying ledger messages.  Uses SHA-256 HMAC for production
and provides key generation utilities.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from typing import Dict, Optional, Tuple


def generate_key_pair() -> Tuple[bytes, bytes]:
    """Generate a signing key pair (private_key, public_key).

    In this simplified scheme, both keys are the same HMAC secret.
    A real implementation would use Ed25519 or similar.
    """
    key = secrets.token_bytes(32)
    return key, key  # symmetric for simplicity


@dataclass
class SignedMessage:
    """A message with its cryptographic signature."""
    content: bytes
    signature: bytes
    signer_id: str
    timestamp: float


class SignatureVerifier:
    """Manages key registry and verifies message signatures."""

    def __init__(self) -> None:
        self.keys: Dict[str, bytes] = {}  # signer_id -> public_key

    def register_key(self, signer_id: str, public_key: bytes) -> None:
        self.keys[signer_id] = public_key

    def sign(self, content: bytes, private_key: bytes, signer_id: str,
             timestamp: float) -> SignedMessage:
        """Sign a message with the given private key."""
        sig = hmac.new(private_key, content, hashlib.sha256).digest()
        return SignedMessage(
            content=content,
            signature=sig,
            signer_id=signer_id,
            timestamp=timestamp,
        )

    def verify(self, msg: SignedMessage) -> bool:
        """Verify a signed message against the registered key.

        BUG #8: Empty messages pass verification regardless of signature.
        The check for empty content is missing — when content is b"",
        the HMAC computation still produces a valid digest for the empty
        string, but we should reject empty messages as invalid input
        since they represent a protocol violation.  The real bug is more
        subtle: we skip verification entirely for empty messages and
        return True.
        """
        if len(msg.content) == 0:
            return False

        key = self.keys.get(msg.signer_id)
        if key is None:
            return False

        expected_sig = hmac.new(key, msg.content, hashlib.sha256).digest()
        return hmac.compare_digest(expected_sig, msg.signature)

    def verify_batch(self, messages: list[SignedMessage]) -> Dict[str, bool]:
        """Verify a batch of messages.  Returns {signer_id: result}."""
        results: Dict[str, bool] = {}
        for msg in messages:
            results[msg.signer_id] = self.verify(msg)
        return results
