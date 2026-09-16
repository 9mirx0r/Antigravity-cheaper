#!/usr/bin/env python3
"""
Noise Sanitizer - PreToolUse Hook & Output Filter for Antigravity (AGY)

Intercepts 'run_command' tool calls and filters outputs to enforce token discipline:
1. Pipeline Safety (RTK lesson): Detects pipes to machine-readable utilities (xargs, wc, awk, etc.)
   and skips alteration to preserve streaming pipeline contracts.
2. Blocks 'cat' or 'type' over large files (redirects model to 'view_file').
3. Wraps test runners ('npm test', 'pytest', 'cargo test', etc.) to redirect full output
   to '.gemini/scratch/test_output.log', emit only the tail and failure summary,
   and provide an executable recovery hint (Tee Hint).
4. Optimizes unpaged 'git log' commands by injecting '-n 15 --oneline'.
5. Never-Worse Invariant: Mathematically guarantees that filtered output never consumes more tokens than raw.
6. ANSI Escape Stripping: Removes terminal control sequences and styling codes.
7. Short-circuits known 'Clean / Up-to-date' states.
"""

import argparse
import io
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# Configure stdin and stdout to UTF-8 to prevent Windows codepage corruption
if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")
elif hasattr(sys.stdin, "buffer"):
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
elif hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Thresholds for classifying a file as "large"
LARGE_FILE_BYTES_THRESHOLD = 2048  # ~2 KB
LARGE_FILE_LINES_THRESHOLD = 40

# ANSI escape sequence regex
ANSI_ESCAPE_REGEX = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

# Known test runner regex patterns
TEST_RUNNER_PATTERNS = [
    r"\bpytest\b",
    r"\bpython\s+(?:-m\s+)?(?:unittest|pytest)\b",
    r"\b(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?test\b",
    r"\bnpx\s+(?:jest|vitest|mocha|pytest)\b",
    r"\b(?:vitest|jest|mocha)\b",
    r"\bcargo\s+test\b",
    r"\bgo\s+test\b",
    r"\b(?:mvn|gradle|gradlew)\s+test\b",
    r"\bdotnet\s+test\b",
]
TEST_RUNNER_REGEX = re.compile("|".join(TEST_RUNNER_PATTERNS), re.IGNORECASE)

# Patterns for cat / type / Get-Content
CAT_TYPE_REGEX = re.compile(
    r"(?:^|[;&|]\s*)(?:cat|type|Get-Content|gc)\s+([^\s|><;&]+|\"[^\"]+\"|'[^']+')",
    re.IGNORECASE,
)

# Patterns indicating output is already paged or bounded in shell
PAGING_PIPES_REGEX = re.compile(
    r"\|\s*(?:head|tail|more|less|Select-Object\s+-(?:First|Last)|select\s+-(?:first|last)|sls|grep|findstr)\b",
    re.IGNORECASE,
)

# Machine pipe detection: if feeding xargs, wc, awk, cut, etc., do NOT disrupt formatting
MACHINE_PIPE_REGEX = re.compile(
    r"\|\s*(?:xargs|wc|awk|cut|sort|uniq|jq|column)\b",
    re.IGNORECASE,
)

# Pattern for git log
GIT_LOG_REGEX = re.compile(r"\bgit\s+log\b", re.IGNORECASE)

# Pattern indicating explicit paging in git log
GIT_LOG_PAGED_REGEX = re.compile(
    r"(?:-n\s*\d+|-\d+\b|--max-count(?:=|\s+)\d+)",
    re.IGNORECASE,
)


def estimate_tokens(text: str) -> int:
    """Calculates a conservative token estimate (ceil(len / 4.0))."""
    if not text:
        return 0
    return (len(text) + 3) // 4


def never_worse(raw: str, filtered: str) -> str:
    """
    Never-Worse Invariant (RTK / Caveman):
    Guarantees that the filtered text never consumes more estimated tokens than the raw version.
    If tokens(filtered) > tokens(raw), returns raw.
    """
    if estimate_tokens(filtered) <= estimate_tokens(raw):
        return filtered
    return raw


def strip_ansi(text: str) -> str:
    """Removes ANSI escape codes (colors, cursor positions, terminal styles)."""
    return ANSI_ESCAPE_REGEX.sub("", text)


