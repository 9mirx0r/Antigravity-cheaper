#!/usr/bin/env python3
"""Token Guard RepoMap Tool (agy_repomap.py).

Generates a compact, global architectural repository map using Tree-sitter
and AST symbol analysis combined with Personalized PageRank (PPR).
Fits symbol hierarchies within a strict token budget (default 1,200 tokens)
so agents have global workspace awareness on Turn 1 without reading full files.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import math
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Default ignore directories
DEFAULT_IGNORES = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".venv",
    "venv",
    "node_modules",
    "target",
    "dist",
    "build",
    ".gemini",
    ".idea",
    ".vscode",
}


class GitIgnoreMatcher:
    """Lightweight, dependency-free .gitignore matcher."""

    def __init__(self, root_dir: Path):
        self.root_dir = root_dir.resolve()
        self.rules: List[Tuple[bool, str, bool]] = []
        self._load_root_gitignore()

    def _load_root_gitignore(self) -> None:
        gi_path = self.root_dir / ".gitignore"
        if not gi_path.is_file():
            return
        try:
            content = gi_path.read_text(encoding="utf-8", errors="ignore")
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                is_neg = line.startswith("!")
                if is_neg:
                    line = line[1:].strip()
                dir_only = line.endswith("/")
                if dir_only:
                    line = line[:-1]
                self.rules.append((is_neg, line, dir_only))
        except Exception:
            pass

    def is_ignored(self, path: Path, is_dir: bool = False) -> bool:
        try:
            rel = path.resolve().relative_to(self.root_dir).as_posix()
        except ValueError:
            rel = path.as_posix()

        ignored = False
        parts = rel.split("/")

        for is_neg, pat, dir_only in self.rules:
            if dir_only and not is_dir:
                continue

            match = False
            if "/" in pat:
                clean_pat = pat.lstrip("/")
                if fnmatch.fnmatch(rel, clean_pat) or fnmatch.fnmatch(rel, f"{clean_pat}/*"):
                    match = True
            else:
                if any(fnmatch.fnmatch(part, pat) for part in parts):
                    match = True

            if match:
                ignored = not is_neg

        return ignored

# Common programming file extensions
CODE_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
}


def estimate_tokens(text: str) -> int:
    """Accurate BPE token estimate for code and identifiers (~3.7 chars/token)."""
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 3.7))


class SymbolDef:
    """Represents a symbol definition (class, function, method)."""

    def __init__(
        self,
        name: str,
        kind: str,
        line: int,
        signature: str = "",
        docstring: str = "",
        parent: Optional[str] = None,
        refs: Optional[Set[str]] = None,
    ):
        self.name = name
        self.kind = kind  # 'class', 'function', 'method'
        self.line = line
        self.signature = signature
        self.docstring = docstring
        self.parent = parent  # Name of parent class if method
        self.refs: Set[str] = refs if refs is not None else set()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "line": self.line,
            "signature": self.signature,
            "docstring": self.docstring,
            "parent": self.parent,
            "refs": sorted(list(self.refs)),
        }


class FileSymbols:
    """Symbol definitions and identifier references for a single source file."""

    def __init__(self, rel_path: str, lang: str):
        self.rel_path = rel_path.replace("\\", "/")
        self.lang = lang
        self.defs: List[SymbolDef] = []
        self.refs: Set[str] = set()

    def def_names(self) -> Set[str]:
        return {d.name for d in self.defs}


class PythonASTExtractor(ast.NodeVisitor):
    """Extracts symbol definitions and identifier references from Python AST."""

    def __init__(self):
        super().__init__()
        self.defs: List[SymbolDef] = []
        self.refs: Set[str] = set()
        self.current_class: Optional[str] = None
        self.symbol_stack: List[SymbolDef] = []

    def _extract_docstring(self, node: ast.AST) -> str:
        doc = ast.get_docstring(node) or ""
        if doc:
            first_line = doc.strip().split("\n")[0].strip()
            return first_line[:80]
        return ""

    def _format_signature(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        try:
            arg_list = []
            for arg in node.args.args:
                if self.current_class and arg.arg == "self":
                    continue
                a = arg.arg
                if arg.annotation:
                    a += f": {ast.unparse(arg.annotation)}"
                arg_list.append(a)
            args_str = ", ".join(arg_list)
        except Exception:
            args_str = "..."

        ret_str = ""
        if node.returns:
            try:
                ret_str = f" -> {ast.unparse(node.returns)}"
            except Exception:
                pass

        prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
        return f"{prefix}{node.name}({args_str}){ret_str}"

    def visit_ClassDef(self, node: ast.ClassDef):
        sdef = SymbolDef(
            name=node.name,
            kind="class",
            line=node.lineno,
            signature=f"class {node.name}",
            docstring=self._extract_docstring(node),
            parent=None,
        )
        self.defs.append(sdef)
        old_class = self.current_class
        self.current_class = node.name
        self.symbol_stack.append(sdef)
        self.generic_visit(node)
        self.symbol_stack.pop()
        self.current_class = old_class

    def visit_FunctionDef(self, node: ast.FunctionDef):
        kind = "method" if self.current_class else "function"
        sdef = SymbolDef(
            name=node.name,
            kind=kind,
            line=node.lineno,
            signature=self._format_signature(node),
            docstring=self._extract_docstring(node),
            parent=self.current_class,
        )
        self.defs.append(sdef)
        self.symbol_stack.append(sdef)
        self.generic_visit(node)
        self.symbol_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        kind = "method" if self.current_class else "function"
        sdef = SymbolDef(
            name=node.name,
            kind=kind,
            line=node.lineno,
            signature=self._format_signature(node),
            docstring=self._extract_docstring(node),
            parent=self.current_class,
        )
        self.defs.append(sdef)
        self.symbol_stack.append(sdef)
        self.generic_visit(node)
        self.symbol_stack.pop()

    def visit_Name(self, node: ast.Name):
        if isinstance(node.ctx, ast.Load):
            self.refs.add(node.id)
            if self.symbol_stack:
                self.symbol_stack[-1].refs.add(node.id)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        self.refs.add(node.attr)
        if self.symbol_stack:
            self.symbol_stack[-1].refs.add(node.attr)
        self.generic_visit(node)



def extract_python_symbols(code: str, rel_path: str) -> FileSymbols:
    """Parse Python source code into FileSymbols."""
    fs = FileSymbols(rel_path, "python")
    try:
        tree = ast.parse(code)
        extractor = PythonASTExtractor()
        extractor.visit(tree)
        fs.defs = extractor.defs
        fs.refs = extractor.refs
    except Exception:
        return extract_regex_symbols(code, rel_path, "python")
    return fs


def extract_regex_symbols(code: str, rel_path: str, lang: str) -> FileSymbols:
    """Regex-based symbol extractor for JS/TS/Rust/Go and fallback Python."""
    fs = FileSymbols(rel_path, lang)
    lines = code.splitlines()

    class_pat = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?class\s+([A-Za-z0-9_]+)")
    func_pat = re.compile(
        r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z0-9_]+)\s*\((.*?)\)"
    )
    arrow_pat = re.compile(
        r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z0-9_]+)\s*=\s*(?:async\s*)?\([^)]*\)\s*(?::\s*[^=]+)?\s*=>"
    )
    ts_interface_pat = re.compile(r"^\s*(?:export\s+)?interface\s+([A-Za-z0-9_]+)")
    ts_type_pat = re.compile(r"^\s*(?:export\s+)?type\s+([A-Za-z0-9_]+)\s*(?:<[^>]+>)?\s*=")
    rust_fn_pat = re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+([A-Za-z0-9_]+)")
    rust_struct_pat = re.compile(r"^\s*(?:pub\s+)?(?:struct|enum|trait)\s+([A-Za-z0-9_]+)")
    go_func_pat = re.compile(r"^\s*func\s+(?:\([^)]+\)\s+)?([A-Za-z0-9_]+)")
    go_type_pat = re.compile(r"^\s*type\s+([A-Za-z0-9_]+)\s+(?:struct|interface)")

    for idx, line in enumerate(lines, 1):
        m = class_pat.search(line) or rust_struct_pat.search(line) or go_type_pat.search(line)
        if m:
            fs.defs.append(
                SymbolDef(
                    name=m.group(1),
                    kind="class",
                    line=idx,
                    signature=line.strip()[:100],
                )
            )
            continue

        m = ts_interface_pat.search(line) or ts_type_pat.search(line)
        if m:
            fs.defs.append(
                SymbolDef(
                    name=m.group(1),
                    kind="class",
                    line=idx,
                    signature=line.strip()[:100],
                )
            )
            continue

        m = func_pat.search(line) or arrow_pat.search(line) or rust_fn_pat.search(line) or go_func_pat.search(line)
        if m:
            fs.defs.append(
                SymbolDef(
                    name=m.group(1),
                    kind="function",
                    line=idx,
                    signature=line.strip()[:100],
                )
            )
            continue

    tokens = set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b", code))
    fs.refs = tokens
    return fs


def parse_source_file(file_path: Path, root_path: Path) -> Optional[FileSymbols]:
    """Parse a single source file into definitions and references."""
    ext = file_path.suffix.lower()
    if ext not in CODE_EXTENSIONS:
        return None

    lang = CODE_EXTENSIONS[ext]
    rel_path = str(file_path.relative_to(root_path)).replace("\\", "/")

    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None

    if lang == "python":
        return extract_python_symbols(content, rel_path)
    else:
        return extract_regex_symbols(content, rel_path, lang)


class RepoMapGraph:
    """Builds symbol reference graph and computes Personalized PageRank."""

    def __init__(self, root_dir: str | Path):
        self.root_dir = Path(root_dir).resolve()
        self.files: Dict[str, FileSymbols] = {}
        self.def_to_files: Dict[str, Set[str]] = defaultdict(set)
        self.gitignore = GitIgnoreMatcher(self.root_dir)

    def scan(self) -> None:
        """Scan directory and index all code files respecting .gitignore."""
        for root, dirs, files in os.walk(self.root_dir):
            dirs[:] = [
                d
                for d in dirs
                if d not in DEFAULT_IGNORES
                and not d.startswith(".")
                and not self.gitignore.is_ignored(Path(root) / d, is_dir=True)
            ]
            for file in files:
                file_path = Path(root) / file
                if self.gitignore.is_ignored(file_path, is_dir=False):
                    continue
                fs = parse_source_file(file_path, self.root_dir)
                if fs and (fs.defs or fs.refs):
                    self.files[fs.rel_path] = fs
                    for def_name in fs.def_names():
                        self.def_to_files[def_name].add(fs.rel_path)

    def build_adj_matrix(self) -> Tuple[List[str], Dict[str, Dict[str, float]]]:
        """Build directed adjacency graph with Ambiguity-Discounted Edge Weights.

        W(f_i, f_j) = sum_{s in Refs(f_i) & Defs(f_j)} 1 / |FilesDef(s)|
        """
        nodes = sorted(self.files.keys())
        adj: Dict[str, Dict[str, float]] = {u: defaultdict(float) for u in nodes}

        for src, fs_src in self.files.items():
            for ref_name in fs_src.refs:
                target_files = self.def_to_files.get(ref_name, set())
                if not target_files:
                    continue
                weight = 1.0 / len(target_files)
                for dst in target_files:
                    if src != dst:
                        adj[src][dst] += weight

        return nodes, adj

    def compute_pagerank(
        self,
        focus_files: Optional[List[str]] = None,
        damping: float = 0.85,
        max_iter: int = 80,
        tol: float = 1e-6,
    ) -> Dict[str, float]:
        """Compute Personalized PageRank using power iteration."""
        nodes, adj = self.build_adj_matrix()
        N = len(nodes)
        if N == 0:
            return {}

        v: Dict[str, float] = {}
        norm_focus: Set[str] = set()
        if focus_files:
            for f in focus_files:
                norm = f.replace("\\", "/").lstrip("./")
                if norm in self.files:
                    norm_focus.add(norm)

        if norm_focus:
            focus_val = 1.0 / len(norm_focus)
            for n in nodes:
                v[n] = focus_val if n in norm_focus else 0.0
        else:
            uniform_val = 1.0 / N
            for n in nodes:
                v[n] = uniform_val

        out_weights: Dict[str, float] = {}
        for u in nodes:
            out_weights[u] = sum(adj[u].values())

        p: Dict[str, float] = {u: v[u] for u in nodes}

        for _ in range(max_iter):
            p_next: Dict[str, float] = {u: (1.0 - damping) * v[u] for u in nodes}
            dangling_sum = 0.0

            for u in nodes:
                total_out = out_weights[u]
                if total_out > 0:
                    flow = damping * p[u] / total_out
                    for dst, w in adj[u].items():
                        p_next[dst] += flow * w
                else:
                    dangling_sum += p[u]

            if dangling_sum > 0:
                dangling_factor = damping * dangling_sum
                for u in nodes:
                    p_next[u] += dangling_factor * v[u]

            diff = sum(abs(p_next[u] - p[u]) for u in nodes)
            p = p_next
            if diff < tol:
                break

        return p

    def format_file_tree(
        self,
        rel_path: str,
        detail_level: int = 2,
    ) -> str:
        """Format symbol tree for a file given detail level (2: full, 1: sig, 0: names)."""
        fs = self.files.get(rel_path)
        if not fs or not fs.defs:
            return f"{rel_path}:\n  (no symbols)"

        lines = [f"{rel_path}:"]

        classes: Dict[str, List[SymbolDef]] = defaultdict(list)
        top_level: List[SymbolDef] = []

        for d in fs.defs:
            if d.kind == "class":
                classes[d.name] = []
            elif d.parent and d.parent in classes:
                classes[d.parent].append(d)
            else:
                top_level.append(d)

        for cls_name, methods in sorted(classes.items()):
            cls_def = next((d for d in fs.defs if d.name == cls_name), None)
            doc = f'  # "{cls_def.docstring}"' if (detail_level >= 2 and cls_def and cls_def.docstring) else ""
            lines.append(f"  class {cls_name}:{doc}")

            if detail_level == 0:
                lines.append("    ...")
            else:
                for m in methods:
                    if detail_level >= 2:
                        doc_m = f'  # "{m.docstring}"' if m.docstring else ""
                        lines.append(f"    {m.signature}:{doc_m}")
                    else:
                        lines.append(f"    {m.signature}: ...")

        for f in top_level:
            if detail_level == 0:
                lines.append(f"  def {f.name}(...)")
            elif detail_level == 1:
                lines.append(f"  {f.signature}: ...")
            else:
                doc_f = f'  # "{f.docstring}"' if f.docstring else ""
                lines.append(f"  {f.signature}:{doc_f}")

        return "\n".join(lines)

    def render_map(
        self,
        focus_files: Optional[List[str]] = None,
        budget_tokens: int = 1200,
    ) -> str:
        """Render ranked repository map within budget using binary search tuning."""
        if not self.files:
            return "# Empty repository (no supported source files found)"

        ranks = self.compute_pagerank(focus_files=focus_files)
        ranked_files = sorted(ranks.keys(), key=lambda f: ranks[f], reverse=True)

        header = f"# Repository Map (PPR Budget: ~{budget_tokens} tokens)\n"
        budget_remaining = budget_tokens - estimate_tokens(header)

        for detail in (2, 1, 0):
            blocks = []
            cur_tokens = 0
            for f in ranked_files:
                block = self.format_file_tree(f, detail_level=detail)
                b_tokens = estimate_tokens(block + "\n")
                if cur_tokens + b_tokens <= budget_remaining:
                    blocks.append(block)
                    cur_tokens += b_tokens
                else:
                    break

            if len(blocks) >= min(4, len(ranked_files)) or detail == 0:
                result = header + "\n" + "\n\n".join(blocks)
                return result

        minimal_blocks = [self.format_file_tree(f, detail_level=0) for f in ranked_files[:10]]
        return header + "\n" + "\n\n".join(minimal_blocks)

    def get_symbol_subgraph(self, symbol_name: str) -> Dict[str, Any]:
        """Find where symbol is defined and which files reference it."""
        defs = []
        for path, fs in self.files.items():
            for d in fs.defs:
                if d.name == symbol_name:
                    defs.append({"file": path, "symbol": d.to_dict()})

        callers = []
        for path, fs in self.files.items():
            if symbol_name in fs.refs:
                callers.append(path)

        return {
            "symbol": symbol_name,
            "definitions": defs,
            "referencing_files": sorted(callers),
        }


    def build_symbol_graph(self) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Set[str]]]:
        """Build directed symbol-to-symbol dependency graph."""
        symbols_meta: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        adj: Dict[str, Set[str]] = defaultdict(set)
        all_def_names: Set[str] = set()

        for path, fs in self.files.items():
            for d in fs.defs:
                all_def_names.add(d.name)
                symbols_meta[d.name].append({
                    "name": d.name,
                    "file": path,
                    "line": d.line,
                    "kind": d.kind,
                    "signature": d.signature,
                    "docstring": d.docstring,
                    "parent": d.parent,
                    "refs": sorted(list(d.refs)),
                })

        for path, fs in self.files.items():
            for d in fs.defs:
                for ref in d.refs:
                    if ref in all_def_names and ref != d.name:
                        adj[d.name].add(ref)
                if d.parent and d.parent in all_def_names:
                    adj[d.parent].add(d.name)

        return symbols_meta, adj

    def find_causal_path(
        self, start_symbol: str, end_symbol: str, max_depth: int = 8
    ) -> Optional[List[Dict[str, Any]]]:
        """Find directed shortest path between start_symbol and end_symbol."""
        symbols_meta, adj = self.build_symbol_graph()

        if start_symbol not in symbols_meta and end_symbol not in symbols_meta:
            return None

        # 1. Forward BFS: start -> end
        queue = [(start_symbol, [start_symbol])]
        visited = {start_symbol}
        found_path: Optional[List[str]] = None

        while queue:
            curr, path = queue.pop(0)
            if curr == end_symbol:
                found_path = path
                break
            if len(path) > max_depth:
                continue
            for neighbor in adj.get(curr, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))

        # 2. Reverse BFS: end -> start
        if not found_path:
            queue = [(end_symbol, [end_symbol])]
            visited = {end_symbol}
            while queue:
                curr, path = queue.pop(0)
                if curr == start_symbol:
                    found_path = list(reversed(path))
                    break
                if len(path) > max_depth:
                    continue
                for neighbor in adj.get(curr, set()):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append((neighbor, path + [neighbor]))

        # 3. Undirected fallback BFS
        if not found_path:
            undirected: Dict[str, Set[str]] = defaultdict(set)
            for u, nbrs in adj.items():
                for v in nbrs:
                    undirected[u].add(v)
                    undirected[v].add(u)
            queue = [(start_symbol, [start_symbol])]
            visited = {start_symbol}
            while queue:
                curr, path = queue.pop(0)
                if curr == end_symbol:
                    found_path = path
                    break
                if len(path) > max_depth:
                    continue
                for neighbor in undirected.get(curr, set()):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append((neighbor, path + [neighbor]))

        if not found_path:
            return None

        result = []
        for sym in found_path:
            meta_list = symbols_meta.get(sym, [])
            primary = meta_list[0] if meta_list else {"name": sym, "file": "unknown", "line": 0, "signature": sym}
            result.append(primary)
        return result

    def find_causal_chain_for_query(
        self, query: str, max_depth: int = 4
    ) -> List[Dict[str, Any]]:
        """Identify symbols mentioned in query/error and trace their caller lineages."""
        symbols_meta, adj = self.build_symbol_graph()
        tokens = set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b", query))
        matched_symbols = [t for t in tokens if t in symbols_meta]

        if not matched_symbols:
            return []

        reverse_adj: Dict[str, Set[str]] = defaultdict(set)
        for u, nbrs in adj.items():
            for v in nbrs:
                reverse_adj[v].add(u)

        chains = []
        for sym in matched_symbols:
            callers = []
            visited = {sym}
            queue = [(sym, 0)]
            while queue:
                curr, depth = queue.pop(0)
                if depth > 0 and curr in symbols_meta:
                    callers.append(symbols_meta[curr][0])
                if depth >= max_depth:
                    continue
                for caller in reverse_adj.get(curr, set()):
                    if caller not in visited:
                        visited.add(caller)
                        queue.append((caller, depth + 1))

            chains.append({
                "target_symbol": symbols_meta[sym][0],
                "upstream_callers": callers[:5],
                "downstream_dependencies": [
                    symbols_meta[callee][0] for callee in adj.get(sym, set()) if callee in symbols_meta
                ][:5],
            })
        return chains


def main():
    parser = argparse.ArgumentParser(description="Antigravity Personalized PageRank RepoMap")
    subparsers = parser.add_subparsers(dest="command", required=True)

    map_p = subparsers.add_parser("map", help="Generate budget-fitted repository map")
    map_p.add_argument("--root", required=True, help="Root directory of repository")
    map_p.add_argument("--budget", type=int, default=1200, help="Target token budget (default: 1200)")
    map_p.add_argument("--focus", action="append", help="Focus file(s) for Personalized PageRank")
    map_p.add_argument("--out", help="Optional output file path")

    sub_p = subparsers.add_parser("subgraph", help="Query symbol definitions and reference subgraph")
    sub_p.add_argument("--root", required=True, help="Root directory of repository")
    sub_p.add_argument("--symbol", required=True, help="Symbol name to query")

    sum_p = subparsers.add_parser("summary", help="Summary statistics of repository symbols")
    sum_p.add_argument("--root", required=True, help="Root directory of repository")

    path_p = subparsers.add_parser("path", help="Compute shortest directed causal path between two symbols")
    path_p.add_argument("--root", required=True, help="Root directory of repository")
    path_p.add_argument("--from-symbol", dest="from_sym", required=True, help="Starting symbol name")
    path_p.add_argument("--to-symbol", dest="to_sym", required=True, help="Target symbol name")
    path_p.add_argument("--json", action="store_true", help="Output raw JSON")

    causal_p = subparsers.add_parser("causal", help="Resolve causal lineage from error message or query")
    causal_p.add_argument("--root", required=True, help="Root directory of repository")
    causal_p.add_argument("--query", required=True, help="Error message, stack trace snippet, or query")
    causal_p.add_argument("--json", action="store_true", help="Output raw JSON")

    args = parser.parse_args()

    graph = RepoMapGraph(args.root)
    graph.scan()

    if args.command == "map":
        output = graph.render_map(focus_files=args.focus, budget_tokens=args.budget)
        if args.out:
            Path(args.out).write_text(output, encoding="utf-8")
            print(f"RepoMap written to {args.out} (~{estimate_tokens(output)} tokens)")
        else:
            print(output)

    elif args.command == "subgraph":
        res = graph.get_symbol_subgraph(args.symbol)
        print(json.dumps(res, indent=2))

    elif args.command == "summary":
        nodes, adj = graph.build_adj_matrix()
        total_defs = sum(len(fs.defs) for fs in graph.files.values())
        print(
            json.dumps(
                {
                    "root": str(graph.root_dir),
                    "total_files": len(graph.files),
                    "total_symbols": total_defs,
                    "graph_nodes": len(nodes),
                    "graph_edges": sum(len(edges) for edges in adj.values()),
                },
                indent=2,
            )
        )

    elif args.command == "path":
        res = graph.find_causal_path(args.from_sym, args.to_sym)
        if not res:
            print(f"No causal path found between '{args.from_sym}' and '{args.to_sym}'.")
            sys.exit(1)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            path_str = " -> ".join(f"[{s['name']}]" for s in res)
            print(f"Causal Path: {path_str}\n")
            for idx, item in enumerate(res, 1):
                sig = item.get("signature") or item["name"]
                print(f"  {idx}. {item['name']} ({item.get('file', '?')}:{item.get('line', '?')})")
                print(f"     {sig}")

    elif args.command == "causal":
        res = graph.find_causal_chain_for_query(args.query)
        if not res:
            print(f"No indexed symbols identified in query: {args.query}")
            sys.exit(1)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            for chain in res:
                tgt = chain["target_symbol"]
                print(f"Causal Root Target: [{tgt['name']}] ({tgt.get('file', '?')}:{tgt.get('line', '?')})")
                if chain["upstream_callers"]:
                    print("  Upstream Callers:")
                    for caller in chain["upstream_callers"]:
                        print(f"    <- {caller['name']} ({caller.get('file', '?')}:{caller.get('line', '?')})")
                if chain["downstream_dependencies"]:
                    print("  Downstream Callees:")
                    for callee in chain["downstream_dependencies"]:
                        print(f"    -> {callee['name']} ({callee.get('file', '?')}:{callee.get('line', '?')})")


if __name__ == "__main__":
    main()
