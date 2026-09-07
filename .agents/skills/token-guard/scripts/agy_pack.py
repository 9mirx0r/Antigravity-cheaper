#!/usr/bin/env python3
"""Token Guard Pack & Expand Tool.

Provides bounded views of voluminous logs, stack traces, and source files.
'pack': Prioritizes deduplicated failure patterns, tail lines, head lines,
and diagnostics within a character budget (default 4000). Includes 1-based
line numbers, 'clipped' flag, sha256 hash, metadata, and 'complete' flag.
'expand': Safely extracts a line range from the original source only after
validating SHA-256 integrity against pack.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

DEFAULT_FAILURE_REGEX = r"(?i)\b(fail\w*|error\w*|except\w*|traceback|assert\w*|fatal|panic|critical)\b"
DEFAULT_DIAG_REGEX = r"(?i)\b(warn|warning|syntax|hint|note|diagnostic|caused by|at\s+[\w\.\/\\-]+:\d+)\b"


def compute_sha256_bytes(data: bytes) -> str:
    """Compute sha256 hex digest for bytes."""
    return hashlib.sha256(data).hexdigest()


def pack_file(
    source_path: str | Path,
    root_dir: Optional[str | Path] = None,
    max_chars: int = 4000,
    failure_pattern: str = DEFAULT_FAILURE_REGEX,
    contains: Optional[str] = None,
    context: int = 2,
) -> Dict[str, Any]:
    """Pack a file into a bounded representation respecting priorities and budget."""
    source_resolved = Path(source_path).resolve()
    if root_dir is not None:
        root_resolved = Path(root_dir).resolve()
        try:
            rel_source = source_resolved.relative_to(root_resolved)
        except ValueError:
            raise ValueError(
                f"Source file '{source_resolved}' must reside within root '{root_resolved}'"
            )
    else:
        root_resolved = Path.cwd().resolve()
        try:
            rel_source = source_resolved.relative_to(root_resolved)
        except ValueError:
            rel_source = source_resolved

    if not source_resolved.is_file():
        raise FileNotFoundError(f"Source file not found: {source_resolved}")

    raw_bytes = source_resolved.read_bytes()
    file_sha256 = compute_sha256_bytes(raw_bytes)
    content = raw_bytes.decode("utf-8", errors="replace")

    raw_lines = content.splitlines()
    total_lines = len(raw_lines)
    total_chars = len(content)

    failure_re = re.compile(failure_pattern)
    diag_re = re.compile(DEFAULT_DIAG_REGEX)

    # Check if the entire file fits comfortably within budget
    if total_chars <= max_chars:
        lines_data = [
            {"line": idx, "content": line}
            for idx, line in enumerate(raw_lines, start=1)
        ]
        formatted = "\n".join(f"{item['line']}: {item['content']}" for item in lines_data)
        return {
            "version": 1,
            "source": str(rel_source).replace("\\", "/"),
            "root": str(root_resolved).replace("\\", "/"),
            "sha256": file_sha256,
            "complete": True,
            "clipped": False,
            "max_chars": max_chars,
            "metadata": {
                "total_lines": total_lines,
                "total_chars": total_chars,
                "selected_lines_count": total_lines,
                "failures_count": 0,
                "head_lines_count": min(5, total_lines),
                "tail_lines_count": min(10, total_lines),
            },
            "lines": lines_data,
            "formatted_text": formatted,
        }

    # If exceeding budget: prioritize contains matches, failures, tail, head, diagnostics
    priority_contains: List[int] = []
    priority_contains_context: List[int] = []
    if contains:
        for idx, line in enumerate(raw_lines, start=1):
            if contains in line:
                priority_contains.append(idx)
        for c_idx in priority_contains:
            for offset in range(-context, context + 1):
                ctx_line = c_idx + offset
                if 1 <= ctx_line <= total_lines and ctx_line not in priority_contains and ctx_line not in priority_contains_context:
                    priority_contains_context.append(ctx_line)

    seen_failure_texts: Set[str] = set()
    priority_failures: List[int] = []
    priority_diagnostics: List[int] = []

    for idx, line in enumerate(raw_lines, start=1):
        if failure_re.search(line):
            norm = line.strip()
            if norm not in seen_failure_texts:
                seen_failure_texts.add(norm)
                priority_failures.append(idx)
        elif diag_re.search(line):
            priority_diagnostics.append(idx)

    head_count = min(5, total_lines)
    priority_head = list(range(1, head_count + 1))

    tail_count = min(10, total_lines)
    priority_tail = list(range(max(1, total_lines - tail_count + 1), total_lines + 1))

    # Priority allocation
    # 0. Contains exact matches and their context (if requested)
    # 1. Deduplicated failures
    # 2. Tail (last 10 lines)
    # 3. Head (first 5 lines)
    # 4. Diagnostics
    selected_set: Set[int] = set()
    current_chars = 0

    def try_add(line_idx: int) -> bool:
        nonlocal current_chars
        if line_idx in selected_set or line_idx < 1 or line_idx > total_lines:
            return True
        line_len = len(raw_lines[line_idx - 1]) + 1
        # Reserve some margin for line number prefixes and elision markers (~150 chars)
        if current_chars + line_len > (max_chars - 150) and len(selected_set) > 0:
            return False
        selected_set.add(line_idx)
        current_chars += line_len
        return True

    # 0. Add contains matches and context
    for idx in priority_contains:
        if not try_add(idx):
            break
    for idx in priority_contains_context:
        if not try_add(idx):
            break

    # 1. Add failures
    for idx in priority_failures:
        if not try_add(idx):
            break

    # 2. Add tail
    for idx in priority_tail:
        if not try_add(idx):
            break

    # 3. Add head
    for idx in priority_head:
        if not try_add(idx):
            break

    # 4. Add diagnostics around failures (context frames)
    for idx in priority_failures:
        if not try_add(idx - 1):
            break
        if not try_add(idx + 1):
            break

    # 5. Add general diagnostics
    for idx in priority_diagnostics:
        if not try_add(idx):
            break

    sorted_lines = sorted(selected_set)
    lines_data = [
        {"line": idx, "content": raw_lines[idx - 1]}
        for idx in sorted_lines
    ]

    # Build formatted text with elision notices
    formatted_parts: List[str] = []
    prev_line = 0
    for item in lines_data:
        cur_line = item["line"]
        if prev_line > 0 and cur_line > prev_line + 1:
            omitted = cur_line - prev_line - 1
            formatted_parts.append(f"... [{omitted} lines omitted (L{prev_line + 1}-L{cur_line - 1})] ...")
        formatted_parts.append(f"{cur_line}: {item['content']}")
        prev_line = cur_line

    if sorted_lines and sorted_lines[-1] < total_lines:
        omitted_end = total_lines - sorted_lines[-1]
        formatted_parts.append(f"... [{omitted_end} trailing lines omitted] ...")

    formatted_text = "\n".join(formatted_parts)

    return {
        "version": 1,
        "source": str(rel_source).replace("\\", "/"),
        "root": str(root_resolved).replace("\\", "/"),
        "sha256": file_sha256,
        "complete": False,
        "clipped": True,
        "max_chars": max_chars,
        "metadata": {
            "total_lines": total_lines,
            "total_chars": total_chars,
            "selected_lines_count": len(sorted_lines),
            "failures_count": len(seen_failure_texts),
            "head_lines_count": len([i for i in sorted_lines if i <= 5]),
            "tail_lines_count": len([i for i in sorted_lines if i >= total_lines - 9]),
            "contains": contains,
            "context": context if contains else 0,
            "contains_matches_count": len(priority_contains) if contains else 0,
        },
        "lines": lines_data,
        "formatted_text": formatted_text,
    }


def expand_pack(
    pack_data_or_path: str | Path | Dict[str, Any],
    start_line: int,
    end_line: int,
    source_override: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """Extract a range of lines from original source after validating SHA-256 integrity."""
    if isinstance(pack_data_or_path, (str, Path)):
        pack_path = Path(pack_data_or_path)
        if not pack_path.is_file():
            raise FileNotFoundError(f"Pack file not found: {pack_path}")
        pack_json = json.loads(pack_path.read_text(encoding="utf-8"))
    else:
        pack_json = pack_data_or_path

    recorded_sha256 = pack_json.get("sha256")
    if not recorded_sha256:
        raise ValueError("Pack data missing 'sha256' field")

    if source_override:
        target_path = Path(source_override).resolve()
    else:
        root_dir = Path(pack_json["root"])
        rel_source = Path(pack_json["source"])
        target_path = (root_dir / rel_source).resolve()

    if not target_path.is_file():
        raise FileNotFoundError(f"Original source file not found: {target_path}")

    raw_bytes = target_path.read_bytes()
    current_sha256 = compute_sha256_bytes(raw_bytes)

    if current_sha256 != recorded_sha256:
        raise ValueError(
            f"Integrity check failed! SHA-256 mismatch for {target_path}.\n"
            f"Recorded in pack: {recorded_sha256}\n"
            f"Current on disk:  {current_sha256}\n"
            f"File has been modified since pack generation."
        )

    content = raw_bytes.decode("utf-8", errors="replace")
    all_lines = content.splitlines()
    total_lines = len(all_lines)

    start_clamped = max(1, start_line)
    end_clamped = min(total_lines, end_line)

    if start_clamped > end_clamped:
        extracted = []
    else:
        extracted = [
            {"line": lno, "content": all_lines[lno - 1]}
            for lno in range(start_clamped, end_clamped + 1)
        ]

    formatted = "\n".join(f"{item['line']}: {item['content']}" for item in extracted)

    return {
        "source": str(target_path).replace("\\", "/"),
        "sha256": current_sha256,
        "start_line": start_clamped,
        "end_line": end_clamped,
        "total_lines": total_lines,
        "lines": extracted,
        "formatted_text": formatted,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Token Guard Pack & Expand - Context bounded view and verified line range expansion"
    )
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to run")

    # pack subcommand
    p_pack = subparsers.add_parser("pack", help="Pack a file into bounded representation")
    p_pack.add_argument("--source", "-s", required=True, help="Path to source file")
    p_pack.add_argument("--root", "-r", default=None, help="Explicit root directory (default current dir)")
    p_pack.add_argument("--max-chars", "-m", type=int, default=4000, help="Max character budget (default 4000)")
    p_pack.add_argument("--failure-pattern", default=DEFAULT_FAILURE_REGEX, help="Regex pattern for failures")
    p_pack.add_argument("--contains", "-c", default=None, help="Literal substring filter for priority lines")
    p_pack.add_argument("--context", type=int, default=2, help="Lines of context around literal matches (default 2)")
    p_pack.add_argument("--out", "-o", help="Output pack JSON file path (default stdout)")

    # expand subcommand
    p_expand = subparsers.add_parser("expand", help="Expand a line range verifying source sha256")
    p_expand.add_argument("--pack", "-p", required=True, help="Path to pack.json")
    p_expand.add_argument("--start", type=int, required=True, help="1-based start line")
    p_expand.add_argument("--end", type=int, required=True, help="1-based end line")
    p_expand.add_argument("--source", help="Optional source file path override")
    p_expand.add_argument("--out", "-o", help="Output file path (default stdout)")
    p_expand.add_argument("--json", action="store_true", help="Output JSON instead of formatted text")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    try:
        if args.command == "pack":
            packed = pack_file(
                source_path=args.source,
                root_dir=args.root,
                max_chars=args.max_chars,
                failure_pattern=args.failure_pattern,
                contains=args.contains,
                context=args.context,
            )
            json_str = json.dumps(packed, indent=2)
            if args.out:
                Path(args.out).write_text(json_str, encoding="utf-8")
            else:
                print(json_str)
            return 0

        elif args.command == "expand":
            expanded = expand_pack(
                pack_data_or_path=args.pack,
                start_line=args.start,
                end_line=args.end,
                source_override=args.source,
            )
            if args.json:
                out_content = json.dumps(expanded, indent=2)
            else:
                out_content = expanded["formatted_text"]

            if args.out:
                Path(args.out).write_text(out_content, encoding="utf-8")
            else:
                print(out_content)
            return 0

    except Exception as exc:
        sys.stderr.write(f"Error: {exc}\n")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
