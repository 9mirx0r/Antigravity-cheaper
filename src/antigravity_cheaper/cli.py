#!/usr/bin/env python3
"""Unified CLI entrypoint for Antigravity-Cheaper (agy).

Provides single-command access to all progressive disclosure tools:
  agy map        - Generate budget-fitted Personalized PageRank symbol map
  agy skeleton   - Extract AST skeleton with function/method bodies elided
  agy symbols    - Extract symbol table from source file
  agy pack       - Bounded context packing for logs, errors, and traces
  agy expand     - Verified line range expansion validating SHA-256
  agy memory     - Persistent zero-tax SQLite+FTS5 memory operations
  agy pipeline   - Autonomous 3-stage cognitive pipeline & swarm decomposer
  agy lock       - Build or verify Merkle prompt prefix cache
  agy ledger     - Prompt-free telemetry recording and cost summaries
  agy server     - Run FastMCP stdio symbol server
  agy setup      - Auto-configure FastMCP symbol server in Antigravity/Cursor/Claude
  agy cache      - Gemini 90% context caching eligibility advisor & prefix profiler
  agy stats      - Unified workspace, memory, and telemetry dashboard
"""

from __future__ import annotations

import sys

from . import (
    __version__,
    agy_ast,
    agy_cache_advisor,
    agy_capsule,
    agy_handoff,
    agy_ledger,
    agy_mcp_server,
    agy_memory,
    agy_pack,
    agy_pipeline,
    agy_prefix_lock,
    agy_repomap,
    agy_setup,
    agy_stats,
    noise_sanitizer,
)


def print_help():
    help_text = f"""Antigravity-Cheaper v{__version__} - Context Optimization Toolkit & FastMCP Symbol Server

Usage:
  agy <command> [options]

Commands:
  QOL & Diagnostics:
    setup      Auto-configure FastMCP symbol server in Antigravity/Cursor/Claude
    cache      Check Gemini 90% context caching eligibility & prefix volume
    stats      Show workspace health, indexed symbols, memory, and telemetry

  Architecture & Symbols:
    map        Generate budget-fitted Personalized PageRank symbol map
    skeleton   Extract AST skeleton with bodies elided (...)
    symbols    Extract symbol definitions and metadata from file
    path       Find shortest directed causal path between two symbols
    causal     Trace callers and dependencies from error message / query

  Context & Noise Slicing:
    pack       Pack large logs or code into bounded context with SHA-256
    expand     Verified line range extraction validating SHA-256 hash
    handoff    Local threshold router (<=24KB full, >24KB pack) with circuit breaker
    capsule    Seal or check file/tree dependency validity
    sanitize   Filter command lines and strip ANSI / terminal noise

  Prompt Cache & Telemetry:
    lock       Build or verify Merkle frozen prefix (>85% cache hit rate)
    ledger     Record or summarize token usage and cost per accepted outcome
    memory     Zero-tax SQLite+FTS5 persistent project memory
    pipeline   Dual-model cognitive pipeline (Architect -> Implementer -> Critic)

  MCP Server:
    server     Run FastMCP stdio symbol server (JSON-RPC 2.0)

General Options:
  -h, --help      Show this help message and exit
  -v, --version   Show version information and exit

Examples:
  agy setup --dry-run
  agy cache --root .
  agy stats
  agy map --root . --budget 1200
  agy skeleton --source src/antigravity_cheaper/cli.py
  agy memory stats
  agy server --test
"""
    print(help_text)


def main(argv: list[str] | None = None) -> int:
    if argv is not None:
        sys.argv = argv
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print_help()
        return 0

    if sys.argv[1] in ("-v", "--version", "version"):
        print(f"antigravity-cheaper v{__version__}")
        return 0

    cmd = sys.argv[1].lower()

    if cmd in ("setup", "install-mcp"):
        return agy_setup.main(sys.argv[2:])

    elif cmd in ("cache", "cache-check", "advisor"):
        return agy_cache_advisor.main(sys.argv[2:])

    elif cmd in ("stats", "dashboard", "status"):
        return agy_stats.main(sys.argv[2:])

    elif cmd in ("map", "subgraph", "summary", "path", "causal"):
        sys.argv = ["agy-repomap"] + sys.argv[1:]
        res = agy_repomap.main()
        return res if isinstance(res, int) else 0

    elif cmd in ("skeleton", "symbols"):
        sys.argv = ["agy-ast"] + sys.argv[1:]
        res = agy_ast.main()
        return res if isinstance(res, int) else 0

    elif cmd in ("pack", "expand"):
        sys.argv = ["agy-pack"] + sys.argv[1:]
        res = agy_pack.main()
        return res if isinstance(res, int) else 0

    elif cmd in ("sanitize", "clean"):
        return noise_sanitizer.main(sys.argv[2:])

    elif cmd == "capsule":
        sys.argv = ["agy-capsule"] + sys.argv[2:]
        res = agy_capsule.main()
        return res if isinstance(res, int) else 0

    elif cmd in ("lock", "prefix"):
        sub = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] in ("build", "verify") else "build"
        remaining = [a for a in sys.argv[2:] if a != sub]
        sys.argv = ["agy-prefix-lock", sub] + remaining
        res = agy_prefix_lock.main()
        return res if isinstance(res, int) else 0

    elif cmd == "memory":
        sys.argv = ["agy-memory"] + sys.argv[2:]
        res = agy_memory.main()
        return res if isinstance(res, int) else 0

    elif cmd == "pipeline":
        sys.argv = ["agy-pipeline"] + sys.argv[2:]
        res = agy_pipeline.main()
        return res if isinstance(res, int) else 0

    elif cmd == "handoff":
        sub = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] == "prepare" else "prepare"
        remaining = [a for a in sys.argv[2:] if a != sub]
        sys.argv = ["agy-handoff", sub] + remaining
        res = agy_handoff.main()
        return res if isinstance(res, int) else 0

    elif cmd == "ledger":
        sub = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] in ("record", "summary") else "summary"
        remaining = [a for a in sys.argv[2:] if a != sub]
        sys.argv = ["agy-ledger", sub] + remaining
        res = agy_ledger.main()
        return res if isinstance(res, int) else 0

    elif cmd == "server":
        sys.argv = ["agy-mcp-server"] + sys.argv[2:]
        res = agy_mcp_server.main()
        return res if isinstance(res, int) else 0

    else:
        print(f"Unknown command: '{cmd}'. Run 'agy --help' for available commands.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