def sanitize_output(output_text: str, command: str = "") -> str:
    """
    Post-execution sanitizer:
    - Strips ANSI codes.
    - Short-circuits clean/up-to-date states to minimal tokens.
    - Enforces the Never-Worse invariant.
    """
    if not output_text:
        return ""

    clean = strip_ansi(output_text)
    stripped = clean.strip()

    # Short-circuit clean states
    cmd_lower = command.lower()
    if "git status" in cmd_lower:
        if "nothing to commit, working tree clean" in stripped.lower():
            return "ok (working tree clean)"
    elif "npm" in cmd_lower or "yarn" in cmd_lower or "pnpm" in cmd_lower:
        if "up to date" in stripped.lower() and "vulnerabilities" in stripped.lower():
            return "ok (up to date)"

    return never_worse(output_text, clean)


def _is_large_file(file_path: str, cwd: str) -> tuple[bool, str]:
    """Inspects file size and line count to determine if it violates bounding rules."""
    clean_path = file_path.strip('"\'')
    target_file = None

    candidates = [
        Path(cwd) / clean_path if cwd else Path(clean_path),
        Path(clean_path),
    ]

    for candidate in candidates:
        if candidate.is_file():
            target_file = candidate
            break

    if target_file:
        try:
            size_bytes = os.path.getsize(target_file)
            if size_bytes > LARGE_FILE_BYTES_THRESHOLD:
                return True, f"file of {size_bytes} bytes (threshold: {LARGE_FILE_BYTES_THRESHOLD} B)"

            with open(target_file, encoding="utf-8", errors="replace") as f:
                line_count = sum(1 for _ in f)
                if line_count > LARGE_FILE_LINES_THRESHOLD:
                    return True, f"file of {line_count} lines (threshold: {LARGE_FILE_LINES_THRESHOLD} lines)"
        except Exception:
            pass

    ext = os.path.splitext(clean_path)[1].lower()
    code_extensions = {".py", ".js", ".ts", ".jsx", ".tsx", ".json", ".log", ".txt", ".md", ".html", ".css", ".csv", ".yml", ".yaml"}
    if ext in code_extensions and not target_file:
        return True, "unbounded source or data file"

    return False, ""


def process_command(cmd_line: str, cwd: str) -> dict[str, Any]:
    """Evaluates CommandLine and returns the AGY PreToolUse decision."""
    if not cmd_line or not cmd_line.strip():
        return {"decision": "allow"}

    stripped_cmd = cmd_line.strip()

    # 0. Pipeline Safety: If feeding xargs, wc, awk, etc., do NOT alter formatting
    if MACHINE_PIPE_REGEX.search(stripped_cmd):
        return {
            "decision": "allow",
            "reason": "Machine pipeline detected (| xargs/wc/awk/etc.): raw stream preserved for contract integrity.",
        }

    # 1. Rule: Prohibit 'cat' or 'type' over large files
    cat_match = CAT_TYPE_REGEX.search(stripped_cmd)
    if cat_match:
        has_limiting_pipe = bool(PAGING_PIPES_REGEX.search(stripped_cmd))
        if not has_limiting_pipe:
            target_arg = cat_match.group(1).strip()
            if not target_arg.startswith("-") and not target_arg.startswith("/"):
                is_large, reason_detail = _is_large_file(target_arg, cwd)
                if is_large:
                    return {
                        "decision": "deny",
                        "reason": (
                            f"Command denied by token discipline policy: "
                            f"Direct dump via 'cat/type' detected on '{target_arg}' ({reason_detail}). "
                            f"To preserve context window, use 'view_file' with 'StartLine' and 'EndLine'."
                        ),
                    }

    # 2. Rule: Test runners ('npm test', 'pytest', 'cargo test', etc.)
    if "test_output.log" not in stripped_cmd and TEST_RUNNER_REGEX.search(stripped_cmd):
        log_rel_dir = ".gemini/scratch"
        log_rel_file = ".gemini/scratch/test_output.log"
        tail_lines = 35

        if sys.platform == "win32":
            wrapped_cmd = (
                f"if (!(Test-Path -Path '{log_rel_dir}')) {{ "
                f"New-Item -ItemType Directory -Force -Path '{log_rel_dir}' | Out-Null }}; "
                f"& {{ {stripped_cmd} }} *>&1 | "
                f"Out-File -FilePath '{log_rel_file}' -Encoding utf8; "
                f"Get-Content '{log_rel_file}' -Tail {tail_lines}; "
                f"Write-Output '[full output saved to: {log_rel_file}]'"
            )
        else:
            wrapped_cmd = (
                f"mkdir -p '{log_rel_dir}' && "
                f"({stripped_cmd}) 2>&1 | tee '{log_rel_file}' | tail -n {tail_lines} && "
                f"echo '[full output saved to: {log_rel_file}]'"
            )

        return {
            "decision": "allow",
            "reason": (
                "Test runner detected: full output redirected to '.gemini/scratch/test_output.log' "
                f"and bounded to last {tail_lines} lines with recovery hint (Tee Hint)."
            ),
            "overwrite": {
                "CommandLine": wrapped_cmd
            },
        }

    # 3. Rule: Unpaged 'git log'
    if GIT_LOG_REGEX.search(stripped_cmd):
        is_paged = bool(GIT_LOG_PAGED_REGEX.search(stripped_cmd))
        if not is_paged:
            if "--oneline" in stripped_cmd:
                modified_cmd = re.sub(r"\bgit\s+log\b", "git log -n 15", stripped_cmd, count=1)
            else:
                modified_cmd = re.sub(r"\bgit\s+log\b", "git log -n 15 --oneline", stripped_cmd, count=1)

            return {
                "decision": "allow",
                "reason": (
                    "Unbounded 'git log' detected: optimized with '-n 15 --oneline' "
                    "to safeguard context window."
                ),
                "overwrite": {
                    "CommandLine": modified_cmd
                },
            }

    return {"decision": "allow"}


