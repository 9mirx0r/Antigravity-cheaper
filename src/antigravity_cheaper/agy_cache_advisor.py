#!/usr/bin/env python3
"""Gemini Context Caching Advisor & Prefix Profiler.

Calculates the token volume of frozen prompt prefix invariants (system instructions,
persistent memories, and PageRank RepoMap) and determines mathematical eligibility
for Gemini's 90% prompt context caching discount.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

GEMINI_CACHE_THRESHOLD = 2048  # Minimum prefix tokens required to trigger discount
CACHE_DISCOUNT_PERCENT = 90.0  # Gemini 2.5/3.x cached token discount (10% of base rate)


def estimate_tokens(text: str) -> int:
    """Accurately estimates tokens using standard 4-char heuristic with whitespace weighting."""
    if not text:
        return 0
    words = len(text.split())
    chars = len(text)
    # Balanced heuristic: max of word-count * 1.33 or ceil(chars / 4.0)
    return max(int(words * 1.33), (chars + 3) // 4)


def scan_invariant_files(root_dir: Path) -> list[tuple[str, int]]:
    """Scans and estimates token volume of candidate invariant / system prompt files."""
    candidates = [
        "INVARIANTS.md",
        "SYSTEM_INSTRUCTIONS.md",
        "README.md",
        ".agents/skills/token-guard/SKILL.md",
    ]
    results = []
    for rel_path in candidates:
        p = root_dir / rel_path
        if p.exists() and p.is_file():
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
                toks = estimate_tokens(text)
                results.append((rel_path, toks))
            except Exception:
                pass

    # Also scan .agents/rules if present
    rules_dir = root_dir / ".agents" / "rules"
    if rules_dir.exists() and rules_dir.is_dir():
        for rf in rules_dir.glob("*.md"):
            try:
                toks = estimate_tokens(rf.read_text(encoding="utf-8", errors="replace"))
                results.append((str(rf.relative_to(root_dir)), toks))
            except Exception:
                pass

    return results


def get_memory_token_count(root_dir: Path) -> tuple[int, int]:
    """Queries .local/memory.db for total entries and token volume."""
    db_path = root_dir / ".local" / "memory.db"
    if not db_path.exists():
        return 0, 0

    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute("SELECT content FROM memories")
        rows = cur.fetchall()
        conn.close()
        total_toks = sum(estimate_tokens(r[0]) for r in rows if r[0])
        return len(rows), total_toks
    except Exception:
        return 0, 0


def analyze_prefix(root_dir: Path, repomap_budget: int = 1200) -> dict[str, Any]:
    """Runs a complete context caching analysis over the workspace."""
    invariants = scan_invariant_files(root_dir)
    invariants_tokens = sum(tok for _, tok in invariants)

    memory_entries, memory_tokens = get_memory_token_count(root_dir)

    total_prefix_tokens = invariants_tokens + memory_tokens + repomap_budget
    is_eligible = total_prefix_tokens >= GEMINI_CACHE_THRESHOLD
    deficit = max(0, GEMINI_CACHE_THRESHOLD - total_prefix_tokens)

    # 10-turn cost projection with baseline ($0.075 / 1M)
    base_rate_per_million = 0.075
    uncached_10turn_cost = 10 * (total_prefix_tokens / 1_000_000) * base_rate_per_million
    cached_10turn_cost = (1 * (total_prefix_tokens / 1_000_000) * base_rate_per_million) + (
        9 * (total_prefix_tokens / 1_000_000) * (base_rate_per_million * 0.10)
    )
    dollar_savings = max(0.0, uncached_10turn_cost - cached_10turn_cost)

    return {
        "root_dir": str(root_dir),
        "threshold": GEMINI_CACHE_THRESHOLD,
        "total_prefix_tokens": total_prefix_tokens,
        "is_eligible": is_eligible,
        "deficit": deficit,
        "discount_percent": CACHE_DISCOUNT_PERCENT,
        "components": {
            "invariants_tokens": invariants_tokens,
            "invariants_files": invariants,
            "memory_entries": memory_entries,
            "memory_tokens": memory_tokens,
            "repomap_budget": repomap_budget,
        },
        "projections": {
            "uncached_10turn_cost": round(uncached_10turn_cost, 6),
            "cached_10turn_cost": round(cached_10turn_cost, 6),
            "dollar_savings_10turns": round(dollar_savings, 6),
        },
    }


def format_card(analysis: dict[str, Any]) -> str:
    """Formats analysis dictionary into a high-visibility terminal card."""
    tot = analysis["total_prefix_tokens"]
    thresh = analysis["threshold"]
    eligible = analysis["is_eligible"]
    pct = min(100, int((tot / thresh) * 100))
    bar_len = 25
    filled = min(bar_len, int((tot / thresh) * bar_len))
    bar = "=" * filled + "-" * (bar_len - filled)

    lines = []
    lines.append("=" * 64)
    lines.append("  GEMINI CONTEXT CACHING PROFILER & ADVISOR (v1.0.0)")
    lines.append("=" * 64)
    lines.append(f"  Target Threshold:       {thresh:,} tokens (Gemini 2.5 / 3.x Flash/Pro)")
    lines.append(f"  Current Prefix Volume:  {tot:,} tokens [{bar}] {pct}%")

    if eligible:
        lines.append("  Cache Status:           [ACTIVE] ELIGIBLE FOR 90% DISCOUNT")
    else:
        lines.append(f"  Cache Status:           [BELOW THRESHOLD] Needs {analysis['deficit']} more tokens")

    lines.append("-" * 64)
    lines.append("  Breakdown:")
    lines.append(f"    - PageRank RepoMap:    {analysis['components']['repomap_budget']:,} tokens (budget)")
    lines.append(f"    - Persistent Memory:    {analysis['components']['memory_tokens']:,} tokens ({analysis['components']['memory_entries']} records)")
    lines.append(f"    - System Invariants:    {analysis['components']['invariants_tokens']:,} tokens")
    for fpath, ftoks in analysis["components"]["invariants_files"]:
        lines.append(f"        * {fpath}: {ftoks:,} tokens")

    lines.append("-" * 64)
    lines.append("  10-Turn Financial Projection (Gemini 3.x):")
    lines.append(f"    - Without Caching:     ${analysis['projections']['uncached_10turn_cost']:.6f}")
    lines.append(f"    - With Prefix Lock:    ${analysis['projections']['cached_10turn_cost']:.6f}")
    if eligible:
        lines.append(f"    - Net Session Savings: ${analysis['projections']['dollar_savings_10turns']:.6f} (-81.0% effective)")
    else:
        lines.append(f"    - Potential Savings:   ${analysis['projections']['dollar_savings_10turns']:.6f} (once threshold is met)")

    lines.append("=" * 64)
    if eligible:
        lines.append("  Recommendation:")
        lines.append("    Your frozen prefix qualifies for Gemini Context Caching.")
        lines.append("    Lock the Merkle prefix with:  agy lock --root . --verify")
    else:
        lines.append("  Recommendation:")
        lines.append(f"    Add {analysis['deficit']} tokens of invariant rules or increase RepoMap budget:")
        lines.append("    Example:  agy map --root . --budget 1500")
        lines.append("    Example:  agy memory save --family invariants --key rules --content '...'")
    lines.append("=" * 64)

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Analyze context caching eligibility and financial savings for Gemini.",
        prog="agy cache",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Workspace root directory (default: current directory).",
    )
    parser.add_argument(
        "--budget",
        type=int,
        default=1200,
        help="RepoMap token budget to include in prefix (default: 1200).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON analysis instead of terminal card.",
    )

    args = parser.parse_args(argv)
    analysis = analyze_prefix(args.root.resolve(), repomap_budget=args.budget)

    if args.json:
        print(json.dumps(analysis, indent=2))
    else:
        print(format_card(analysis))
    return 0


if __name__ == "__main__":
    sys.exit(main())
