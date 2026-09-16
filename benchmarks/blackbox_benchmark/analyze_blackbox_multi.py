"""Multi-Run Blackbox Benchmark Analyzer.

Computes metrics for Run 1, Run 2, and aggregate averages for Baseline vs Antigravity-Cheaper.
"""

import json
from pathlib import Path
from datetime import datetime

MODEL_PRICING = {
    "flash_input_per_m": 0.15,
    "flash_output_per_m": 0.60,
    "flash_thinking_per_m": 0.70,
    "flash_cached_per_m": 0.0375,
}

CHARS_PER_TOKEN = 3.9
THINKING_CHARS_PER_TOKEN = 4.0


def analyze_transcript(transcript_path: str, label: str) -> dict:
    path = Path(transcript_path)
    full_path = path.parent / "transcript_full.jsonl"
    target = full_path if full_path.exists() else path

    steps = []
    with open(target, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                steps.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    planner_turns = [s for s in steps if s.get("type") == "PLANNER_RESPONSE"]
    generic_steps = [s for s in steps if s.get("type") == "GENERIC"]
    user_steps = [s for s in steps if s.get("type") == "USER_INPUT"]

    timestamps = []
    for s in steps:
        ts = s.get("created_at", "")
        if ts:
            try:
                if ts.endswith("Z"):
                    ts = ts[:-1] + "+00:00"
                timestamps.append(datetime.fromisoformat(ts))
            except:
                pass

    wall_clock_s = 0
    if len(timestamps) >= 2:
        wall_clock_s = (timestamps[-1] - timestamps[0]).total_seconds()

    total_thinking_chars = 0
    total_output_chars = 0
    total_input_chars = 0
    tool_calls_count = 0
    tool_call_types = {}
    test_run_count = 0
    file_read_count = 0
    file_edit_count = 0

    for step in planner_turns:
        thinking = step.get("thinking", "") or ""
        content = step.get("content", "") or ""
        total_thinking_chars += len(thinking)
        total_output_chars += len(content)

        tc = step.get("tool_calls", []) or []
        tool_calls_count += len(tc)
        for call in tc:
            tool_name = call.get("name", call.get("tool", "unknown"))
            tool_call_types[tool_name] = tool_call_types.get(tool_name, 0) + 1

            if tool_name == "run_command":
                args = call.get("arguments", call.get("args", {}))
                cmd = ""
                if isinstance(args, dict):
                    cmd = args.get("CommandLine", args.get("command", ""))
                if "test_blackbox" in str(cmd):
                    test_run_count += 1
            elif tool_name in ("view_file", "grep_search", "find_by_name", "list_dir"):
                file_read_count += 1
            elif tool_name in ("replace_file_content", "write_to_file"):
                file_edit_count += 1

    for step in generic_steps:
        content = step.get("content", "") or ""
        total_input_chars += len(content)

    for step in user_steps:
        content = step.get("content", "") or ""
        total_input_chars += len(content)

    thinking_tokens = int(total_thinking_chars / THINKING_CHARS_PER_TOKEN)
    output_tokens = int(total_output_chars / CHARS_PER_TOKEN)

    cumulative_input = 0
    running_context = 0
    for step in steps:
        content = step.get("content", "") or ""
        thinking = step.get("thinking", "") or ""
        if step.get("type") == "PLANNER_RESPONSE":
            cumulative_input += int(running_context / CHARS_PER_TOKEN)
            running_context += len(content) + len(thinking)
        else:
            running_context += len(content)

    input_cost = (cumulative_input / 1_000_000) * MODEL_PRICING["flash_input_per_m"]
    output_cost = (output_tokens / 1_000_000) * MODEL_PRICING["flash_output_per_m"]
    thinking_cost = (thinking_tokens / 1_000_000) * MODEL_PRICING["flash_thinking_per_m"]
    total_cost = input_cost + output_cost + thinking_cost

    return {
        "label": label,
        "total_steps": len(steps),
        "planner_turns": len(planner_turns),
        "tool_calls": tool_calls_count,
        "test_runs": test_run_count,
        "file_reads": file_read_count,
        "file_edits": file_edit_count,
        "wall_clock_seconds": wall_clock_s,
        "thinking_chars": total_thinking_chars,
        "output_chars": total_output_chars,
        "input_chars_tool_output": total_input_chars,
        "thinking_tokens_est": thinking_tokens,
        "output_tokens_est": output_tokens,
        "cumulative_input_tokens_est": cumulative_input,
        "input_cost_est": input_cost,
        "output_cost_est": output_cost,
        "thinking_cost_est": thinking_cost,
        "total_cost_est": total_cost,
        "tool_call_breakdown": tool_call_types,
    }


def main():
    runs = {
        "run1_baseline": r"C:\Users\emir\.gemini\antigravity\brain\a64c4855-e601-41e9-8996-dfe6b54b8c5f\.system_generated\logs\transcript.jsonl",
        "run1_cheaper": r"C:\Users\emir\.gemini\antigravity\brain\ca2f313f-68a1-4ad9-8e1d-65ded077ece1\.system_generated\logs\transcript.jsonl",
        "run2_baseline": r"C:\Users\emir\.gemini\antigravity\brain\f6bd3e44-5042-488c-ac2b-f6bd7ca0b5a6\.system_generated\logs\transcript.jsonl",
        "run2_cheaper": r"C:\Users\emir\.gemini\antigravity\brain\b68f2a49-61a8-4d0b-ac52-cb53fd88bf80\.system_generated\logs\transcript.jsonl",
    }

    missing = [v for v in runs.values() if not Path(v).exists()]
    if missing:
        print(f"Notice: {len(missing)} benchmark transcript(s) not found on this machine.")
        print("Provide local transcript JSONL paths to run replication analysis.")
        return

    data = {k: analyze_transcript(v, k) for k, v in runs.items()}

    print("=" * 86)
    print("  OPERATION BLACKBOX — Multi-Run Replication Telemetry (Run 1 & Run 2)")
    print("=" * 86)
    print()

    header = f"{'Metric':<34} | {'Base R1':>10} {'Chp R1':>10} | {'Base R2':>10} {'Chp R2':>10} | {'Delta R2':>8}"
    print(header)
    print("-" * 92)

    metrics = [
        ("Total Steps", "total_steps", False),
        ("Planner Turns", "planner_turns", False),
        ("Total Tool Calls", "tool_calls", False),
        ("Test Suite Runs", "test_runs", False),
        ("File Reads", "file_reads", False),
        ("File Edits", "file_edits", False),
        ("Wall-clock Time (s)", "wall_clock_seconds", True),
        ("Thinking Tokens (est)", "thinking_tokens_est", False),
        ("Tool Noise Chars", "input_chars_tool_output", False),
        ("Cumulative Input Tokens", "cumulative_input_tokens_est", False),
        ("Input Cost ($)", "input_cost_est", True),
        ("Thinking Cost ($)", "thinking_cost_est", True),
        ("TOTAL COST ($)", "total_cost_est", True),
    ]

    for label, key, is_float in metrics:
        b1 = data["run1_baseline"][key]
        c1 = data["run1_cheaper"][key]
        b2 = data["run2_baseline"][key]
        c2 = data["run2_cheaper"][key]

        if is_float:
            if "cost" in key.lower() or "Cost" in label:
                s_b1 = f"${b1:.4f}"
                s_c1 = f"${c1:.4f}"
                s_b2 = f"${b2:.4f}"
                s_c2 = f"${c2:.4f}"
            else:
                s_b1 = f"{b1:.1f}"
                s_c1 = f"{c1:.1f}"
                s_b2 = f"{b2:.1f}"
                s_c2 = f"{c2:.1f}"
        else:
            s_b1 = f"{b1:,}"
            s_c1 = f"{c1:,}"
            s_b2 = f"{b2:,}"
            s_c2 = f"{c2:,}"

        delta_r2 = ((c2 - b2) / b2) * 100 if b2 > 0 else 0.0
        s_delta2 = f"{delta_r2:+.1f}%"

        print(f"  {label:<32} | {s_b1:>10} {s_c1:>10} | {s_b2:>10} {s_c2:>10} | {s_delta2:>8}")

    print("-" * 92)
    print()

    # Tool call breakdown for Run 2
    print("  Run 2 Tool Call Breakdown:")
    all_tools = set(list(data["run2_baseline"]["tool_call_breakdown"].keys()) +
                    list(data["run2_cheaper"]["tool_call_breakdown"].keys()))
    for tool in sorted(all_tools):
        b = data["run2_baseline"]["tool_call_breakdown"].get(tool, 0)
        c = data["run2_cheaper"]["tool_call_breakdown"].get(tool, 0)
        print(f"    {tool:<35} Baseline: {b:>3} | Cheaper: {c:>3}")

    print()

    # Aggregate averages
    print("=" * 86)
    print("  AVERAGE ACROSS BOTH RUNS (N=2)")
    print("=" * 86)
    print(f"  {'Metric':<34} | {'Baseline Avg':>15} | {'Cheaper Avg':>15} | {'Delta Avg':>10}")
    print("-" * 86)

    for label, key, is_float in metrics:
        avg_b = (data["run1_baseline"][key] + data["run2_baseline"][key]) / 2.0
        avg_c = (data["run1_cheaper"][key] + data["run2_cheaper"][key]) / 2.0

        if is_float:
            if "cost" in key.lower() or "Cost" in label:
                sb = f"${avg_b:.4f}"
                sc = f"${avg_c:.4f}"
            else:
                sb = f"{avg_b:.1f}"
                sc = f"{avg_c:.1f}"
        else:
            sb = f"{int(avg_b):,}"
            sc = f"{int(avg_c):,}"

        delta_avg = ((avg_c - avg_b) / avg_b) * 100 if avg_b > 0 else 0.0
        s_delta = f"{delta_avg:+.1f}%"
        print(f"  {label:<34} | {sb:>15} | {sc:>15} | {s_delta:>10}")

    print("-" * 86)

    # Save to json
    out_file = Path("benchmarks/blackbox_benchmark/blackbox_multi_run_results.json")
    with open(out_file, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"\n  Multi-run results saved to: {out_file}")


if __name__ == "__main__":
    main()
