#!/usr/bin/env python3
"""Token Guard Capsule Tool.

Manages dependency capsules with 'seal' and 'status'.
'seal': Records a claim, individual files (sha256 and existence), directory
trees (sorted deterministic tree hash), kind ('static' or 'live'), and ttl_seconds.
'status': Recalculates hashes.
  - If modified: returns 'stale' with changed paths (exit code 1).
  - If expired: returns 'stale' with expiration reason (exit code 1).
  - If kind is 'live': returns 'refresh_required' (exit code 1).
  - If unchanged and valid: returns 'dependencies_match' (exit code 0).
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


def compute_file_sha256(path: Path) -> str | None:
    """Compute sha256 for a file if it exists."""
    if not path.is_file():
        return None
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def compute_tree_hash(tree_path: Path) -> tuple[str | None, int]:
    """Recursively compute deterministic sha256 hash of a directory tree.

    Sorts relative paths lexicographically, hashes each file, and combines
    into an overall tree hash.
    """
    if not tree_path.is_dir():
        return None, 0

    entries: list[tuple[str, str]] = []
    file_count = 0

    for root, dirnames, filenames in os.walk(tree_path):
        dirnames.sort()
        filenames.sort()
        for filename in filenames:
            file_full = Path(root) / filename
            rel_path = file_full.relative_to(tree_path).as_posix()
            file_hash = compute_file_sha256(file_full)
            if file_hash is not None:
                entries.append((rel_path, file_hash))
                file_count += 1

    entries.sort(key=lambda x: x[0])
    combined_hasher = hashlib.sha256()
    for rel_path, file_hash in entries:
        combined_hasher.update(f"{rel_path}:{file_hash}\n".encode())

    return combined_hasher.hexdigest(), file_count


def seal_capsule(
    claim: str,
    files: list[str] | None = None,
    trees: list[str] | None = None,
    kind: str = "static",
    ttl_seconds: float | None = None,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Seal dependencies into a capsule dictionary."""
    base = Path(base_dir).resolve() if base_dir else Path.cwd()
    norm_kind = kind.strip().lower()
    if norm_kind not in ("static", "live"):
        raise ValueError(f"Invalid capsule kind: '{kind}'. Must be 'static' or 'live'.")

    files_record: dict[str, dict[str, Any]] = {}
    if files:
        for f_str in files:
            f_path = Path(f_str)
            if not f_path.is_absolute():
                f_path = (base / f_path).resolve()
            try:
                rel_display = f_path.relative_to(base).as_posix()
            except ValueError:
                rel_display = str(f_path).replace("\\", "/")

            if f_path.is_file():
                h = compute_file_sha256(f_path)
                files_record[rel_display] = {
                    "exists": True,
                    "sha256": h,
                    "size": f_path.stat().st_size,
                    "absolute_path": str(f_path).replace("\\", "/"),
                }
            else:
                files_record[rel_display] = {
                    "exists": False,
                    "sha256": None,
                    "size": 0,
                    "absolute_path": str(f_path).replace("\\", "/"),
                }

    trees_record: dict[str, dict[str, Any]] = {}
    if trees:
        for t_str in trees:
            t_path = Path(t_str)
            if not t_path.is_absolute():
                t_path = (base / t_path).resolve()
            try:
                rel_display = t_path.relative_to(base).as_posix()
            except ValueError:
                rel_display = str(t_path).replace("\\", "/")

            if t_path.is_dir():
                tree_h, count = compute_tree_hash(t_path)
                trees_record[rel_display] = {
                    "exists": True,
                    "tree_hash": tree_h,
                    "file_count": count,
                    "absolute_path": str(t_path).replace("\\", "/"),
                }
            else:
                trees_record[rel_display] = {
                    "exists": False,
                    "tree_hash": None,
                    "file_count": 0,
                    "absolute_path": str(t_path).replace("\\", "/"),
                }

    now_ts = time.time()
    now_iso = datetime.datetime.fromtimestamp(now_ts, tz=datetime.timezone.utc).isoformat()

    return {
        "version": 1,
        "claim": claim,
        "kind": norm_kind,
        "created_at": now_ts,
        "created_at_iso": now_iso,
        "ttl_seconds": ttl_seconds,
        "base_dir": str(base).replace("\\", "/"),
        "files": files_record,
        "trees": trees_record,
    }


