#!/usr/bin/env python3
"""Triathlon Benchmark Evaluator & Telemetry Compiler.

Evaluates 3 sequential engineering stages across both variants:
  1. Stage 1: Build Your Own SQLite
  2. Stage 2: Distributed Raft Consensus & 2PC
  3. Stage 3: Build Your Own BitTorrent

Computes:
  - Unit & Integration Test Pass Rates (3 suites per variant)
  - Token Consumption (Input, Cached Input, Output, Reasoning Tokens)
  - Tool Execution Efficiency
  - Wall-Clock Speedup & API Cost
  - Hextech Dark Telemetry Dashboard
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent
WORKSPACE_ROOT = ROOT.parents[1]

# Reference Pricing per 1M tokens ($ USD) for Gemini Flash & Reasoning
PRICING = {
    "input_standard": 0.15,
    "input_cached": 0.0375,
    "output_standard": 0.60,
    "reasoning_token": 0.60,
}


def calculate_cost(input_tokens: int, cached_tokens: int, output_tokens: int, reasoning_tokens: int = 0) -> float:
    uncached = max(0, input_tokens - cached_tokens)
    cost = (
        (uncached / 1_000_000 * PRICING["input_standard"])
        + (cached_tokens / 1_000_000 * PRICING["input_cached"])
        + (output_tokens / 1_000_000 * PRICING["output_standard"])
        + (reasoning_tokens / 1_000_000 * PRICING["reasoning_token"])
    )
    return round(cost, 5)


def run_stage_test(variant_dir: Path, stage_name: str, test_script: Path) -> Dict[str, Any]:
    """Runs a specific stage test against a variant directory."""
    if not test_script.is_file():
        return {"stage": stage_name, "passed": False, "tests_run": 0, "failures": 0, "errors": 1, "output": "Test file missing"}

    env = dict(os.environ)
    env["TRIATHLON_VARIANT_DIR"] = str(variant_dir)

    cmd = [sys.executable, str(test_script)]
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(cmd, cwd=str(variant_dir), capture_output=True, text=True, timeout=60, env=env)
        elapsed = round(time.perf_counter() - t0, 2)
        out = (proc.stdout or "") + (proc.stderr or "")
        passed = proc.returncode == 0
    except subprocess.TimeoutExpired:
        return {"stage": stage_name, "passed": False, "tests_run": 0, "failures": 0, "errors": 1, "output": "Timeout (60s)", "elapsed_seconds": 60.0}

    tests_run = 0
    failures = 0
    errors = 0
    for line in out.splitlines():
        if "Ran " in line and " tests in " in line:
            try:
                tests_run = int(line.split("Ran ")[1].split(" tests in ")[0])
            except ValueError:
                pass
        if "FAILED (" in line:
            if "failures=" in line:
                try:
                    failures = int(line.split("failures=")[1].split(")")[0].split(",")[0])
                except ValueError:
                    pass
            if "errors=" in line:
                try:
                    errors = int(line.split("errors=")[1].split(")")[0])
                except ValueError:
                    pass

    return {
        "stage": stage_name,
        "passed": passed,
        "tests_run": tests_run,
        "failures": failures,
        "errors": errors,
        "elapsed_seconds": elapsed,
        "output": out[-300:] if out else ""
    }


def parse_transcript_metrics(transcript_path: Optional[Path]) -> Dict[str, Any]:
    metrics = {
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "tool_calls": 0,
        "turns": 0,
        "wall_clock_seconds": 0.0,
    }
    if not transcript_path or not transcript_path.is_file():
        return metrics

    entries: List[Dict[str, Any]] = []
    timestamps: List[str] = []

    for line in transcript_path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            entries.append(entry)
            if entry.get("created_at"):
                timestamps.append(entry["created_at"])
        except Exception:
            continue

    if len(timestamps) >= 2:
        try:
            t0 = datetime.datetime.fromisoformat(timestamps[0].replace("Z", "+00:00"))
            t1 = datetime.datetime.fromisoformat(timestamps[-1].replace("Z", "+00:00"))
            metrics["wall_clock_seconds"] = round(abs((t1 - t0).total_seconds()), 2)
        except Exception:
            pass

    accumulated_chars = 0
    for entry in entries:
        etype = entry.get("type")
        content = entry.get("content") or ""
        thinking = entry.get("thinking") or ""
        calls = entry.get("tool_calls") or []

        if etype == "USER_INPUT":
            metrics["turns"] += 1
            accumulated_chars += len(content)
        elif etype == "PLANNER_RESPONSE":
            current_input = max(1, int(accumulated_chars / 3.9))
            cached = int(current_input * 0.85) if current_input > 1024 else 0
            metrics["input_tokens"] += current_input
            metrics["cached_input_tokens"] += cached

            step_reasoning = max(0, int(len(thinking) / 4.0)) if thinking else 0
            call_chars = len(json.dumps(calls)) if calls else 0
            step_output = max(1, int((len(content) + call_chars) / 4.0))

            metrics["reasoning_tokens"] += step_reasoning
            metrics["output_tokens"] += step_output
            metrics["tool_calls"] += len(calls)
            accumulated_chars += len(content) + call_chars
        elif etype == "GENERIC":
            accumulated_chars += len(content)

    return metrics


def count_variant_code(variant_dir: Path) -> Dict[str, Any]:
    total_files = 0
    total_loc = 0
    stages = ["stage1_sqlite", "stage2_consensus", "stage3_bittorrent"]
    breakdown = {}

    for stage in stages:
        stage_dir = variant_dir / stage / "src"
        st_files = 0
        st_loc = 0
        if stage_dir.is_dir():
            for p in stage_dir.rglob("*.py"):
                if p.name == "__init__.py":
                    continue
                st_files += 1
                lines = p.read_text(encoding="utf-8-sig", errors="replace").splitlines()
                st_loc += len(lines)
        breakdown[stage] = {"files": st_files, "loc": st_loc}
        total_files += st_files
        total_loc += st_loc

    return {"total_files": total_files, "total_loc": total_loc, "stages": breakdown}


def render_ascii_bar(label: str, val: float, max_val: float, bar_width: int = 35, unit: str = "") -> str:
    ratio = min(1.0, val / max_val) if max_val > 0 else 0
    filled = int(round(ratio * bar_width))
    bar = "#" * filled + "-" * (bar_width - filled)
    return f"{label:<22} [{bar}] {int(val):>10,d} {unit}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Triathlon Benchmark Evaluator")
    parser.add_argument("--baseline-dir", default=str(ROOT / "variants" / "baseline"))
    parser.add_argument("--cheaper-dir", default=str(ROOT / "variants" / "token_guard"))
    parser.add_argument("--baseline-transcript", default=None)
    parser.add_argument("--cheaper-transcript", default=None)
    parser.add_argument("--output-json", default=str(ROOT / "triathlon_summary.json"))
    parser.add_argument("--output-html", default=str(ROOT / "telemetry_dashboard.html"))

    args = parser.parse_args()

    base_dir = Path(args.baseline_dir).resolve()
    cheap_dir = Path(args.cheaper_dir).resolve()
    runners_dir = ROOT / "test_runners"

    stages = [
        ("Stage 1 (SQLite)", runners_dir / "test_stage1_sqlite.py"),
        ("Stage 2 (Consensus)", runners_dir / "test_stage2_consensus.py"),
        ("Stage 3 (BitTorrent)", runners_dir / "test_stage3_bittorrent.py"),
    ]

    print(f"Evaluating Baseline Variant in: {base_dir}")
    base_results = [run_stage_test(base_dir, st[0], st[1]) for st in stages]
    base_code = count_variant_code(base_dir)
    base_metrics = parse_transcript_metrics(Path(args.baseline_transcript) if args.baseline_transcript else None)

    print(f"Evaluating Antigravity-Cheaper Variant in: {cheap_dir}")
    cheap_results = [run_stage_test(cheap_dir, st[0], st[1]) for st in stages]
    cheap_code = count_variant_code(cheap_dir)
    cheap_metrics = parse_transcript_metrics(Path(args.cheaper_transcript) if args.cheaper_transcript else None)

    base_cost = calculate_cost(base_metrics["input_tokens"], base_metrics["cached_input_tokens"], base_metrics["output_tokens"], base_metrics["reasoning_tokens"])
    cheap_cost = calculate_cost(cheap_metrics["input_tokens"], cheap_metrics["cached_input_tokens"], cheap_metrics["output_tokens"], cheap_metrics["reasoning_tokens"])

    base_passed = all(r["passed"] for r in base_results)
    cheap_passed = all(r["passed"] for r in cheap_results)

    summary = {
        "benchmark_id": "triathlon_systems_marathon",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "stages": ["Stage 1: SQLite B-Tree", "Stage 2: Raft Consensus 2PC", "Stage 3: BitTorrent Wire"],
        "variants": {
            "baseline": {
                "passed": base_passed,
                "stages": base_results,
                "code": base_code,
                "telemetry": base_metrics,
                "cost_usd": base_cost
            },
            "token_guard": {
                "passed": cheap_passed,
                "stages": cheap_results,
                "code": cheap_code,
                "telemetry": cheap_metrics,
                "cost_usd": cheap_cost
            }
        }
    }

    Path(args.output_json).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Summary written to: {args.output_json}")

    # Render report
    max_in = max(base_metrics["input_tokens"], cheap_metrics["input_tokens"], 1)
    max_reason = max(base_metrics["reasoning_tokens"], cheap_metrics["reasoning_tokens"], 1)
    in_savings = ((base_metrics["input_tokens"] - cheap_metrics["input_tokens"]) / max_in * 100) if max_in > 1 else 0
    reason_savings = ((base_metrics["reasoning_tokens"] - cheap_metrics["reasoning_tokens"]) / max_reason * 100) if max_reason > 1 else 0

    lines = [
        "=" * 78,
        "  TRIATHLON BENCHMARK: 3-STAGE SYSTEMS MARATHON TELEMETRY LEDGER",
        "  Baseline vs. Antigravity-Cheaper (Token-Guard Guided)",
        "=" * 78,
        "",
        "1. CUMULATIVE INPUT TOKENS (Compound 3-Stage History - Lower is Better)",
        render_ascii_bar("Baseline", base_metrics["input_tokens"], max_in, unit="tok"),
        render_ascii_bar("Antigravity-Cheaper", cheap_metrics["input_tokens"], max_in, unit="tok"),
        f"   >> Net Input Token Reduction: {in_savings:+.1f}%",
        "",
        "2. REASONING TOKENS (CoT Thinking Across 3 Complex Protocols)",
        render_ascii_bar("Baseline", base_metrics["reasoning_tokens"], max_reason, unit="tok"),
        render_ascii_bar("Antigravity-Cheaper", cheap_metrics["reasoning_tokens"], max_reason, unit="tok"),
        f"   >> Reasoning Token Reduction: {reason_savings:+.1f}%",
        "",
        "3. TOOL CALL EFFICIENCY & WALL-CLOCK SPEEDUP",
        f"   Baseline:             {base_metrics['tool_calls']} calls | {base_metrics['wall_clock_seconds']}s ({base_metrics['wall_clock_seconds']/60:.1f}m)",
        f"   Antigravity-Cheaper:  {cheap_metrics['tool_calls']} calls | {cheap_metrics['wall_clock_seconds']}s ({cheap_metrics['wall_clock_seconds']/60:.1f}m)",
        "",
        "4. TEST SUITE VERIFICATION STATUS ACROSS 3 STAGES",
        f"   Baseline:             Stage 1: {'PASS' if base_results[0]['passed'] else 'FAIL'} | Stage 2: {'PASS' if base_results[1]['passed'] else 'FAIL'} | Stage 3: {'PASS' if base_results[2]['passed'] else 'FAIL'}",
        f"   Antigravity-Cheaper:  Stage 1: {'PASS' if cheap_results[0]['passed'] else 'FAIL'} | Stage 2: {'PASS' if cheap_results[1]['passed'] else 'FAIL'} | Stage 3: {'PASS' if cheap_results[2]['passed'] else 'FAIL'}",
        "",
        "=" * 78,
        f"  TRIATHLON OUTCOME: Baseline: {'PASS' if base_passed else 'FAIL'} | Antigravity-Cheaper: {'PASS' if cheap_passed else 'FAIL'}",
        "=" * 78
    ]
    print("\n" + "\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
