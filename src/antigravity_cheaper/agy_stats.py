#!/usr/bin/env python3
"""Unified Workspace & Telemetry Dashboard for Antigravity-Cheaper.

Collects and visualizes workspace symbol coverage, persistent SQLite memory health,
Merkle prefix lock status, and financial token telemetry into a single dashboard.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

from . import __version__
from . import agy_cache_advisor
from . import agy_ledger
from . import agy_prefix_lock


def collect_stats(root_dir: Path) -> dict[str, Any]:
    """Collects comprehensive health and usage statistics across the workspace."""
    # 1. Source files & Symbols
    source_files = []
    for ext in ("*.py", "*.js", "*.ts", "*.jsx", "*.tsx"):
        for p in root_dir.glob(f"**/{ext}"):
            # ignore hidden, venv, pycache
            parts = p.parts
            if any(part.startswith(".") or part in ("venv", ".venv", "__pycache__", "build", "dist") for part in parts):
                continue
            source_files.append(p)

    total_files = len(source_files)

    # 2. SQLite Persistent Memory
    mem_db = root_dir / ".local" / "memory.db"
    memory_stats = {"exists": False, "count": 0, "size_bytes": 0, "topics": {}}
    if mem_db.exists():
        try:
            memory_stats["exists"] = True
            memory_stats["size_bytes"] = mem_db.stat().st_size
            conn = sqlite3.connect(str(mem_db))
            cur = conn.cursor()
            cur.execute("SELECT topic, COUNT(*) FROM memories GROUP BY topic")
            for topic, count in cur.fetchall():
                memory_stats["topics"][topic] = count
            cur.execute("SELECT COUNT(*) FROM memories")
            row = cur.fetchone()
            memory_stats["count"] = row[0] if row else 0
            conn.close()
        except Exception:
            pass

    # 3. Prefix Lock Manifest
    manifest_path = root_dir / ".prefix_lock.json"
    prefix_stats = {"locked": False, "merkle_root": None, "file_count": 0}
    if manifest_path.exists():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                mdata = json.load(f)
                prefix_stats["locked"] = True
                prefix_stats["merkle_root"] = mdata.get("merkle_root")
                prefix_stats["file_count"] = len(mdata.get("files", []))
        except Exception:
            pass

    # 4. Cache advisor check
    cache_analysis = agy_cache_advisor.analyze_prefix(root_dir)

    # 5. Ledger Telemetry
    ledger_candidates = [
        root_dir / ".local" / "ledger.jsonl",
        root_dir / "benchmarks" / "data" / "benchmark_usage.jsonl",
    ]
    ledger_summary = None
    ledger_file_used = None
    for lc in ledger_candidates:
        if lc.exists():
            try:
                ledger_summary = agy_ledger.summarize_ledger(lc)
                ledger_file_used = str(lc.relative_to(root_dir))
                break
            except Exception:
                pass

    return {
        "version": __version__,
        "root": str(root_dir),
        "source_code": {
            "total_files": total_files,
        },
        "memory": memory_stats,
        "prefix_lock": prefix_stats,
        "cache": {
            "total_prefix_tokens": cache_analysis["total_prefix_tokens"],
            "is_eligible": cache_analysis["is_eligible"],
            "discount_percent": cache_analysis["discount_percent"],
        },
        "ledger": {
            "file": ledger_file_used,
            "summary": ledger_summary,
        },
    }


def format_dashboard(stats: dict[str, Any]) -> str:
    """Renders a clean ASCII dashboard from stats dictionary."""
    lines = []
    lines.append("=" * 66)
    lines.append(f"  ANTIGRAVITY-CHEAPER WORKSPACE DASHBOARD (v{stats['version']})")
    lines.append("=" * 66)
    lines.append(f"  Workspace:        {stats['root']}")
    lines.append(f"  Source Modules:   {stats['source_code']['total_files']} files detected (Python, JS, TS)")

    # Memory
    mem = stats["memory"]
    lines.append("-" * 66)
    if mem["exists"]:
        kb = mem["size_bytes"] / 1024.0
        topics_str = ", ".join(f"{k}: {v}" for k, v in mem["topics"].items()) if mem["topics"] else "none"
        lines.append(f"  SQLite Memory:    [ACTIVE] {mem['count']} records ({kb:.1f} KB in .local/memory.db)")
        lines.append(f"                    Topics: {topics_str}")
    else:
        lines.append("  SQLite Memory:    [EMPTY] No records in .local/memory.db (run 'agy memory')")

    # Prefix Lock & Cache
    lock = stats["prefix_lock"]
    cache = stats["cache"]
    lines.append("-" * 66)
    if lock["locked"]:
        m_short = lock["merkle_root"][:16] + "..." if lock["merkle_root"] else "unknown"
        lines.append(f"  Merkle Prefix:    [LOCKED] SHA-256: {m_short} ({lock['file_count']} files)")
    else:
        lines.append("  Merkle Prefix:    [UNLOCKED] Manifest .prefix_lock.json not sealed")

    c_status = "[ELIGIBLE] 90% discount" if cache["is_eligible"] else "[BELOW 2,048t THRESHOLD]"
    lines.append(f"  Gemini Caching:   {c_status} (Prefix: {cache['total_prefix_tokens']:,} tokens)")

    # Ledger
    led = stats["ledger"]
    lines.append("-" * 66)
    if led["summary"]:
        s = led["summary"]
        tot_tok = s.get("total_tokens", 0)
        cache_hit = s.get("cache_hit_rate_pct", 0.0)
        tot_cost = s.get("total_cost_usd", 0.0)
        runs = s.get("total_runs", 0)
        acc_runs = s.get("accepted_runs", 0)
        cpao = s.get("cost_per_accepted_outcome", None)
        cpao_str = f"${cpao:.4f}" if cpao is not None else "N/A"

        lines.append(f"  Telemetry Ledger: {led['file']} ({runs} runs logged, {acc_runs} accepted)")
        lines.append(f"    - Total Tokens: {tot_tok:,}")
        lines.append(f"    - Cache Hit:    {cache_hit:.1f}%")
        lines.append(f"    - Total Cost:   ${tot_cost:.4f}")
        lines.append(f"    - CPAO:         {cpao_str} per accepted outcome")
    else:
        lines.append("  Telemetry Ledger: [NO DATA] Run benchmarks or 'agy ledger' to record telemetry")

    lines.append("=" * 66)
    lines.append("  Quick Actions:")
    lines.append("    agy map --budget 1000   | Generate PageRank symbol map")
    lines.append("    agy cache               | Analyze Gemini 90% cache eligibility")
    lines.append("    agy setup               | Register FastMCP in Antigravity/Cursor")
    lines.append("=" * 66)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Unified workspace and telemetry statistics dashboard.",
        prog="agy stats",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Workspace root directory (default: current directory).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON statistics.",
    )

    args = parser.parse_args(argv)
    stats = collect_stats(args.root.resolve())

    if args.json:
        print(json.dumps(stats, indent=2))
    else:
        print(format_dashboard(stats))
    return 0


if __name__ == "__main__":
    sys.exit(main())