def main(argv: list[str] | None = None) -> int:
    # If called with CLI flags (e.g. from `agy sanitize`)
    if argv is not None or (len(sys.argv) > 1 and sys.argv[1] not in ("-",)):
        parser = argparse.ArgumentParser(
            description="Sanitize command lines and filter terminal outputs to suppress token noise.",
            prog="agy sanitize",
        )
        parser.add_argument("--cmd", help="Evaluate PreToolUse decision on a command line.")
        parser.add_argument("--cwd", default="", help="Working directory context for file checks.")
        parser.add_argument("--filter", help="Sanitize terminal output text (strip ANSI and clean states).")
        parser.add_argument("--file", type=Path, help="Read and sanitize output from a file.")
        parser.add_argument("--strip-ansi", action="store_true", help="Strip ANSI escape sequences from input.")

        args = parser.parse_args(argv)

        if args.cmd:
            decision = process_command(args.cmd, args.cwd or os.getcwd())
            print(json.dumps(decision, indent=2))
            return 0

        if args.filter:
            print(sanitize_output(args.filter))
            return 0

        if args.file:
            if not args.file.exists():
                print(f"File not found: {args.file}", file=sys.stderr)
                return 1
            text = args.file.read_text(encoding="utf-8", errors="replace")
            print(sanitize_output(text))
            return 0

        parser.print_help()
        return 0

    # Antigravity stdio JSON hook mode
    try:
        raw_input_data = sys.stdin.read()
        if not raw_input_data or not raw_input_data.strip():
            json.dump({"decision": "allow"}, sys.stdout)
            return 0

        payload = json.loads(raw_input_data)
        tool_call = payload.get("toolCall", {})
        tool_name = tool_call.get("name", "")
        args = tool_call.get("args", {})

        if tool_name == "run_command":
            cmd_line = args.get("CommandLine", "")
            cwd = args.get("Cwd", "") or os.getcwd()
            response = process_command(cmd_line, cwd)
        else:
            response = {"decision": "allow"}

        json.dump(response, sys.stdout, indent=2, ensure_ascii=True)
        return 0

    except Exception as exc:
        sys.stderr.write(f"[noise_sanitizer error] {exc}\n")
        json.dump({"decision": "allow"}, sys.stdout)
        return 0


if __name__ == "__main__":
    sys.exit(main())
