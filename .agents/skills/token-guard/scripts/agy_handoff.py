#!/usr/bin/env python3
"""
agy_handoff.py - Deterministic Local Handoff Router & Circuit Breaker
Part of the token-guard skill for Google Antigravity.

Implements the Local Threshold Routing pattern discovered in Astra-cheap V2:
1. Evaluates artifact size locally (0 LLM calls).
2. If size <= full_limit (~24KB / ~6k tokens), selects route 'full' to eliminate
   costly expansion rounds (+97% tokens in multi-turn delegation).
3. If size > full_limit, verifies recovery attempts. If recovery_attempts >= 2
   on the same unchanged SHA-256 fingerprint, trips the Circuit Breaker to halt
   infinite packing loops and forces a focused direct read.
4. Otherwise, generates a bounded view pack with optional literal focus.
"""

import argparse
import hashlib
import json
import os
import sys
from typing import Any, Dict, Optional

# Import local sibling agy_pack if available
try:
    from . import agy_pack
except ImportError:
    import agy_pack


DEFAULT_FULL_LIMIT = 24000   # ~6,000 tokens
DEFAULT_PACK_LIMIT = 3500    # ~875 tokens


class CircuitBreakerError(Exception):
    """Raised when recovery attempts threshold is exceeded on unchanged source."""
    pass


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def prepare_handoff(
    source_path: str,
    full_limit: int = DEFAULT_FULL_LIMIT,
    pack_limit: int = DEFAULT_PACK_LIMIT,
    recovery_attempts: int = 0,
    previous_sha256: Optional[str] = None,
    task: Optional[str] = None,
    acceptance: Optional[str] = None,
    contains: Optional[str] = None,
    context: int = 2,
    root_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Deterministically decides whether to deliver full content or a bounded pack.
    
    Returns a dictionary with routing metadata and payload.
    Raises CircuitBreakerError if 2+ recoveries occurred on unchanged source.
    """
    abs_path = os.path.abspath(source_path)
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"Source file not found: {source_path}")
    if os.path.isdir(abs_path):
        raise IsADirectoryError(f"Source must be a file, directory given: {source_path}")

    with open(abs_path, "rb") as f:
        raw_bytes = f.read()

    current_sha256 = compute_sha256(raw_bytes)
    content_str = raw_bytes.decode("utf-8", errors="replace")
    total_chars = len(content_str)
    total_lines = content_str.count("\n") + (1 if content_str and not content_str.endswith("\n") else 0)

    # 1. Circuit breaker check
    if (
        previous_sha256 is not None
        and previous_sha256.lower() == current_sha256.lower()
        and recovery_attempts >= 2
    ):
        raise CircuitBreakerError(
            f"Circuit breaker tripped: {recovery_attempts} consecutive recovery attempts "
            f"on unchanged source (sha256={current_sha256[:12]}...). "
            "Repeated packing blocked to prevent expansion token spiral (+97%). "
            "Switch to direct focused inspection (e.g. view_file with specific lines or contains filter)."
        )

    # 2. Threshold routing decision
    if total_chars <= full_limit:
        return {
            "route": "full",
            "source": os.path.relpath(abs_path, root_dir) if root_dir else abs_path,
            "sha256": current_sha256,
            "total_bytes": len(raw_bytes),
            "total_chars": total_chars,
            "total_lines": total_lines,
            "content": content_str,
            "task": task,
            "acceptance": acceptance,
            "reason": f"Content ({total_chars} chars) is under full threshold ({full_limit} chars). 1-turn direct delivery."
        }
    else:
        pack_data = agy_pack.pack_file(
            source_path=abs_path,
            max_chars=pack_limit,
            root_dir=root_dir,
            contains=contains,
            context=context,
        )
        return {
            "route": "pack",
            "source": os.path.relpath(abs_path, root_dir) if root_dir else abs_path,
            "sha256": current_sha256,
            "total_bytes": len(raw_bytes),
            "total_chars": total_chars,
            "total_lines": total_lines,
            "pack": pack_data,
            "task": task,
            "acceptance": acceptance,
            "reason": f"Content ({total_chars} chars) exceeds full threshold ({full_limit} chars). Bounded view generated."
        }


def main():
    parser = argparse.ArgumentParser(description="Deterministic local handoff router and circuit breaker.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prep_parser = subparsers.add_parser("prepare", help="Prepare an artifact handoff packet")
    prep_parser.add_argument("--source", "-s", required=True, help="Path to artifact file")
    prep_parser.add_argument("--full-limit", type=int, default=DEFAULT_FULL_LIMIT, help="Max chars for full route")
    prep_parser.add_argument("--pack-limit", type=int, default=DEFAULT_PACK_LIMIT, help="Max chars for pack route")
    prep_parser.add_argument("--recovery-attempts", type=int, default=0, help="Prior recovery attempts on this source")
    prep_parser.add_argument("--previous-sha", type=str, default=None, help="SHA256 from prior attempt")
    prep_parser.add_argument("--task", type=str, default=None, help="Explicit task description")
    prep_parser.add_argument("--acceptance", type=str, default=None, help="Acceptance criteria")
    prep_parser.add_argument("--contains", type=str, default=None, help="Literal substring filter for packed view")
    prep_parser.add_argument("--context", type=int, default=2, help="Lines of context around literal matches")
    prep_parser.add_argument("--root", type=str, default=".", help="Root security boundary")
    prep_parser.add_argument("--out", "-o", type=str, default=None, help="Output JSON path (default stdout)")

    args = parser.parse_args()

    if args.command == "prepare":
        try:
            result = prepare_handoff(
                source_path=args.source,
                full_limit=args.full_limit,
                pack_limit=args.pack_limit,
                recovery_attempts=args.recovery_attempts,
                previous_sha256=args.previous_sha,
                task=args.task,
                acceptance=args.acceptance,
                contains=args.contains,
                context=args.context,
                root_dir=args.root,
            )
            output_json = json.dumps(result, indent=2)
            if args.out:
                with open(args.out, "w", encoding="utf-8") as f:
                    f.write(output_json)
                print(f"Handoff packet written to: {args.out} (route: {result['route']})")
            else:
                print(output_json)
            sys.exit(0)
        except CircuitBreakerError as e:
            sys.stderr.write(f"ERROR [CircuitBreaker]: {e}\n")
            sys.exit(2)
        except Exception as e:
            sys.stderr.write(f"ERROR: {e}\n")
            sys.exit(1)


if __name__ == "__main__":
    main()