def check_status(
    capsule_data_or_path: str | Path | dict[str, Any],
    base_dir_override: str | Path | None = None,
) -> dict[str, Any]:
    """Check the status of a sealed capsule.

    Returns dictionary with:
      - status: 'dependencies_match' | 'stale' | 'refresh_required'
      - exit_code: 0 for dependencies_match, 1 for stale / refresh_required
      - changed_paths: list of paths that modified or disappeared
      - reason: textual explanation
    """
    if isinstance(capsule_data_or_path, (str, Path)):
        capsule_path = Path(capsule_data_or_path)
        if not capsule_path.is_file():
            raise FileNotFoundError(f"Capsule file not found: {capsule_path}")
        capsule = json.loads(capsule_path.read_text(encoding="utf-8"))
    else:
        capsule = capsule_data_or_path

    kind = capsule.get("kind", "static").lower()
    base_dir = Path(base_dir_override).resolve() if base_dir_override else Path(capsule.get("base_dir", "."))

    # 1. Check live kind: live kind always requires dynamic refresh
    if kind == "live":
        return {
            "status": "refresh_required",
            "exit_code": 1,
            "claim": capsule.get("claim", ""),
            "kind": kind,
            "changed_paths": [],
            "reason": "Capsule kind is 'live'; dynamic refresh is always required.",
        }

    # 2. Check TTL expiration
    ttl = capsule.get("ttl_seconds")
    created_at = capsule.get("created_at", 0)
    now = time.time()
    if ttl is not None and (now - created_at) > ttl:
        elapsed = now - created_at
        return {
            "status": "stale",
            "exit_code": 1,
            "claim": capsule.get("claim", ""),
            "kind": kind,
            "changed_paths": [],
            "reason": f"Capsule expired: {elapsed:.1f}s elapsed > TTL of {ttl}s.",
        }

    changed_paths: list[str] = []

    # 3. Check individual files
    files_record = capsule.get("files", {})
    for rel_path, rec in files_record.items():
        abs_path_str = rec.get("absolute_path")
        if abs_path_str and Path(abs_path_str).is_file():
            target_file = Path(abs_path_str)
        else:
            target_file = (base_dir / rel_path).resolve()

        if not rec.get("exists", False):
            # Sealed as non-existent: if it now exists, it changed
            if target_file.is_file():
                changed_paths.append(rel_path)
        else:
            # Sealed as existing
            if not target_file.is_file():
                changed_paths.append(rel_path)
            else:
                cur_hash = compute_file_sha256(target_file)
                if cur_hash != rec.get("sha256"):
                    changed_paths.append(rel_path)

    # 4. Check directory trees
    trees_record = capsule.get("trees", {})
    for rel_path, rec in trees_record.items():
        abs_path_str = rec.get("absolute_path")
        if abs_path_str and Path(abs_path_str).is_dir():
            target_dir = Path(abs_path_str)
        else:
            target_dir = (base_dir / rel_path).resolve()

        if not rec.get("exists", False):
            if target_dir.is_dir():
                changed_paths.append(rel_path)
        else:
            if not target_dir.is_dir():
                changed_paths.append(rel_path)
            else:
                cur_tree_hash, _ = compute_tree_hash(target_dir)
                if cur_tree_hash != rec.get("tree_hash"):
                    changed_paths.append(rel_path)

    if changed_paths:
        return {
            "status": "stale",
            "exit_code": 1,
            "claim": capsule.get("claim", ""),
            "kind": kind,
            "changed_paths": changed_paths,
            "reason": f"Dependencies modified in {len(changed_paths)} target path(s): {', '.join(changed_paths)}",
        }

    return {
        "status": "dependencies_match",
        "exit_code": 0,
        "claim": capsule.get("claim", ""),
        "kind": kind,
        "changed_paths": [],
        "reason": "All sealed dependencies match current disk hashes and TTL is valid.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Token Guard Capsule Tool - Dependency sealing and status verification"
    )
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to execute")

    # seal subcommand
    p_seal = subparsers.add_parser("seal", help="Seal files and directories into a dependency capsule")
    p_seal.add_argument("--claim", "-c", required=True, help="Assertion/claim for this dependency capsule")
    p_seal.add_argument("--file", "-f", action="append", default=[], help="File path to track (repeatable)")
    p_seal.add_argument("--tree", "-t", action="append", default=[], help="Directory tree to track (repeatable)")
    p_seal.add_argument(
        "--kind",
        "-k",
        choices=["static", "live"],
        default="static",
        help="Capsule kind ('static' or 'live', default 'static')",
    )
    p_seal.add_argument("--ttl", "--ttl-seconds", dest="ttl_seconds", type=float, help="TTL in seconds")
    p_seal.add_argument("--out", "-o", help="Path to write sealed capsule JSON (default stdout)")

    # status subcommand
    p_status = subparsers.add_parser("status", help="Check capsule verification status")
    p_status.add_argument("--capsule", "-p", required=True, help="Path to capsule JSON file")
    p_status.add_argument("--json", action="store_true", help="Output status report in JSON format")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    try:
        if args.command == "seal":
            capsule = seal_capsule(
                claim=args.claim,
                files=args.file,
                trees=args.tree,
                kind=args.kind,
                ttl_seconds=args.ttl_seconds,
            )
            capsule_json = json.dumps(capsule, indent=2)
            if args.out:
                Path(args.out).write_text(capsule_json, encoding="utf-8")
                print(f"Capsule successfully sealed to: {args.out}")
            else:
                print(capsule_json)
            return 0

        elif args.command == "status":
            res = check_status(args.capsule)
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                print(f"Status: {res['status']}")
                print(f"Claim:  {res['claim']}")
                print(f"Reason: {res['reason']}")
                if res["changed_paths"]:
                    print("Changed paths:")
                    for p in res["changed_paths"]:
                        print(f"  - {p}")
            return res["exit_code"]

    except Exception as exc:
        sys.stderr.write(f"Error: {exc}\n")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
