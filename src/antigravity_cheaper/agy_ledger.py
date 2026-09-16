#!/usr/bin/env python3
"""Token Guard Gemini Telemetry Ledger.

Records and aggregates token telemetry without persisting prompts or completions.
'record': Appends a structured telemetry event to a JSONL ledger file.
'summary': Computes aggregated metrics, cache hit rate, cost breakdown,
and 'cost_per_accepted_outcome' grouped by variant.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Reference pricing per 1,000,000 tokens (USD)
# (uncached_input, cached_input, output)
MODEL_PRICING_PER_MILLION: Dict[str, Tuple[float, float, float]] = {
    # Gemini Pro families (1.5, 2.0, 2.5, 3.x)
    "gemini-3.8-pro": (1.25, 0.3125, 5.00),
    "gemini-3.0-pro": (1.25, 0.3125, 5.00),
    "gemini-3-pro": (1.25, 0.3125, 5.00),
    "gemini-2.5-pro": (1.25, 0.3125, 5.00),
    "gemini-2.0-pro": (1.25, 0.3125, 5.00),
    "gemini-1.5-pro": (1.25, 0.3125, 5.00),
    "gemini-pro": (1.25, 0.3125, 5.00),
    # Gemini Flash families (1.5, 2.0, 2.5, 3.x)
    "gemini-3.8-flash": (0.075, 0.01875, 0.30),
    "gemini-3.0-flash": (0.075, 0.01875, 0.30),
    "gemini-3-flash": (0.075, 0.01875, 0.30),
    "gemini-2.5-flash": (0.075, 0.01875, 0.30),
    "gemini-2.0-flash": (0.075, 0.01875, 0.30),
    "gemini-1.5-flash": (0.075, 0.01875, 0.30),
    "gemini-flash": (0.075, 0.01875, 0.30),
    "gemini-flash-thinking": (0.075, 0.01875, 0.30),
    # Gemini Flash-Lite families
    "gemini-flash-lite": (0.0375, 0.009375, 0.15),
    "gemini-2.0-flash-lite": (0.0375, 0.009375, 0.15),
    "gemini-2.5-flash-lite": (0.0375, 0.009375, 0.15),
    # Default baseline pricing fallback
    "default": (1.00, 0.25, 4.00),
}


def parse_bool(val: Any) -> bool:
    """Safely parse boolean values from CLI or json."""
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if s in ("true", "1", "yes", "t", "y", "ship", "pass", "accepted"):
        return True
    if s in ("false", "0", "no", "f", "n", "rethink", "fix-first", "rejected", "failed"):
        return False
    raise ValueError(f"Cannot parse '{val}' as boolean")


def get_model_rates(model_name: str) -> Tuple[float, float, float]:
    """Retrieve pricing rates for a given model per 1M tokens."""
    norm = model_name.strip().lower()
    for key, rates in MODEL_PRICING_PER_MILLION.items():
        if key in norm:
            return rates
    return MODEL_PRICING_PER_MILLION["default"]


def calculate_record_cost(record: Dict[str, Any]) -> float:
    """Calculate the estimated USD cost of a single telemetry record."""
    rates = get_model_rates(record.get("model", "default"))
    rate_uncached, rate_cached, rate_output = rates

    input_tokens = int(record.get("input_tokens", 0))
    cached_tokens = int(record.get("cached_input_tokens", 0))
    output_tokens = int(record.get("output_tokens", 0))

    cost = (
        (input_tokens / 1_000_000.0) * rate_uncached
        + (cached_tokens / 1_000_000.0) * rate_cached
        + (output_tokens / 1_000_000.0) * rate_output
    )
    return cost


def record_telemetry(
    task_id: str,
    variant: str,
    model: str,
    effort: str,
    status: str,
    accepted: bool,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    reasoning_output_tokens: int,
    retries: int,
    elapsed_seconds: float,
    ledger_path: str | Path = "agy_ledger.jsonl",
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    """Record a telemetry event to a JSONL file without saving prompts."""
    if not timestamp:
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

    record = {
        "timestamp": timestamp,
        "task_id": task_id,
        "variant": variant,
        "model": model,
        "effort": str(effort),
        "status": status,
        "accepted": accepted,
        "input_tokens": int(input_tokens),
        "cached_input_tokens": int(cached_input_tokens),
        "output_tokens": int(output_tokens),
        "reasoning_output_tokens": int(reasoning_output_tokens),
        "retries": int(retries),
        "elapsed_seconds": round(float(elapsed_seconds), 4),
    }

    target_file = Path(ledger_path).resolve()
    target_file.parent.mkdir(parents=True, exist_ok=True)

    with target_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    return record


def load_ledger(ledger_path: str | Path) -> List[Dict[str, Any]]:
    """Load all telemetry entries from a JSONL file."""
    path = Path(ledger_path).resolve()
    if not path.is_file():
        return []

    records: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line_str = line.strip()
            if line_str:
                try:
                    records.append(json.loads(line_str))
                except json.JSONDecodeError:
                    continue
    return records


def compute_summary(
    records: List[Dict[str, Any]],
    variant_filter: Optional[str] = None,
) -> Dict[str, Any]:
    """Aggregate metrics and compute cost_per_accepted_outcome by variant."""
    if variant_filter:
        records = [r for r in records if r.get("variant") == variant_filter]

    variants: Dict[str, List[Dict[str, Any]]] = {}
    for r in records:
        v = r.get("variant", "unknown")
        variants.setdefault(v, []).append(r)

    variant_summaries: Dict[str, Any] = {}

    for v_name, v_records in variants.items():
        total_tasks = len(v_records)
        accepted_tasks = sum(1 for r in v_records if parse_bool(r.get("accepted", False)))
        acc_rate = (accepted_tasks / total_tasks) if total_tasks > 0 else 0.0

        total_input = sum(int(r.get("input_tokens", 0)) for r in v_records)
        total_cached = sum(int(r.get("cached_input_tokens", 0)) for r in v_records)
        total_output = sum(int(r.get("output_tokens", 0)) for r in v_records)
        total_reasoning = sum(int(r.get("reasoning_output_tokens", 0)) for r in v_records)
        total_all_tokens = total_input + total_cached + total_output

        total_prompt_tokens = total_input + total_cached
        cache_hit_rate = (
            (total_cached / total_prompt_tokens) if total_prompt_tokens > 0 else 0.0
        )

        total_cost = sum(calculate_record_cost(r) for r in v_records)

        cost_per_accepted = (
            (total_cost / accepted_tasks) if accepted_tasks > 0 else None
        )

        total_retries = sum(int(r.get("retries", 0)) for r in v_records)
        avg_retries = (total_retries / total_tasks) if total_tasks > 0 else 0.0

        total_elapsed = sum(float(r.get("elapsed_seconds", 0.0)) for r in v_records)
        avg_elapsed = (total_elapsed / total_tasks) if total_tasks > 0 else 0.0

        variant_summaries[v_name] = {
            "variant": v_name,
            "total_tasks": total_tasks,
            "accepted_tasks": accepted_tasks,
            "acceptance_rate": round(acc_rate, 4),
            "total_input_tokens": total_input,
            "total_cached_input_tokens": total_cached,
            "total_output_tokens": total_output,
            "total_reasoning_output_tokens": total_reasoning,
            "total_tokens": total_all_tokens,
            "cache_hit_rate": round(cache_hit_rate, 4),
            "total_cost_usd": round(total_cost, 6),
            "cost_per_accepted_outcome": (
                round(cost_per_accepted, 6) if cost_per_accepted is not None else None
            ),
            "total_retries": total_retries,
            "avg_retries": round(avg_retries, 2),
            "total_elapsed_seconds": round(total_elapsed, 2),
            "avg_elapsed_seconds": round(avg_elapsed, 2),
        }

    # Overall summary across all included records
    total_tasks_all = len(records)
    accepted_tasks_all = sum(1 for r in records if parse_bool(r.get("accepted", False)))
    all_cost = sum(calculate_record_cost(r) for r in records)
    all_input = sum(int(r.get("input_tokens", 0)) for r in records)
    all_cached = sum(int(r.get("cached_input_tokens", 0)) for r in records)
    all_output = sum(int(r.get("output_tokens", 0)) for r in records)
    all_prompt = all_input + all_cached

    overall = {
        "total_records": total_tasks_all,
        "accepted_records": accepted_tasks_all,
        "overall_acceptance_rate": (
            round(accepted_tasks_all / total_tasks_all, 4) if total_tasks_all > 0 else 0.0
        ),
        "overall_total_tokens": all_input + all_cached + all_output,
        "overall_cache_hit_rate": (
            round(all_cached / all_prompt, 4) if all_prompt > 0 else 0.0
        ),
        "overall_cost_usd": round(all_cost, 6),
        "overall_cost_per_accepted_outcome": (
            round(all_cost / accepted_tasks_all, 6) if accepted_tasks_all > 0 else None
        ),
    }

    return {
        "variants": variant_summaries,
        "overall": overall,
    }


def format_summary_table(summary: Dict[str, Any]) -> str:
    """Format human-readable summary table."""
    lines: List[str] = [
        "==========================================================================================================",
        "                                     TOKEN GUARD TELEMETRY SUMMARY",
        "==========================================================================================================",
        f"{'Variant':<18} | {'Tasks':<6} | {'Accepted':<8} | {'Acc %':<7} | {'Cache Hit':<9} | {'Total Tok':<10} | {'Cost ($)':<9} | {'Cost/Acc ($)':<12}",
        "-------------------+--------+----------+---------+-----------+------------+-----------+-------------",
    ]

    for v_name, v_data in summary["variants"].items():
        acc_pct = f"{v_data['acceptance_rate'] * 100:.1f}%"
        hit_pct = f"{v_data['cache_hit_rate'] * 100:.1f}%"
        c_acc = (
            f"${v_data['cost_per_accepted_outcome']:.4f}"
            if v_data["cost_per_accepted_outcome"] is not None
            else "N/A (0 acc)"
        )
        line = (
            f"{v_name:<18} | "
            f"{v_data['total_tasks']:<6} | "
            f"{v_data['accepted_tasks']:<8} | "
            f"{acc_pct:<7} | "
            f"{hit_pct:<9} | "
            f"{v_data['total_tokens']:<10} | "
            f"${v_data['total_cost_usd']:<8.4f} | "
            f"{c_acc:<12}"
        )
        lines.append(line)

    lines.append("==========================================================================================================")
    ov = summary["overall"]
    ov_c_acc = (
        f"${ov['overall_cost_per_accepted_outcome']:.4f}"
        if ov["overall_cost_per_accepted_outcome"] is not None
        else "N/A"
    )
    lines.append(
        f"OVERALL: {ov['total_records']} tasks ({ov['accepted_records']} accepted, {ov['overall_acceptance_rate']*100:.1f}% rate) | "
        f"Cache Hit: {ov['overall_cache_hit_rate']*100:.1f}% | "
        f"Total Cost: ${ov['overall_cost_usd']:.4f} | "
        f"Cost/Acc Outcome: {ov_c_acc}"
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Token Guard Gemini Telemetry Ledger"
    )
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to execute")

    # record subcommand
    p_record = subparsers.add_parser("record", help="Record telemetry event to JSONL")
    p_record.add_argument("--task-id", required=True, help="Unique identifier for the task/run")
    p_record.add_argument("--variant", required=True, help="Strategy/prompt variant name")
    p_record.add_argument("--model", required=True, help="Gemini model identifier")
    p_record.add_argument("--effort", required=True, help="Reasoning effort level")
    p_record.add_argument("--status", required=True, help="Status (e.g. ship, fix-first, success)")
    p_record.add_argument("--accepted", required=True, help="Whether outcome was accepted (true/false)")
    p_record.add_argument("--input-tokens", type=int, required=True, help="Uncached input tokens")
    p_record.add_argument("--cached-input-tokens", type=int, required=True, help="Cached input tokens")
    p_record.add_argument("--output-tokens", type=int, required=True, help="Total output tokens")
    p_record.add_argument("--reasoning-output-tokens", type=int, required=True, help="Reasoning tokens")
    p_record.add_argument("--retries", type=int, required=True, help="Number of retries")
    p_record.add_argument("--elapsed-seconds", type=float, required=True, help="Elapsed time in seconds")
    p_record.add_argument("--ledger", default="agy_ledger.jsonl", help="Path to JSONL ledger file")
    p_record.add_argument("--timestamp", help="Optional ISO timestamp override")

    # summary subcommand
    p_summary = subparsers.add_parser("summary", help="Aggregate metrics from JSONL ledger")
    p_summary.add_argument("--ledger", default="agy_ledger.jsonl", help="Path to JSONL ledger file")
    p_summary.add_argument("--variant", help="Filter by specific variant")
    p_summary.add_argument("--json", action="store_true", help="Output summary in JSON format")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    try:
        if args.command == "record":
            acc_val = parse_bool(args.accepted)
            rec = record_telemetry(
                task_id=args.task_id,
                variant=args.variant,
                model=args.model,
                effort=args.effort,
                status=args.status,
                accepted=acc_val,
                input_tokens=args.input_tokens,
                cached_input_tokens=args.cached_input_tokens,
                output_tokens=args.output_tokens,
                reasoning_output_tokens=args.reasoning_output_tokens,
                retries=args.retries,
                elapsed_seconds=args.elapsed_seconds,
                ledger_path=args.ledger,
                timestamp=args.timestamp,
            )
            print(f"Recorded telemetry for task '{args.task_id}' [{args.variant}] to {args.ledger}")
            return 0

        elif args.command == "summary":
            records = load_ledger(args.ledger)
            if not records:
                print(f"No records found in ledger: {args.ledger}")
                return 0

            summary = compute_summary(records, variant_filter=args.variant)
            if args.json:
                print(json.dumps(summary, indent=2))
            else:
                print(format_summary_table(summary))
            return 0

    except Exception as exc:
        sys.stderr.write(f"Error: {exc}\n")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
