"""
Storage engine for Hextech Oracle (Aegis-LoL).
SQLite 3 storage with Write-Ahead Logging (WAL) and index optimization.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import sqlite3
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class HextechDatabase:
    """SQLite Database manager for Hextech Oracle with WAL mode and indexing."""

    def __init__(
        self,
        db_path: str = ":memory:",
        auto_seed: bool = True,
        seed_file_path: Optional[str] = None,
    ) -> None:
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._init_connection()
        self.initialize_schema()

        if auto_seed:
            self._check_and_auto_seed(seed_file_path)

    def _init_connection(self) -> None:
        """Initialize SQLite connection and configure PRAGMAs."""
        self._conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            timeout=10.0,
        )
        self._conn.row_factory = sqlite3.Row

        # Enable WAL mode for file-based databases
        if self.db_path != ":memory:" and not self.db_path.startswith("file:"):
            try:
                self._conn.execute("PRAGMA journal_mode = WAL;")
                self._conn.execute("PRAGMA synchronous = NORMAL;")
            except sqlite3.Error as err:
                logger.warning("Could not set WAL pragma: %s", err)

        try:
            self._conn.execute("PRAGMA foreign_keys = ON;")
            self._conn.execute("PRAGMA temp_store = MEMORY;")
        except sqlite3.Error:
            pass

    @property
    def connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._init_connection()
        assert self._conn is not None
        return self._conn

    def initialize_schema(self) -> None:
        """Idempotent table and index creation."""
        cursor = self.connection.cursor()
        cursor.executescript(
            """
            CREATE TABLE IF NOT EXISTS champions (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                title TEXT DEFAULT '',
                roles TEXT DEFAULT '',
                attack INTEGER DEFAULT 5,
                defense INTEGER DEFAULT 5,
                magic INTEGER DEFAULT 5,
                difficulty INTEGER DEFAULT 5,
                win_rate REAL DEFAULT 0.50,
                ban_rate REAL DEFAULT 0.05,
                damage_type TEXT DEFAULT 'AD',
                cc INTEGER DEFAULT 50,
                engage INTEGER DEFAULT 50,
                poke INTEGER DEFAULT 50,
                waveclear INTEGER DEFAULT 50,
                scaling INTEGER DEFAULT 50
            );

            CREATE TABLE IF NOT EXISTS synergies (
                champ_a TEXT NOT NULL,
                champ_b TEXT NOT NULL,
                synergy_score REAL NOT NULL,
                combo_type TEXT DEFAULT '',
                PRIMARY KEY(champ_a, champ_b)
            );

            CREATE TABLE IF NOT EXISTS counters (
                champion TEXT NOT NULL,
                counter_champion TEXT NOT NULL,
                advantage_delta REAL NOT NULL,
                PRIMARY KEY(champion, counter_champion)
            );

            CREATE TABLE IF NOT EXISTS summoner_cache (
                puuid TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                tag_line TEXT NOT NULL,
                level INTEGER DEFAULT 1,
                tier TEXT DEFAULT 'UNRANKED',
                rank TEXT DEFAULT 'I',
                lp INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                last_updated REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS match_history (
                match_id TEXT NOT NULL,
                puuid TEXT NOT NULL,
                champion TEXT NOT NULL,
                kills INTEGER DEFAULT 0,
                deaths INTEGER DEFAULT 0,
                assists INTEGER DEFAULT 0,
                cs INTEGER DEFAULT 0,
                vision_score INTEGER DEFAULT 0,
                win INTEGER DEFAULT 0,
                duration INTEGER DEFAULT 0,
                PRIMARY KEY(match_id, puuid)
            );

            -- Indexes for fast lookups
            CREATE INDEX IF NOT EXISTS idx_match_history_puuid ON match_history(puuid);
            CREATE INDEX IF NOT EXISTS idx_champions_name ON champions(name);
            CREATE INDEX IF NOT EXISTS idx_synergies_pair ON synergies(champ_a, champ_b);
            CREATE INDEX IF NOT EXISTS idx_counters_pair ON counters(champion, counter_champion);
            """
        )
        self.connection.commit()

    def _default_seed_path(self) -> Path:
        """Find the default seed_data.json path."""
        # Check standard project locations
        possible_paths = [
            Path(__file__).resolve().parent.parent.parent / "mock_data" / "seed_data.json",
            Path(__file__).resolve().parent.parent.parent.parent / "mock_data" / "seed_data.json",
            Path.cwd() / "mock_data" / "seed_data.json",
            Path.cwd().parent / "mock_data" / "seed_data.json",
            Path.cwd().parent.parent / "mock_data" / "seed_data.json",
        ]
        for path in possible_paths:
            if path.exists():
                return path
        return possible_paths[0]

    def _check_and_auto_seed(self, seed_file_path: Optional[str] = None) -> None:
        """Auto seed database if champions table is empty."""
        cursor = self.connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM champions;")
        count = cursor.fetchone()[0]
        if count == 0:
            target_path = Path(seed_file_path) if seed_file_path else self._default_seed_path()
            if target_path.exists():
                self.seed_from_file(str(target_path))

    def seed_from_file(self, file_path: str) -> None:
        """Load JSON seed file and populate baseline meta tables."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Seed file not found: {file_path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        champions_data = data.get("champions", [])
        synergies_data = data.get("synergies", [])
        counters_data = data.get("counters", [])

        self.seed_static_data(champions_data, synergies_data, counters_data)

        # Also seed mock summoner if present
        mock_state = data.get("mock_lcu_state", {})
        active_summoner = mock_state.get("active_summoner")
        if active_summoner:
            self.upsert_summoner(active_summoner)

    def seed_static_data(
        self,
        champions_data: List[Dict[str, Any]],
        synergies_data: List[Dict[str, Any]],
        counters_data: List[Dict[str, Any]],
    ) -> None:
        """Populate champions, synergies, and counters tables."""
        cursor = self.connection.cursor()

        # Seed champions
        for c in champions_data:
            cursor.execute(
                """
                INSERT OR REPLACE INTO champions (
                    id, name, title, roles, attack, defense, magic,
                    difficulty, win_rate, ban_rate, damage_type,
                    cc, engage, poke, waveclear, scaling
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    c["id"],
                    c.get("name", c["id"]),
                    c.get("title", ""),
                    c.get("roles", ""),
                    int(c.get("attack", 5)),
                    int(c.get("defense", 5)),
                    int(c.get("magic", 5)),
                    int(c.get("difficulty", 5)),
                    float(c.get("win_rate", 0.50)),
                    float(c.get("ban_rate", 0.05)),
                    c.get("damage_type", "AD"),
                    int(c.get("cc", 50)),
                    int(c.get("engage", 50)),
                    int(c.get("poke", 50)),
                    int(c.get("waveclear", 50)),
                    int(c.get("scaling", 50)),
                ),
            )

        # Seed synergies
        for s in synergies_data:
            cursor.execute(
                """
                INSERT OR REPLACE INTO synergies (
                    champ_a, champ_b, synergy_score, combo_type
                ) VALUES (?, ?, ?, ?);
                """,
                (
                    s["champ_a"],
                    s["champ_b"],
                    float(s["synergy_score"]),
                    s.get("combo_type", ""),
                ),
            )

        # Seed counters
        for cnt in counters_data:
            cursor.execute(
                """
                INSERT OR REPLACE INTO counters (
                    champion, counter_champion, advantage_delta
                ) VALUES (?, ?, ?);
                """,
                (
                    cnt["champion"],
                    cnt["counter_champion"],
                    float(cnt["advantage_delta"]),
                ),
            )

        self.connection.commit()

    def upsert_summoner(self, profile_dict: Dict[str, Any]) -> None:
        """Insert or replace summoner record in cache."""
        cursor = self.connection.cursor()
        last_updated = profile_dict.get("last_updated", time.time())
        cursor.execute(
            """
            INSERT OR REPLACE INTO summoner_cache (
                puuid, name, tag_line, level, tier, rank, lp, wins, losses, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                profile_dict["puuid"],
                profile_dict["name"],
                profile_dict.get("tag_line", "NA1"),
                int(profile_dict.get("level", 30)),
                profile_dict.get("tier", "UNRANKED"),
                profile_dict.get("rank", "I"),
                int(profile_dict.get("lp", 0)),
                int(profile_dict.get("wins", 0)),
                int(profile_dict.get("losses", 0)),
                float(last_updated),
            ),
        )
        self.connection.commit()

    def get_summoner(
        self, puuid: Optional[str] = None, name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Retrieve summoner profile from cache by PUUID or Name."""
        cursor = self.connection.cursor()
        if puuid:
            cursor.execute("SELECT * FROM summoner_cache WHERE puuid = ?;", (puuid,))
        elif name:
            cursor.execute(
                "SELECT * FROM summoner_cache WHERE LOWER(name) = LOWER(?);", (name,)
            )
        else:
            return None

        row = cursor.fetchone()
        return dict(row) if row else None

    def record_matches(self, matches_list: List[Dict[str, Any]]) -> None:
        """Bulk insert historical match records."""
        cursor = self.connection.cursor()
        for m in matches_list:
            cursor.execute(
                """
                INSERT OR REPLACE INTO match_history (
                    match_id, puuid, champion, kills, deaths, assists,
                    cs, vision_score, win, duration
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    str(m["match_id"]),
                    str(m["puuid"]),
                    str(m["champion"]),
                    int(m.get("kills", 0)),
                    int(m.get("deaths", 0)),
                    int(m.get("assists", 0)),
                    int(m.get("cs", 0)),
                    int(m.get("vision_score", 0)),
                    1 if m.get("win") in (1, True, "1", "True") else 0,
                    int(m.get("duration", 1800)),
                ),
            )
        self.connection.commit()

    def get_summoner_history(self, puuid: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Return past matches for given puuid, sorted by match_id desc."""
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT * FROM match_history
            WHERE puuid = ?
            ORDER BY rowid DESC, match_id DESC
            LIMIT ?;
            """,
            (puuid, limit),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_champion_stats(self, champ_name: str) -> Optional[Dict[str, Any]]:
        """
        Returns stats, counters, and synergy partners for a given champion name or id.
        """
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT * FROM champions
            WHERE LOWER(name) = LOWER(?) OR LOWER(id) = LOWER(?);
            """,
            (champ_name, champ_name),
        )
        row = cursor.fetchone()
        if not row:
            return None

        champ = dict(row)
        actual_name = champ["name"]
        actual_id = champ["id"]

        # Fetch counters where this champion is countered or counters another
        cursor.execute(
            """
            SELECT champion, counter_champion, advantage_delta
            FROM counters
            WHERE LOWER(champion) IN (LOWER(?), LOWER(?))
               OR LOWER(counter_champion) IN (LOWER(?), LOWER(?));
            """,
            (actual_name, actual_id, actual_name, actual_id),
        )
        counters = [dict(c) for c in cursor.fetchall()]

        # Fetch synergies
        cursor.execute(
            """
            SELECT champ_a, champ_b, synergy_score, combo_type
            FROM synergies
            WHERE LOWER(champ_a) IN (LOWER(?), LOWER(?))
               OR LOWER(champ_b) IN (LOWER(?), LOWER(?));
            """,
            (actual_name, actual_id, actual_name, actual_id),
        )
        synergies = [dict(s) for s in cursor.fetchall()]

        champ["counters"] = counters
        champ["synergies"] = synergies
        return champ

    def get_all_champions(self) -> List[Dict[str, Any]]:
        """Return list of all champions ordered by name."""
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM champions ORDER BY name ASC;")
        return [dict(row) for row in cursor.fetchall()]

    def get_synergy(self, champ_a: str, champ_b: str) -> float:
        """Look up synergy score between two champions (symmetric)."""
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT synergy_score FROM synergies
            WHERE (LOWER(champ_a) = LOWER(?) AND LOWER(champ_b) = LOWER(?))
               OR (LOWER(champ_a) = LOWER(?) AND LOWER(champ_b) = LOWER(?))
            LIMIT 1;
            """,
            (champ_a, champ_b, champ_b, champ_a),
        )
        row = cursor.fetchone()
        return float(row[0]) if row else 0.0

    def get_counter_delta(self, champ_a: str, champ_b: str) -> float:
        """
        Returns advantage delta for champ_a against champ_b.
        Positive if champ_a counters champ_b, negative if champ_b counters champ_a.
        """
        cursor = self.connection.cursor()
        # Check if champ_a counters champ_b
        cursor.execute(
            """
            SELECT advantage_delta FROM counters
            WHERE LOWER(champion) = LOWER(?) AND LOWER(counter_champion) = LOWER(?)
            LIMIT 1;
            """,
            (champ_a, champ_b),
        )
        row = cursor.fetchone()
        if row:
            return float(row[0])

        # Check if champ_b counters champ_a
        cursor.execute(
            """
            SELECT advantage_delta FROM counters
            WHERE LOWER(champion) = LOWER(?) AND LOWER(counter_champion) = LOWER(?)
            LIMIT 1;
            """,
            (champ_b, champ_a),
        )
        row = cursor.fetchone()
        if row:
            return -float(row[0])

        return 0.0

    def close(self) -> None:
        """Close SQLite database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> HextechDatabase:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
