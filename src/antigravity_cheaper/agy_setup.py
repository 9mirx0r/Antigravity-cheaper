#!/usr/bin/env python3
"""Auto-configuration wizard for Antigravity-Cheaper FastMCP Symbol Server.

Safely detects and registers 'agy-symbol-server' into:
- Antigravity global MCP config (~/.gemini/antigravity/mcp_config.json)
- Antigravity workspace MCP config (.agents/mcp_config.json or .gemini/antigravity/mcp_config.json)
- Cursor IDE config (.cursor/mcp.json)
- Claude Desktop config (%APPDATA%/Claude/claude_desktop_config.json)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

SERVER_NAME = "agy-symbol-server"
DEFAULT_SERVER_CONFIG = {
    "command": "python",
    "args": ["-m", "antigravity_cheaper.agy_mcp_server"],
}


def get_default_config_locations() -> list[tuple[str, Path]]:
    """Returns standard candidates for MCP configuration files."""
    home = Path.home()
    cwd = Path.cwd()
    candidates = []

    # 1. Antigravity Global
    candidates.append(("Antigravity (Global)", home / ".gemini" / "antigravity" / "mcp_config.json"))

    # 2. Antigravity Workspace
    candidates.append(("Antigravity (Workspace .agents)", cwd / ".agents" / "mcp_config.json"))
    candidates.append(("Antigravity (Workspace .gemini)", cwd / ".gemini" / "antigravity" / "mcp_config.json"))

    # 3. Cursor
    candidates.append(("Cursor (Workspace)", cwd / ".cursor" / "mcp.json"))
    candidates.append(("Cursor (Global)", home / ".cursor" / "mcp.json"))

    # 4. Claude Desktop
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.append(("Claude Desktop (Windows)", Path(appdata) / "Claude" / "claude_desktop_config.json"))
    elif sys.platform == "darwin":
        candidates.append(("Claude Desktop (macOS)", home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"))
    else:
        candidates.append(("Claude Desktop (Linux)", home / ".config" / "Claude" / "claude_desktop_config.json"))

    return candidates


def read_json_config(path: Path) -> dict[str, Any]:
    """Reads and parses a JSON config file safely."""
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"Warning: Could not parse {path}: {e}", file=sys.stderr)
        return {}


def write_json_config(path: Path, data: dict[str, Any], dry_run: bool = False) -> bool:
    """Writes data to a JSON file safely with formatting."""
    if dry_run:
        return True
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return True


def configure_mcp_file(
    path: Path,
    python_bin: str = "python",
    remove: bool = False,
    dry_run: bool = False,
) -> tuple[bool, str]:
    """Injects or removes agy-symbol-server in the specified config file."""
    data = read_json_config(path)
    servers_key = "mcpServers"
    if servers_key not in data or not isinstance(data[servers_key], dict):
        data[servers_key] = {}

    servers = data[servers_key]

    if remove:
        if SERVER_NAME in servers:
            del servers[SERVER_NAME]
            write_json_config(path, data, dry_run=dry_run)
            action = "Would remove" if dry_run else "Removed"
            return True, f"{action} '{SERVER_NAME}' from {path}"
        return False, f"'{SERVER_NAME}' was not found in {path}"

    server_entry = {
        "command": python_bin,
        "args": ["-m", "antigravity_cheaper.agy_mcp_server"],
    }

    already_configured = servers.get(SERVER_NAME) == server_entry
    servers[SERVER_NAME] = server_entry
    write_json_config(path, data, dry_run=dry_run)

    if already_configured:
        return True, f"Already up-to-date in {path}"
    action = "Would register" if dry_run else "Successfully registered"
    return True, f"{action} '{SERVER_NAME}' in {path}"


def run_setup(
    target_path: Path | None = None,
    python_bin: str = "python",
    remove: bool = False,
    dry_run: bool = False,
) -> int:
    """Main setup routine detecting or applying MCP config."""
    print("Antigravity-Cheaper MCP Setup (v1.0.0)")
    print("=" * 60)

    if target_path:
        targets = [("Specified Path", target_path)]
    else:
        all_candidates = get_default_config_locations()
        existing = [c for c in all_candidates if c[1].exists() or c[1].parent.exists()]
        if not existing:
            targets = [all_candidates[0]]
        else:
            targets = existing

    success_count = 0
    for label, path in targets:
        ok, msg = configure_mcp_file(path, python_bin=python_bin, remove=remove, dry_run=dry_run)
        prefix = "[DRY-RUN] " if dry_run else ""
        icon = "[OK]" if ok else "[--]"
        print(f"{icon} {label}: {prefix}{msg}")
        if ok:
            success_count += 1

    print("=" * 60)
    if dry_run:
        print("Dry-run completed. No files were modified.")
    elif remove:
        print("Removal complete.")
    else:
        print(f"MCP Symbol Server configured in {success_count} location(s).")
        print("To verify connectivity in Antigravity or terminal, run:")
        print("  agy server --test")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Auto-configure Antigravity-Cheaper FastMCP Symbol Server in MCP hosts.",
        prog="agy setup",
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=None,
        help="Explicit path to mcp_config.json or mcp.json to configure.",
    )
    parser.add_argument(
        "--python",
        default="python",
        help="Python executable name or path to invoke agy_mcp_server (default: 'python').",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate configuration without modifying any files on disk.",
    )
    parser.add_argument(
        "--remove",
        action="store_true",
        help="Remove agy-symbol-server from target MCP configuration files.",
    )

    args = parser.parse_args(argv)
    return run_setup(
        target_path=args.path,
        python_bin=args.python,
        remove=args.remove,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
