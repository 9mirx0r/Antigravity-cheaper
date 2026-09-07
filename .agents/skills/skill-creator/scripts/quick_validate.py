#!/usr/bin/env python3
"""
quick_validate.py - Canonical Deterministic Validator for Agent Skills (agentskills.io).

Validates:
1. Existence and syntax of YAML frontmatter (name and description required).
2. Kebab-case naming convention and exact match with enclosing directory name.
3. Description quality, length, and style (third-person, pushy triggers, <= 1024 chars).
4. Referential integrity: physical existence on disk of relative links to scripts/ or references/.
5. Progressive Disclosure: warning if SKILL.md exceeds recommended line threshold (150 lines).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Ensure UTF-8 output on Windows console
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def parse_frontmatter(content: str) -> Tuple[Dict[str, Any] | None, str, str | None]:
    """
    Parses YAML frontmatter delimited by '---'.
    Returns (frontmatter_dict, markdown_body, error_message).
    Native implementation with zero external dependencies.
    """
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, content, "SKILL.md must begin with '---' delimiter on line 1."

    end_idx = -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx == -1:
        return None, content, "Unclosed YAML frontmatter: closing '---' delimiter missing."

    fm_raw = "\n".join(lines[1:end_idx])
    body = "\n".join(lines[end_idx + 1:])

    # Try PyYAML if installed
    try:
        import yaml
        try:
            data = yaml.safe_load(fm_raw)
            if not isinstance(data, dict):
                return None, body, "YAML frontmatter must represent a key-value mapping."
            return data, body, None
        except yaml.YAMLError as exc:
            return None, body, f"YAML syntax error: {exc}"
    except ImportError:
        pass

    # Lightweight native parser for standard frontmatter keys
    data: Dict[str, Any] = {}
    current_key: str | None = None
    multiline_buf: List[str] = []
    scalar_mode: str | None = None

    for line in lines[1:end_idx]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        key_match = re.match(r"^([a-zA-Z0-9_-]+)\s*:\s*(.*)$", line)
        if key_match:
            if current_key is not None:
                joined = "\n".join(multiline_buf) if scalar_mode in ("|", "|-") else " ".join(multiline_buf)
                data[current_key] = joined.strip()
                multiline_buf = []
                scalar_mode = None

            key = key_match.group(1)
            raw_val = key_match.group(2).strip()

            if raw_val in (">", ">-", "|", "|-"):
                current_key = key
                scalar_mode = raw_val
            elif (raw_val.startswith('"') and raw_val.endswith('"')) or (
                raw_val.startswith("'") and raw_val.endswith("'")
            ):
                data[key] = raw_val[1:-1].strip()
                current_key = None
            elif raw_val:
                data[key] = raw_val
                current_key = None
            else:
                current_key = key
                scalar_mode = ">"
        elif current_key is not None and (line.startswith("  ") or line.startswith("\t")):
            multiline_buf.append(stripped)
        else:
            if current_key is not None:
                multiline_buf.append(stripped)

    if current_key is not None:
        joined = "\n".join(multiline_buf) if scalar_mode in ("|", "|-") else " ".join(multiline_buf)
        data[current_key] = joined.strip()

    return data, body, None


def extract_markdown_links(content: str) -> List[Tuple[str, str, int]]:
    """
    Extracts relative markdown links in [label](target) format.
    Returns list of (label, target, line_number).
    """
    links: List[Tuple[str, str, int]] = []
    for line_no, line in enumerate(content.splitlines(), start=1):
        matches = re.finditer(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)", line)
        for m in matches:
            label, target = m.group(1), m.group(2).strip()
            if re.match(r"^(https?://|mailto:|#)", target, re.IGNORECASE):
                continue
            links.append((label, target, line_no))
    return links


class SkillValidator:
    def __init__(self, skill_path: Path, max_lines_warn: int = 150):
        self.skill_dir = skill_path if skill_path.is_dir() else skill_path.parent
        self.skill_file = self.skill_dir / "SKILL.md"
        self.max_lines_warn = max_lines_warn
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def validate(self) -> bool:
        if not self.skill_file.exists():
            self.errors.append(f"Missing mandatory root file: {self.skill_file}")
            return False

        try:
            content = self.skill_file.read_text(encoding="utf-8")
        except Exception as e:
            self.errors.append(f"Failed to read {self.skill_file}: {e}")
            return False

        lines = content.splitlines()
        total_lines = len(lines)

        if total_lines > self.max_lines_warn:
            self.warnings.append(
                f"SKILL.md has {total_lines} lines (recommended: <= {self.max_lines_warn}). "
                "Consider delegating deep documentation to references/ to optimize context window."
            )

        fm_data, body, fm_error = parse_frontmatter(content)
        if fm_error:
            self.errors.append(f"Invalid frontmatter: {fm_error}")
            return False

        if not fm_data:
            self.errors.append("Empty or missing YAML frontmatter.")
            return False

        self._validate_name(fm_data.get("name"))
        self._validate_description(fm_data.get("description"))
        self._validate_relative_links(content)

        return len(self.errors) == 0

    def _validate_name(self, name: Any) -> None:
        if not name or not isinstance(name, str):
            self.errors.append("Field 'name' is required in frontmatter and must be a string.")
            return

        name = name.strip()
        expected_dir_name = self.skill_dir.name

        if name != expected_dir_name:
            self.errors.append(
                f"Field 'name' ('{name}') must match enclosing directory name ('{expected_dir_name}')."
            )

        kebab_regex = r"^[a-z0-9]+(-[a-z0-9]+)*$"
        if not re.match(kebab_regex, name):
            self.errors.append(
                f"Field 'name' ('{name}') must be in kebab-case format "
                "(lowercase letters, digits, and single hyphens, e.g. 'token-guard')."
            )

        if len(name) > 64:
            self.errors.append(f"Field 'name' must not exceed 64 characters (current: {len(name)}).")

    def _validate_description(self, desc: Any) -> None:
        if not desc or not isinstance(desc, str):
            self.errors.append("Field 'description' is required in frontmatter and must be a string.")
            return

        desc = desc.strip()
        desc_len = len(desc)

        if desc_len < 30:
            self.warnings.append(
                f"Field 'description' is very short ({desc_len} characters). "
                "Ensure it includes clear triggers, capabilities, and activation context."
            )
        elif desc_len > 1024:
            self.errors.append(
                f"Field 'description' exceeds standard limit of 1024 characters (current: {desc_len})."
            )

        first_person_patterns = [
            r"\b(i\s+can|i\s+will|i\s+am|my|we)\b",
        ]
        for pattern in first_person_patterns:
            if re.search(pattern, desc, re.IGNORECASE):
                self.warnings.append(
                    "First-person language detected in 'description'. "
                    "Use third-person action verbs indicating role and triggers (e.g. 'Optimizes...', 'Guides...')."
                )
                break

    def _validate_relative_links(self, content: str) -> None:
        links = extract_markdown_links(content)
        for label, target, line_no in links:
            clean_target = target.split("#")[0].split("?")[0].strip()
            if not clean_target:
                continue

            resolved_path = (self.skill_dir / clean_target).resolve()
            if not resolved_path.exists():
                self.errors.append(
                    f"Line {line_no}: Broken relative link to '{target}'. "
                    f"Resource does not exist on disk at: {resolved_path}"
                )


def scan_skills_directory(directory: Path) -> List[Path]:
    """Finds all directories containing a SKILL.md file."""
    skill_dirs: List[Path] = []
    if not directory.exists() or not directory.is_dir():
        return skill_dirs

    if (directory / "SKILL.md").exists():
        skill_dirs.append(directory)
        return skill_dirs

    for item in sorted(directory.iterdir()):
        if item.is_dir() and (item / "SKILL.md").exists():
            skill_dirs.append(item)

    return skill_dirs


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Canonical validator for Agent Skills under agentskills.io standard."
    )
    parser.add_argument(
        "--skill",
        type=str,
        help="Path to specific skill directory or SKILL.md file.",
    )
    parser.add_argument(
        "--skills-dir",
        type=str,
        help="Path to directory containing multiple skills (e.g. .agents/skills).",
    )
    parser.add_argument(
        "--max-lines",
        type=int,
        default=150,
        help="Recommended max line budget for SKILL.md (default: 150).",
    )

    args = parser.parse_args()
    targets: List[Path] = []

    if args.skill:
        p = Path(args.skill).resolve()
        if not p.exists():
            print(f"[ERROR] Specified path does not exist: {p}", file=sys.stderr)
            return 1
        targets.append(p if p.is_dir() else p.parent)
    elif args.skills_dir:
        dir_p = Path(args.skills_dir).resolve()
        targets = scan_skills_directory(dir_p)
        if not targets:
            print(f"[ERROR] No skills with SKILL.md found in: {dir_p}", file=sys.stderr)
            return 1
    else:
        current_dir = Path.cwd().resolve()
        targets = scan_skills_directory(current_dir)
        if not targets:
            print(
                "[ERROR] Neither --skill nor --skills-dir specified, and no SKILL.md in current directory.",
                file=sys.stderr,
            )
            parser.print_help()
            return 1

    total_skills = len(targets)
    failed_count = 0
    warning_count = 0

    print("=" * 60)
    print(f" AGENT SKILL VALIDATOR (agentskills.io) - Validating {total_skills} skill(s)")
    print("=" * 60)

    for skill_path in targets:
        validator = SkillValidator(skill_path, max_lines_warn=args.max_lines)
        is_valid = validator.validate()

        skill_display = skill_path.name
        status = "[PASS]" if is_valid else "[FAIL]"

        print(f"\n{status} {skill_display} ({skill_path})")

        if validator.errors:
            failed_count += 1
            print("  Errors found:")
            for err in validator.errors:
                print(f"    - [ERROR] {err}")

        if validator.warnings:
            warning_count += len(validator.warnings)
            print("  Warnings:")
            for warn in validator.warnings:
                print(f"    - [WARN]  {warn}")

    print("\n" + "-" * 60)
    print(f"Summary: {total_skills} evaluated | {total_skills - failed_count} passed | {failed_count} failed | {warning_count} warning(s)")
    print("-" * 60)

    return 1 if failed_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
