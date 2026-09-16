#!/usr/bin/env python3
"""Token-Guard Persistent Invariant Memory (agy_memory.py).

Zero-Tax Local Memory Engine inspired by Gentleman-Programming/engram:
- Pure SQLite + FTS5 full-text search.
- Topic-Key upserts (family/description) to prevent memory duplication.
- Zero MCP Tool Schema Tax: accessed via deterministic CLI or Layer 2 Prefix Locking.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = Path(".local/memory.db")


class MemoryEngine:
    """Manages persistent SQLite + FTS5 memory store."""

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self.conn:
            # Main table
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project TEXT NOT NULL,
                    topic_key TEXT NOT NULL,
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    revision_count INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(project, topic_key)
                )
                """
            )
            # FTS5 Virtual table
            self.conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                    topic_key,
                    category,
                    title,
                    content,
                    content='memories',
                    content_rowid='id'
                )
                """
            )
            # Triggers to keep FTS in sync
            self.conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                    INSERT INTO memories_fts(rowid, topic_key, category, title, content)
                    VALUES (new.id, new.topic_key, new.category, new.title, new.content);
                END;
                """
            )
            self.conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                    INSERT INTO memories_fts(memories_fts, rowid, topic_key, category, title, content)
                    VALUES ('delete', old.id, old.topic_key, old.category, old.title, old.content);
                END;
                """
            )
            self.conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
                    INSERT INTO memories_fts(memories_fts, rowid, topic_key, category, title, content)
                    VALUES ('delete', old.id, old.topic_key, old.category, old.title, old.content);
                    INSERT INTO memories_fts(rowid, topic_key, category, title, content)
                    VALUES (new.id, new.topic_key, new.category, new.title, new.content);
                END;
                """
            )

    def save(
        self,
        topic_key: str,
        title: str,
        content: str,
        category: str = "decision",
        project: str = "default",
    ) -> dict[str, Any]:
        """Save memory with topic_key upsert semantics."""
        now = datetime.now(timezone.utc).isoformat()
        topic_key = topic_key.strip().lower()

        with self.conn:
            existing = self.conn.execute(
                "SELECT id, revision_count FROM memories WHERE project = ? AND topic_key = ?",
                (project, topic_key),
            ).fetchone()

            if existing:
                mem_id = existing["id"]
                new_rev = existing["revision_count"] + 1
                self.conn.execute(
                    """
                    UPDATE memories
                    SET title = ?, content = ?, category = ?, revision_count = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (title, content, category, new_rev, now, mem_id),
                )
                return {
                    "action": "updated",
                    "id": mem_id,
                    "topic_key": topic_key,
                    "revision": new_rev,
                }
            else:
                cursor = self.conn.execute(
                    """
                    INSERT INTO memories (project, topic_key, category, title, content, revision_count, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (project, topic_key, category, title, content, now, now),
                )
                return {
                    "action": "created",
                    "id": cursor.lastrowid,
                    "topic_key": topic_key,
                    "revision": 1,
                }

    def search(
        self, query: str, project: str = "default", limit: int = 5
    ) -> list[dict[str, Any]]:
        """Full-text search using FTS5 with BM25 ranking."""
        # Sanitize query for FTS5: strip non-alphanumeric except spaces
        cleaned = "".join(c if c.isalnum() or c.isspace() else " " for c in query).strip()
        if not cleaned:
            return []

        # Use prefix matching on each term
        fts_query = " ".join(f"{term}*" for term in cleaned.split())

        try:
            cursor = self.conn.execute(
                """
                SELECT m.id, m.project, m.topic_key, m.category, m.title, m.content, m.revision_count, m.updated_at,
                       bm25(memories_fts) as rank
                FROM memories_fts f
                JOIN memories m ON f.rowid = m.id
                WHERE memories_fts MATCH ? AND m.project = ?
                ORDER BY rank
                LIMIT ?
                """,
                (fts_query, project, limit),
            )
            rows = cursor.fetchall()
        except sqlite3.OperationalError:
            # Fallback to LIKE if FTS expression fails
            cursor = self.conn.execute(
                """
                SELECT id, project, topic_key, category, title, content, revision_count, updated_at, 0.0 as rank
                FROM memories
                WHERE project = ? AND (title LIKE ? OR content LIKE ? OR topic_key LIKE ?)
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (project, f"%{cleaned}%", f"%{cleaned}%", f"%{cleaned}%", limit),
            )
            rows = cursor.fetchall()

        results = []
        for r in rows:
            snippet = r["content"][:150] + "..." if len(r["content"]) > 150 else r["content"]
            results.append({
                "id": r["id"],
                "topic_key": r["topic_key"],
                "category": r["category"],
                "title": r["title"],
                "snippet": snippet,
                "revision": r["revision_count"],
                "updated_at": r["updated_at"],
            })
        return results

    def get(self, topic_key: str | None = None, mem_id: int | None = None, project: str = "default") -> dict[str, Any] | None:
        """Retrieve full memory content."""
        if topic_key:
            row = self.conn.execute(
                "SELECT * FROM memories WHERE project = ? AND topic_key = ?",
                (project, topic_key.strip().lower()),
            ).fetchone()
        elif mem_id:
            row = self.conn.execute(
                "SELECT * FROM memories WHERE id = ?", (mem_id,)
            ).fetchone()
        else:
            return None

        if not row:
            return None
        return dict(row)

    def delete(self, topic_key: str, project: str = "default") -> bool:
        """Delete memory by topic_key."""
        with self.conn:
            cursor = self.conn.execute(
                "DELETE FROM memories WHERE project = ? AND topic_key = ?",
                (project, topic_key.strip().lower()),
            )
            return cursor.rowcount > 0

    def get_project_context(self, project: str = "default", limit: int = 15) -> str:
        """Render compact Layer-2 context block of all active project memories."""
        rows = self.conn.execute(
            """
            SELECT topic_key, category, title, content, revision_count
            FROM memories
            WHERE project = ?
            ORDER BY category, topic_key
            LIMIT ?
            """,
            (project, limit),
        ).fetchall()

        if not rows:
            return ""

        lines = [f"# Project Knowledge Invariants (Memory Snapshot: {project})"]
        for r in rows:
            lines.append(f"\n### [{r['category'].upper()}] {r['topic_key']} (rev {r['revision_count']}): {r['title']}")
            lines.append(f"{r['content']}")

        return "\n".join(lines)

    def stats(self) -> dict[str, Any]:
        """Return memory repository statistics."""
        total = self.conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        categories = self.conn.execute(
            "SELECT category, COUNT(*) as cnt FROM memories GROUP BY category"
        ).fetchall()
        projects = self.conn.execute(
            "SELECT project, COUNT(*) as cnt FROM memories GROUP BY project"
        ).fetchall()

        return {
            "total_memories": total,
            "categories": {r["category"]: r["cnt"] for r in categories},
            "projects": {r["project"]: r["cnt"] for r in projects},
            "db_path": str(self.db_path),
        }

    def close(self) -> None:
        self.conn.close()


def main():
    parser = argparse.ArgumentParser(description="Antigravity Zero-Tax Persistent Memory Tool")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Path to SQLite memory database")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Command: save
    save_p = subparsers.add_parser("save", help="Save or upsert a memory")
    save_p.add_argument("--key", required=True, help="Topic key (e.g. architecture/auth-model)")
    save_p.add_argument("--title", required=True, help="Short descriptive title")
    save_p.add_argument("--content", required=True, help="Content of memory (What/Why/Learned)")
    save_p.add_argument("--category", default="decision", choices=["architecture", "bug", "decision", "pattern", "config", "discovery"])
    save_p.add_argument("--project", default="default", help="Project scope")

    # Command: search
    search_p = subparsers.add_parser("search", help="Full-text search across memories")
    search_p.add_argument("--query", required=True, help="Search query string")
    search_p.add_argument("--project", default="default", help="Project scope")
    search_p.add_argument("--limit", type=int, default=5, help="Max results")

    # Command: get
    get_p = subparsers.add_parser("get", help="Get full memory content")
    get_p.add_argument("--key", help="Topic key")
    get_p.add_argument("--id", type=int, help="Memory ID")
    get_p.add_argument("--project", default="default", help="Project scope")

    # Command: context
    ctx_p = subparsers.add_parser("context", help="Export compact Layer-2 context block")
    ctx_p.add_argument("--project", default="default", help="Project scope")
    ctx_p.add_argument("--limit", type=int, default=15, help="Max items")

    # Command: delete
    del_p = subparsers.add_parser("delete", help="Delete a memory")
    del_p.add_argument("--key", required=True, help="Topic key")
    del_p.add_argument("--project", default="default", help="Project scope")

    # Command: stats
    subparsers.add_parser("stats", help="Show memory statistics")

    args = parser.parse_args()
    engine = MemoryEngine(args.db)

    try:
        if args.command == "save":
            res = engine.save(
                topic_key=args.key,
                title=args.title,
                content=args.content,
                category=args.category,
                project=args.project,
            )
            print(json.dumps(res, indent=2))

        elif args.command == "search":
            results = engine.search(query=args.query, project=args.project, limit=args.limit)
            if not results:
                print(f"No memories matched: {args.query}")
            else:
                for r in results:
                    print(f"[{r['category'].upper()}] {r['topic_key']} (rev {r['revision']}) - {r['title']}")
                    print(f"  {r['snippet']}\n")

        elif args.command == "get":
            mem = engine.get(topic_key=args.key, mem_id=args.id, project=args.project)
            if not mem:
                print("Memory not found.")
                sys.exit(1)
            print(json.dumps(mem, indent=2))

        elif args.command == "context":
            block = engine.get_project_context(project=args.project, limit=args.limit)
            print(block if block else "# No stored memories for this project.")

        elif args.command == "delete":
            ok = engine.delete(topic_key=args.key, project=args.project)
            print(f"Deleted: {ok}")

        elif args.command == "stats":
            print(json.dumps(engine.stats(), indent=2))

    finally:
        engine.close()


if __name__ == "__main__":
    main()
