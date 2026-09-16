#!/usr/bin/env python3
"""Token Guard AST Tool.

Generates code skeletons by eliding function, method, and generator bodies
with '...' (Ellipsis) or 'pass', preserving classes, signatures, decorators,
types, and docstrings. Supports Python via ast.NodeTransformer and basic
signatures for JS/TS.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any


class PythonSkeletonTransformer(ast.NodeTransformer):
    """AST transformer that elides function, method, and generator bodies."""

    def __init__(self, style: str = "ellipsis"):
        super().__init__()
        self.style = style.lower()

    def _create_placeholder(self) -> ast.stmt:
        if self.style == "pass":
            return ast.Pass()
        return ast.Expr(value=ast.Constant(value=Ellipsis))

    def _elide_function_body(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> ast.FunctionDef | ast.AsyncFunctionDef:
        docstring_node: ast.stmt | None = None
        if node.body:
            first = node.body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                docstring_node = first

        placeholder = self._create_placeholder()
        if docstring_node is not None:
            node.body = [docstring_node, placeholder]
        else:
            node.body = [placeholder]
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        return self._elide_function_body(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        return self._elide_function_body(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        new_body: list[ast.stmt] = []
        for stmt in node.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                new_body.append(self._elide_function_body(stmt))
            elif isinstance(stmt, ast.ClassDef):
                elided_class = self.visit_ClassDef(stmt)
                if isinstance(elided_class, ast.stmt):
                    new_body.append(elided_class)
            elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
                # Class docstring
                new_body.append(stmt)
            elif isinstance(stmt, (ast.AnnAssign, ast.Assign, getattr(ast, "TypeAlias", ast.AST))):
                # Class-level type annotations and assignments
                new_body.append(stmt)
            elif isinstance(stmt, ast.Pass):
                new_body.append(stmt)
            else:
                # Keep other class-level declarations
                new_body.append(stmt)

        if not new_body:
            new_body = [self._create_placeholder()]
        node.body = new_body
        return node

    def visit_If(self, node: ast.If) -> ast.AST:
        # Elide `if __name__ == '__main__':` block
        is_main_check = False
        if isinstance(node.test, ast.Compare):
            left = node.test.left
            if isinstance(left, ast.Name) and left.id == "__name__":
                for comparator in node.test.comparators:
                    if isinstance(comparator, ast.Constant) and comparator.value == "__main__":
                        is_main_check = True
                        break

        if is_main_check:
            node.body = [self._create_placeholder()]
            node.orelse = []
            return node

        self.generic_visit(node)
        return node


def python_skeleton(code: str, style: str = "ellipsis") -> str:
    """Generate a skeleton for Python code."""
    tree = ast.parse(code)
    transformer = PythonSkeletonTransformer(style=style)
    transformed = transformer.visit(tree)
    ast.fix_missing_locations(transformed)
    return ast.unparse(transformed)


def python_symbols(code: str) -> list[dict[str, Any]]:
    """Extract symbol table from Python code."""
    tree = ast.parse(code)
    symbols: list[dict[str, Any]] = []

    def format_args(args: ast.arguments) -> str:
        parts: list[str] = []
        # Positional-only args
        for arg in getattr(args, "posonlyargs", []):
            s = arg.arg
            if arg.annotation:
                s += f": {ast.unparse(arg.annotation)}"
            parts.append(s)
        if getattr(args, "posonlyargs", []):
            parts.append("/")

        # Normal args
        defaults_offset = len(args.args) - len(args.defaults)
        for i, arg in enumerate(args.args):
            s = arg.arg
            if arg.annotation:
                s += f": {ast.unparse(arg.annotation)}"
            if i >= defaults_offset:
                default_val = args.defaults[i - defaults_offset]
                s += f" = {ast.unparse(default_val)}"
            parts.append(s)

        # *vararg
        if args.vararg:
            s = f"*{args.vararg.arg}"
            if args.vararg.annotation:
                s += f": {ast.unparse(args.vararg.annotation)}"
            parts.append(s)
        elif args.kwonlyargs:
            parts.append("*")

        # kw-only args
        kw_defaults_map = dict(zip(args.kwonlyargs, args.kw_defaults))
        for arg in args.kwonlyargs:
            s = arg.arg
            if arg.annotation:
                s += f": {ast.unparse(arg.annotation)}"
            default = kw_defaults_map.get(arg)
            if default is not None:
                s += f" = {ast.unparse(default)}"
            parts.append(s)

        # **kwarg
        if args.kwarg:
            s = f"**{args.kwarg.arg}"
            if args.kwarg.annotation:
                s += f": {ast.unparse(args.kwarg.annotation)}"
            parts.append(s)

        return f"({', '.join(parts)})"

    def is_generator_node(node: ast.AST) -> bool:
        for child in ast.walk(node):
            if isinstance(child, (ast.Yield, ast.YieldFrom)):
                return True
        return False

    def get_doc_summary(node: ast.AST) -> str:
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef, ast.ClassDef, ast.Module)):
            doc = ast.get_docstring(node)
            if doc:
                return doc.strip().splitlines()[0]
        return ""

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            bases = [ast.unparse(b) for b in node.bases]
            class_sym: dict[str, Any] = {
                "name": node.name,
                "kind": "class",
                "line": node.lineno,
                "bases": bases,
                "decorators": [ast.unparse(d) for d in node.decorator_list],
                "docstring": get_doc_summary(node),
                "methods": [],
            }
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    ret_ann = ast.unparse(item.returns) if item.returns else None
                    kind = "generator" if is_generator_node(item) else "method"
                    method_sym = {
                        "name": item.name,
                        "kind": kind,
                        "line": item.lineno,
                        "is_async": isinstance(item, ast.AsyncFunctionDef),
                        "args": format_args(item.args),
                        "returns": ret_ann,
                        "decorators": [ast.unparse(d) for d in item.decorator_list],
                        "docstring": get_doc_summary(item),
                    }
                    class_sym["methods"].append(method_sym)
            symbols.append(class_sym)

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            ret_ann = ast.unparse(node.returns) if node.returns else None
            kind = "generator" if is_generator_node(node) else "function"
            symbols.append(
                {
                    "name": node.name,
                    "kind": kind,
                    "line": node.lineno,
                    "is_async": isinstance(node, ast.AsyncFunctionDef),
                    "args": format_args(node.args),
                    "returns": ret_ann,
                    "decorators": [ast.unparse(d) for d in node.decorator_list],
                    "docstring": get_doc_summary(node),
                }
            )

        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            symbols.append(
                {
                    "name": node.target.id,
                    "kind": "variable",
                    "line": node.lineno,
                    "type": ast.unparse(node.annotation),
                }
            )

    return symbols


# ---------------------------------------------------------------------------
# JS / TS Support
# ---------------------------------------------------------------------------

JS_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}


def is_js_ts_file(path: Path | str) -> bool:
    """Check if file is a JS/TS source."""
    return Path(path).suffix.lower() in JS_EXTENSIONS


def count_code_braces(line: str, in_multiline_comment: bool = False) -> tuple[int, bool]:
    """Count { (+1) and } (-1) in JS/TS code, ignoring braces inside strings and comments."""
    delta = 0
    in_single = False
    in_double = False
    in_template = False
    in_comment = in_multiline_comment
    escape = False

    idx = 0
    n = len(line)
    while idx < n:
        ch = line[idx]
        nxt = line[idx + 1] if idx + 1 < n else ""

        if in_comment:
            if ch == "*" and nxt == "/":
                in_comment = False
                idx += 2
                continue
            idx += 1
            continue

        if escape:
            escape = False
            idx += 1
            continue

        if ch == "\\":
            escape = True
            idx += 1
            continue

        if in_single:
            if ch == "'":
                in_single = False
            idx += 1
            continue

        if in_double:
            if ch == '"':
                in_double = False
            idx += 1
            continue

        if in_template:
            if ch == "`":
                in_template = False
            idx += 1
            continue

        if ch == "/" and nxt == "/":
            break
        if ch == "/" and nxt == "*":
            in_comment = True
            idx += 2
            continue

        if ch == "'":
            in_single = True
            idx += 1
            continue
        if ch == '"':
            in_double = True
            idx += 1
            continue
        if ch == "`":
            in_template = True
            idx += 1
            continue

        if ch == "{":
            delta += 1
        elif ch == "}":
            delta -= 1

        idx += 1

    return delta, in_comment


def skip_code_block(lines: list[str], start_idx: int) -> int:
    """Advance line index until the closing brace of a JS/TS block is reached."""
    cur_idx = start_idx
    delta, in_comment = count_code_braces(lines[cur_idx])
    brace_count = delta
    n = len(lines)
    while brace_count > 0 and cur_idx + 1 < n:
        cur_idx += 1
        delta, in_comment = count_code_braces(lines[cur_idx], in_comment)
        brace_count += delta
    return cur_idx


def js_ts_skeleton(code: str) -> str:
    """Generate skeleton for JavaScript/TypeScript source code."""
    lines = code.splitlines()
    output_lines: list[str] = []
    i = 0
    n = len(lines)

    func_pattern = re.compile(
        r"^(\s*(?:export\s+(?:default\s+)?)?(?:async\s+)?function(?:\s*\*)?\s*[\w$]*\s*\([^)]*\)(?:\s*:\s*[^{]+)?)\s*\{"
    )
    class_pattern = re.compile(
        r"^(\s*(?:export\s+(?:default\s+)?)?(?:abstract\s+)?class\s+[\w$]+(?:\s+extends\s+[\w$<>.,\s]+)?(?:\s+implements\s+[\w$<>.,\s]+)?)\s*\{"
    )
    interface_pattern = re.compile(
        r"^(\s*(?:export\s+)?interface\s+[\w$]+(?:\s+extends\s+[\w$<>.,\s]+)?)\s*\{"
    )
    type_pattern = re.compile(
        r"^\s*(?:export\s+)?type\s+[\w$]+(?:\s*<[^>]+>)?\s*=.*?;?$"
    )
    method_pattern = re.compile(
        r"^(\s*(?:(?:public|private|protected|static|async|readonly|override)\s+)*[\w$]+\s*\([^)]*\)(?:\s*:\s*[^{]+)?)\s*\{"
    )
    arrow_pattern = re.compile(
        r"^(\s*(?:export\s+)?(?:const|let|var)\s+[\w$]+\s*(?::\s*[^=]+)?\s*=\s*(?:async\s+)?\([^)]*\)(?:\s*:\s*[^{=>]+)?\s*=>)\s*\{"
    )

    in_class = False
    class_indent = 0

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # Preserve comments / JSDoc
        if stripped.startswith("/**") or stripped.startswith("//") or stripped.startswith("*"):
            output_lines.append(line)
            i += 1
            continue

        # Type alias
        if type_pattern.match(line):
            output_lines.append(line)
            i += 1
            continue

        # Interface (keep body)
        m_iface = interface_pattern.match(line)
        if m_iface:
            output_lines.append(line)
            i += 1
            continue

        # Class header
        m_cls = class_pattern.match(line)
        if m_cls:
            output_lines.append(f"{m_cls.group(1)} {{")
            in_class = True
            class_indent = len(line) - len(line.lstrip())
            i += 1
            continue

        # If inside class, check for methods or closing brace
        if in_class:
            cur_indent = len(line) - len(line.lstrip())
            if stripped == "}" and cur_indent <= class_indent:
                output_lines.append(line)
                in_class = False
                i += 1
                continue

            m_meth = method_pattern.match(line)
            if m_meth and not stripped.startswith("if") and not stripped.startswith("for") and not stripped.startswith("switch"):
                sig = m_meth.group(1).rstrip()
                output_lines.append(f"{sig} {{ ... }}")
                i = skip_code_block(lines, i) + 1
                continue

            # Class fields / properties
            if (";" in stripped or ":" in stripped) and not stripped.startswith("constructor"):
                output_lines.append(line)
                i += 1
                continue

        # Function
        m_fn = func_pattern.match(line)
        if m_fn:
            sig = m_fn.group(1).rstrip()
            output_lines.append(f"{sig} {{ ... }}")
            i = skip_code_block(lines, i) + 1
            continue

        # Arrow function
        m_arrow = arrow_pattern.match(line)
        if m_arrow:
            sig = m_arrow.group(1).rstrip()
            output_lines.append(f"{sig} {{ ... }}")
            i = skip_code_block(lines, i) + 1
            continue

        # Imports & Exports
        if stripped.startswith("import ") or (stripped.startswith("export ") and "{" not in stripped):
            output_lines.append(line)
            i += 1
            continue

        if stripped == "}" and in_class:
            output_lines.append(line)
            in_class = False
            i += 1
            continue

        # For unhandled top-level line, preserve if short or definition
        if not in_class and (stripped.startswith("export ") or stripped.startswith("const ") or stripped.startswith("let ")):
            output_lines.append(line)

        i += 1

    return "\n".join(output_lines)


def js_ts_symbols(code: str) -> list[dict[str, Any]]:
    """Extract symbol table from JS/TS code."""
    symbols: list[dict[str, Any]] = []
    lines = code.splitlines()

    class_pattern = re.compile(
        r"^(?:export\s+(?:default\s+)?)?(?:abstract\s+)?class\s+([\w$]+)"
    )
    iface_pattern = re.compile(r"^(?:export\s+)?interface\s+([\w$]+)")
    type_pattern = re.compile(r"^(?:export\s+)?type\s+([\w$]+)")
    func_pattern = re.compile(
        r"^(?:export\s+(?:default\s+)?)?(?:async\s+)?function(?:\s*\*)?\s*([\w$]+)\s*(\([^)]*\))(?:\s*:\s*([^{]+))?"
    )
    arrow_pattern = re.compile(
        r"^(?:export\s+)?(?:const|let|var)\s+([\w$]+)\s*(?::\s*([^=]+))?\s*=\s*(?:async\s+)?(\([^)]*\))(?:\s*:\s*([^{=>]+))?\s*=>"
    )
    method_pattern = re.compile(
        r"^(?:(?:public|private|protected|static|async|readonly|override)\s+)*([\w$]+)\s*(\([^)]*\))(?:\s*:\s*([^{]+))?\s*\{"
    )

    current_class: str | None = None
    class_indent = 0

    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        cur_indent = len(line) - len(line.lstrip())

        if current_class and stripped == "}" and cur_indent <= class_indent:
            current_class = None
            continue

        # Class
        m_cls = class_pattern.search(stripped)
        if m_cls:
            current_class = m_cls.group(1)
            class_indent = cur_indent
            symbols.append({
                "name": current_class,
                "kind": "class",
                "line": idx,
                "signature": stripped.split("{")[0].strip(),
            })
            continue

        # Interface
        m_iface = iface_pattern.search(stripped)
        if m_iface:
            symbols.append({
                "name": m_iface.group(1),
                "kind": "interface",
                "line": idx,
                "signature": stripped.split("{")[0].strip(),
            })
            continue

        # Type
        m_type = type_pattern.search(stripped)
        if m_type:
            symbols.append({
                "name": m_type.group(1),
                "kind": "type",
                "line": idx,
                "signature": stripped,
            })
            continue

        # Function
        m_fn = func_pattern.search(stripped)
        if m_fn:
            name = m_fn.group(1)
            args = m_fn.group(2)
            ret = m_fn.group(3).strip() if m_fn.group(3) else None
            symbols.append({
                "name": name,
                "kind": "function",
                "line": idx,
                "args": args,
                "returns": ret,
                "signature": f"{name}{args}" + (f": {ret}" if ret else ""),
            })
            continue

        # Arrow function
        m_arrow = arrow_pattern.search(stripped)
        if m_arrow:
            name = m_arrow.group(1)
            args = m_arrow.group(3)
            ret = m_arrow.group(4).strip() if m_arrow.group(4) else None
            symbols.append({
                "name": name,
                "kind": "function",
                "line": idx,
                "args": args,
                "returns": ret,
                "signature": f"{name} = {args}" + (f": {ret}" if ret else ""),
            })
            continue

        # Method inside class
        if current_class:
            m_meth = method_pattern.search(stripped)
            if m_meth and not stripped.startswith("if") and not stripped.startswith("for") and not stripped.startswith("switch"):
                name = m_meth.group(1)
                args = m_meth.group(2)
                ret = m_meth.group(3).strip() if m_meth.group(3) else None
                symbols.append({
                    "name": name,
                    "kind": "method",
                    "class": current_class,
                    "line": idx,
                    "args": args,
                    "returns": ret,
                    "signature": f"{name}{args}" + (f": {ret}" if ret else ""),
                })
                continue

    return symbols




def is_go_file(path: str | Path) -> bool:
    """Check if file is a Go source file."""
    return Path(path).suffix.lower() == ".go"


def is_rust_file(path: str | Path) -> bool:
    """Check if file is a Rust source file."""
    return Path(path).suffix.lower() == ".rs"


def go_skeleton(code: str) -> str:
    """Generate skeleton for Go source code by eliding function/method bodies."""
    lines = code.splitlines()
    output_lines: list[str] = []
    i = 0
    n = len(lines)

    # Matches func (recv Type) Name(...) ... { or func Name(...) ... {
    func_pattern = re.compile(
        r"^(\s*func(?:\s*\([^)]*\))?\s+[\w$]+\s*\([^)]*\)(?:\s*(?:\([^)]*\)|[^{]+))?)\s*\{"
    )

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # Preserve comments
        if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
            output_lines.append(line)
            i += 1
            continue

        m_func = func_pattern.match(line)
        if m_func:
            indent = line[:len(line) - len(line.lstrip())]
            header = m_func.group(1).rstrip()
            end_i = skip_code_block(lines, i)
            output_lines.append(f"{header} {{")
            output_lines.append(f"{indent}\t...")
            output_lines.append(f"{indent}}}")
            i = end_i + 1
            continue

        output_lines.append(line)
        i += 1

    return "\n".join(output_lines)


def go_symbols(code: str) -> list[dict[str, Any]]:
    """Extract symbol list for Go source code."""
    symbols: list[dict[str, Any]] = []
    lines = code.splitlines()

    # func (r *Recv) Method(...) ...
    method_pattern = re.compile(
        r"^\s*func\s*\(([^)]+)\)\s+([\w$]+)\s*(\([^)]*\))(?:\s*(.+?))?(?:\s*\{|$)"
    )
    # func Name(...) ...
    func_pattern = re.compile(
        r"^\s*func\s+([\w$]+)\s*(\([^)]*\))(?:\s*(.+?))?(?:\s*\{|$)"
    )
    # type Name struct/interface/alias
    type_pattern = re.compile(
        r"^\s*type\s+([\w$]+)\s+(struct|interface|[^{;\s]+)"
    )

    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
            continue

        m_method = method_pattern.match(line)
        if m_method:
            recv = m_method.group(1).strip()
            name = m_method.group(2)
            args = m_method.group(3)
            ret = m_method.group(4) or ""
            symbols.append({
                "name": name,
                "kind": "method",
                "receiver": recv,
                "line": idx,
                "args": args,
                "returns": ret.strip(),
                "signature": f"func ({recv}) {name}{args} {ret}".strip(),
            })
            continue

        m_func = func_pattern.match(line)
        if m_func:
            name = m_func.group(1)
            args = m_func.group(2)
            ret = m_func.group(3) or ""
            symbols.append({
                "name": name,
                "kind": "function",
                "line": idx,
                "args": args,
                "returns": ret.strip(),
                "signature": f"func {name}{args} {ret}".strip(),
            })
            continue

        m_type = type_pattern.match(line)
        if m_type:
            name = m_type.group(1)
            kind = m_type.group(2)
            symbols.append({
                "name": name,
                "kind": "struct" if kind == "struct" else ("interface" if kind == "interface" else "type"),
                "line": idx,
                "signature": f"type {name} {kind}",
            })
            continue

    return symbols


def rust_skeleton(code: str) -> str:
    """Generate skeleton for Rust source code by eliding function bodies."""
    lines = code.splitlines()
    output_lines: list[str] = []
    i = 0
    n = len(lines)

    # Matches fn name(...) -> Ret {
    fn_pattern = re.compile(
        r"^(\s*(?:pub(?:\([^)]*\))?\s+)?(?:const\s+|async\s+|unsafe\s+)?(?:extern\s+\"[^\"]+\"\s+)?fn\s+[\w$]+(?:\s*<[^>]+>)?\s*\([^)]*\)(?:\s*->\s*[^{]+)?)\s*\{"
    )

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # Preserve comments and attributes
        if (
            stripped.startswith("//")
            or stripped.startswith("/*")
            or stripped.startswith("*")
            or stripped.startswith("#[")
            or stripped.startswith("#![")
        ):
            output_lines.append(line)
            i += 1
            continue

        m_fn = fn_pattern.match(line)
        if m_fn:
            indent = line[:len(line) - len(line.lstrip())]
            header = m_fn.group(1).rstrip()
            end_i = skip_code_block(lines, i)
            output_lines.append(f"{header} {{")
            output_lines.append(f"{indent}    ...")
            output_lines.append(f"{indent}}}")
            i = end_i + 1
            continue

        output_lines.append(line)
        i += 1

    return "\n".join(output_lines)


def rust_symbols(code: str) -> list[dict[str, Any]]:
    """Extract symbol list for Rust source code."""
    symbols: list[dict[str, Any]] = []
    lines = code.splitlines()

    fn_pattern = re.compile(
        r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:const\s+|async\s+|unsafe\s+)?(?:extern\s+\"[^\"]+\"\s+)?fn\s+([\w$]+)(?:\s*<[^>]+>)?\s*(\([^)]*\))(?:\s*->\s*([^{;]+))?"
    )
    struct_pattern = re.compile(
        r"^\s*(?:pub(?:\([^)]*\))?\s+)?struct\s+([\w$]+)(?:\s*<[^>]+>)?"
    )
    enum_pattern = re.compile(
        r"^\s*(?:pub(?:\([^)]*\))?\s+)?enum\s+([\w$]+)(?:\s*<[^>]+>)?"
    )
    trait_pattern = re.compile(
        r"^\s*(?:pub(?:\([^)]*\))?\s+)?trait\s+([\w$]+)(?:\s*<[^>]+>)?"
    )
    impl_pattern = re.compile(
        r"^\s*impl(?:\s*<[^>]+>)?\s+([\w$<>:, \t]+?)(?:\s+for\s+([\w$<>:, \t]+))?\s*\{"
    )

    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
            continue

        m_fn = fn_pattern.match(line)
        if m_fn:
            name = m_fn.group(1)
            args = m_fn.group(2)
            ret = (m_fn.group(3) or "").strip()
            symbols.append({
                "name": name,
                "kind": "function",
                "line": idx,
                "args": args,
                "returns": ret,
                "signature": f"fn {name}{args}" + (f" -> {ret}" if ret else ""),
            })
            continue

        m_struct = struct_pattern.match(line)
        if m_struct:
            name = m_struct.group(1)
            symbols.append({
                "name": name,
                "kind": "struct",
                "line": idx,
                "signature": f"struct {name}",
            })
            continue

        m_enum = enum_pattern.match(line)
        if m_enum:
            name = m_enum.group(1)
            symbols.append({
                "name": name,
                "kind": "enum",
                "line": idx,
                "signature": f"enum {name}",
            })
            continue

        m_trait = trait_pattern.match(line)
        if m_trait:
            name = m_trait.group(1)
            symbols.append({
                "name": name,
                "kind": "trait",
                "line": idx,
                "signature": f"trait {name}",
            })
            continue

        m_impl = impl_pattern.match(line)
        if m_impl:
            trait_name = m_impl.group(1).strip()
            for_type = (m_impl.group(2) or "").strip()
            sig = f"impl {trait_name} for {for_type}" if for_type else f"impl {trait_name}"
            symbols.append({
                "name": for_type if for_type else trait_name,
                "kind": "impl",
                "line": idx,
                "signature": sig,
            })
            continue

    return symbols


def generate_skeleton(source_path: str | Path, style: str = "ellipsis") -> str:
    """Generate code skeleton for a given file."""
    path = Path(source_path)
    if not path.exists():
        raise FileNotFoundError(f"Source file not found: {source_path}")

    code = path.read_text(encoding="utf-8")
    if is_js_ts_file(path):
        return js_ts_skeleton(code)
    if is_go_file(path):
        return go_skeleton(code)
    if is_rust_file(path):
        return rust_skeleton(code)
    return python_skeleton(code, style=style)


def extract_symbols(source_path: str | Path) -> list[dict[str, Any]]:
    """Extract symbol list for a given file."""
    path = Path(source_path)
    if not path.exists():
        raise FileNotFoundError(f"Source file not found: {source_path}")

    code = path.read_text(encoding="utf-8")
    if is_js_ts_file(path):
        return js_ts_symbols(code)
    if is_go_file(path):
        return go_symbols(code)
    if is_rust_file(path):
        return rust_symbols(code)
    return python_symbols(code)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Token Guard AST Skeleton and Symbol Extractor"
    )
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to execute")

    # skeleton command
    p_skeleton = subparsers.add_parser("skeleton", help="Generate code skeleton")
    p_skeleton.add_argument("--source", "-s", required=True, help="Path to source file")
    p_skeleton.add_argument("--out", "-o", help="Output file path (default stdout)")
    p_skeleton.add_argument(
        "--style",
        choices=["ellipsis", "pass"],
        default="ellipsis",
        help="Elision placeholder style (default 'ellipsis')",
    )

    # symbols command
    p_symbols = subparsers.add_parser("symbols", help="Extract symbol table")
    p_symbols.add_argument("--source", "-s", required=True, help="Path to source file")
    p_symbols.add_argument("--json", action="store_true", help="Output in JSON format")
    p_symbols.add_argument("--out", "-o", help="Output file path (default stdout)")

    # Support shorthand: `agy_ast.py <file>`
    if len(sys.argv) == 2 and not sys.argv[1].startswith("-") and sys.argv[1] not in ("skeleton", "symbols"):
        source = sys.argv[1]
        try:
            res = generate_skeleton(source)
            print(res)
            return 0
        except Exception as e:
            sys.stderr.write(f"Error: {e}\n")
            return 1

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    try:
        if args.command == "skeleton":
            result = generate_skeleton(args.source, style=args.style)
            if args.out:
                Path(args.out).write_text(result, encoding="utf-8")
            else:
                print(result)
            return 0

        elif args.command == "symbols":
            symbols = extract_symbols(args.source)
            if args.json:
                result = json.dumps(symbols, indent=2)
            else:
                # Format readable table
                lines: list[str] = [f"Symbols in {args.source}:"]
                for sym in symbols:
                    kind = sym.get("kind", "symbol")
                    line = sym.get("line", "?")
                    name = sym.get("name", "")
                    doc = sym.get("docstring", "")
                    doc_str = f" - {doc}" if doc else ""
                    if "signature" in sym:
                        lines.append(f"  L{line:<4} [{kind:<9}] {sym['signature']}{doc_str}")
                    elif "methods" in sym:
                        bases_str = f"({', '.join(sym.get('bases', []))})" if sym.get("bases") else ""
                        lines.append(f"  L{line:<4} [class    ] {name}{bases_str}{doc_str}")
                        for m in sym["methods"]:
                            m_line = m.get("line", "?")
                            m_sig = f"{m['name']}{m.get('args', '')}"
                            if m.get("returns"):
                                m_sig += f" -> {m['returns']}"
                            m_doc = f" - {m['docstring']}" if m.get("docstring") else ""
                            lines.append(f"    L{m_line:<4} [{m['kind']:<9}] {m_sig}{m_doc}")
                    else:
                        sig = f"{name}{sym.get('args', '')}"
                        if sym.get("returns"):
                            sig += f" -> {sym['returns']}"
                        lines.append(f"  L{line:<4} [{kind:<9}] {sig}{doc_str}")
                result = "\n".join(lines)

            if args.out:
                Path(args.out).write_text(result, encoding="utf-8")
            else:
                print(result)
            return 0

    except Exception as exc:
        sys.stderr.write(f"Error: {exc}\n")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
