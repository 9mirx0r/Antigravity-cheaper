"""Hextech Oracle - SQLite Storage Engine with WAL Mode & Auto-Seeding."""

import json
import logging
import os
import sqlite3
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_DB_FILENAME = "hextech_oracle.db"


class Database:
    """High-performance SQLite database manager for Hextech Oracle."""

    def __init__(self, db_path: Optional[str] = None, auto_seed: bool = True):
        """Initialize SQLite database connection.

        Args:
            db_path: Path to SQLite database file. Defaults to local hextech_oracle.db.
                     Use ':memory:' for transient test instances.
            auto_seed: Whether to automatically seed database from seed_data.json if empty.
        """
        if db_path is None:
            self.db_path = os.path.join(os.getcwd(), DEFAULT_DB_FILENAME)
        else:
            self.db_path = db_path

        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        # Configure WAL mode and synchronous settings for maximum concurrency and safety
        if self.db_path != ":memory:":
            self.conn.execute("PRAGMA journal_mode = WAL;")
        self.conn.execute("PRAGMA synchronous = NORMAL;")
        self.conn.execute("PRAGMA foreign_keys = ON;")

        self.initialize_schema()

        if auto_seed:
            self.auto_seed_if_empty()

    def initialize_schema(self) -> None:
        """Create tables and indexes idempotently."""
        cursor = self.conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS champions (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                title TEXT,
                roles TEXT,
                attack INTEGER DEFAULT 0,
                defense INTEGER DEFAULT 0,
                magic INTEGER DEFAULT 0,
                difficulty INTEGER DEFAULT 0,
                win_rate REAL DEFAULT 0.50,
                ban_rate REAL DEFAULT 0.05,
                damage_type TEXT DEFAULT 'AD',
                cc INTEGER DEFAULT 50,
                engage INTEGER DEFAULT 50,
                poke INTEGER DEFAULT 50,
                waveclear INTEGER DEFAULT 50,
                scaling INTEGER DEFAULT 50
            );
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS synergies (
                champ_a TEXT NOT NULL,
                champ_b TEXT NOT NULL,
                synergy_score REAL NOT NULL,
                combo_type TEXT,
                PRIMARY KEY(champ_a, champ_b)
            );
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS counters (
                champion TEXT NOT NULL,
                counter_champion TEXT NOT NULL,
                advantage_delta REAL NOT NULL,
                PRIMARY KEY(champion, counter_champion)
            );
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS summoner_cache (
                puuid TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                tag_line TEXT,
                level INTEGER DEFAULT 1,
                tier TEXT DEFAULT 'UNRANKED',
                rank TEXT DEFAULT '',
                lp INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                last_updated REAL DEFAULT 0.0
            );
            """
        )

        cursor.execute(
            """
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
                duration INTEGER DEFAULT 1800,
                role TEXT DEFAULT 'MID',
                timestamp REAL DEFAULT 0.0,
                PRIMARY KEY(match_id, puuid)
            );
            """
        )

        # Performance Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_match_puuid ON match_history(puuid);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_counters_champ ON counters(champion);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_counters_target ON counters(counter_champion);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_synergies_a ON synergies(champ_a);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_synergies_b ON synergies(champ_b);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_champions_name ON champions(name);")

        self.conn.commit()

    def _find_seed_file(self) -> Optional[str]:
        """Locate seed_data.json across standard search paths."""
        candidates = [
            os.environ.get("HEXTECH_SEED_DATA"),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "mock_data", "seed_data.json")),
            os.path.abspath(os.path.join(os.getcwd(), "mock_data", "seed_data.json")),
            os.path.abspath(os.path.join(os.getcwd(), "..", "mock_data", "seed_data.json")),
            os.path.abspath(os.path.join(os.getcwd(), "..", "..", "mock_data", "seed_data.json")),
        ]
        for path in candidates:
            if path and os.path.exists(path):
                return path
        return None

    def auto_seed_if_empty(self) -> bool:
        """Seed database from seed_data.json if champions table is empty."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM champions;")
        count = cursor.fetchone()[0]
        if count > 0:
            return False

        seed_file = self._find_seed_file()
        if not seed_file:
            logger.warning("seed_data.json could not be located for auto-seeding.")
            return False

        try:
            with open(seed_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.seed_static_data(
                champions_data=data.get("champions", []),
                synergies_data=data.get("synergies", []),
                counters_data=data.get("counters", []),
            )

            # Also seed mock summoner if available in seed data
            mock_lcu = data.get("mock_lcu_state", {})
            active_sum = mock_lcu.get("active_summoner")
            if active_sum:
                self.upsert_summoner(active_sum)

            return True
        except Exception as e:
            logger.error(f"Error during auto-seeding: {e}")
            return False

    def seed_static_data(
        self,
        champions_data: Optional[List[Dict[str, Any]]] = None,
        synergies_data: Optional[List[Dict[str, Any]]] = None,
        counters_data: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Bulk seed champions, synergies, and counters tables."""
        cursor = self.conn.cursor()

        if champions_data:
            cursor.executemany(
                """
                INSERT OR REPLACE INTO champions (
                    id, name, title, roles, attack, defense, magic, difficulty,
                    win_rate, ban_rate, damage_type, cc, engage, poke, waveclear, scaling
                ) VALUES (
                    :id, :name, :title, :roles, :attack, :defense, :magic, :difficulty,
                    :win_rate, :ban_rate, :damage_type, :cc, :engage, :poke, :waveclear, :scaling
                )
                """,
                [
                    {
                        "id": c["id"],
                        "name": c["name"],
                        "title": c.get("title", ""),
                        "roles": c.get("roles", ""),
                        "attack": c.get("attack", 0),
                        "defense": c.get("defense", 0),
                        "magic": c.get("magic", 0),
                        "difficulty": c.get("difficulty", 0),
                        "win_rate": c.get("win_rate", 0.50),
                        "ban_rate": c.get("ban_rate", 0.05),
                        "damage_type": c.get("damage_type", "AD"),
                        "cc": c.get("cc", 50),
                        "engage": c.get("engage", 50),
                        "poke": c.get("poke", 50),
                        "waveclear": c.get("waveclear", 50),
                        "scaling": c.get("scaling", 50),
                    }
                    for c in champions_data
                ],
            )

        if synergies_data:
            cursor.executemany(
                """
                INSERT OR REPLACE INTO synergies (
                    champ_a, champ_b, synergy_score, combo_type
                ) VALUES (
                    :champ_a, :champ_b, :synergy_score, :combo_type
                )
                """,
                [
                    {
                        "champ_a": s["champ_a"],
                        "champ_b": s["champ_b"],
                        "synergy_score": s["synergy_score"],
                        "combo_type": s.get("combo_type", ""),
                    }
                    for s in synergies_data
                ],
            )

        if counters_data:
            cursor.executemany(
                """
                INSERT OR REPLACE INTO counters (
                    champion, counter_champion, advantage_delta
                ) VALUES (
                    :champion, :counter_champion, :advantage_delta
                )
                """,
                [
                    {
                        "champion": c["champion"],
                        "counter_champion": c["counter_champion"],
                        "advantage_delta": c["advantage_delta"],
                    }
                    for c in counters_data
                ],
            )

        self.conn.commit()

    def upsert_summoner(self, profile_dict: Dict[str, Any]) -> None:
        """Insert or update summoner cache record."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO summoner_cache (
                puuid, name, tag_line, level, tier, rank, lp, wins, losses, last_updated
            ) VALUES (
                :puuid, :name, :tag_line, :level, :tier, :rank, :lp, :wins, :losses, :last_updated
            )
            """,
            {
                "puuid": profile_dict.get("puuid", "unknown"),
                "name": profile_dict.get("name", "Unknown Summoner"),
                "tag_line": profile_dict.get("tag_line", "NA1"),
                "level": profile_dict.get("level", 1),
                "tier": profile_dict.get("tier", "UNRANKED"),
                "rank": profile_dict.get("rank", ""),
                "lp": profile_dict.get("lp", 0),
                "wins": profile_dict.get("wins", 0),
                "losses": profile_dict.get("losses", 0),
                "last_updated": profile_dict.get("last_updated", 0.0),
            },
        )
        self.conn.commit()

    def get_summoner(self, puuid: str) -> Optional[Dict[str, Any]]:
        """Retrieve summoner by PUUID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM summoner_cache WHERE puuid = ?;", (puuid,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_summoner_by_name(self, name: str, tag_line: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieve summoner by name and optional tag line (case-insensitive)."""
        cursor = self.conn.cursor()
        if tag_line:
            cursor.execute(
                "SELECT * FROM summoner_cache WHERE LOWER(name) = LOWER(?) AND LOWER(tag_line) = LOWER(?);",
                (name, tag_line),
            )
        else:
            cursor.execute("SELECT * FROM summoner_cache WHERE LOWER(name) = LOWER(?);", (name,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def record_matches(self, matches_list: List[Dict[str, Any]]) -> None:
        """Bulk record match history entries."""
        cursor = self.conn.cursor()
        cursor.executemany(
            """
            INSERT OR REPLACE INTO match_history (
                match_id, puuid, champion, kills, deaths, assists,
                cs, vision_score, win, duration, role, timestamp
            ) VALUES (
                :match_id, :puuid, :champion, :kills, :deaths, :assists,
                :cs, :vision_score, :win, :duration, :role, :timestamp
            )
            """,
            [
                {
                    "match_id": str(m["match_id"]),
                    "puuid": str(m["puuid"]),
                    "champion": m["champion"],
                    "kills": m.get("kills", 0),
                    "deaths": m.get("deaths", 0),
                    "assists": m.get("assists", 0),
                    "cs": m.get("cs", 0),
                    "vision_score": m.get("vision_score", 0),
                    "win": 1 if m.get("win") else 0,
                    "duration": m.get("duration", 1800),
                    "role": m.get("role", "MID"),
                    "timestamp": m.get("timestamp", 0.0),
                }
                for m in matches_list
            ],
        )
        self.conn.commit()

    def get_summoner_history(self, puuid: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Retrieve the most recent matches for a summoner."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM match_history
            WHERE puuid = ?
            ORDER BY timestamp DESC, match_id DESC
            LIMIT ?;
            """,
            (puuid, limit),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_champion(self, champ_id_or_name: str) -> Optional[Dict[str, Any]]:
        """Lookup champion by id or name (case-insensitive)."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM champions
            WHERE LOWER(id) = LOWER(?) OR LOWER(name) = LOWER(?);
            """,
            (champ_id_or_name, champ_id_or_name),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_all_champions(self) -> List[Dict[str, Any]]:
        """Retrieve all champion records ordered by name."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM champions ORDER BY name ASC;")
        return [dict(row) for row in cursor.fetchall()]

    def get_champion_stats(self, champ_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve full champion details, counters, and synergies."""
        champ = self.get_champion(champ_name)
        if not champ:
            return None

        canonical_id = champ["id"]
        canonical_name = champ["name"]
        cursor = self.conn.cursor()

        # Champions this champion counters (advantage for champ)
        cursor.execute(
            """
            SELECT counter_champion, advantage_delta
            FROM counters
            WHERE LOWER(champion) = LOWER(?) OR LOWER(champion) = LOWER(?);
            """,
            (canonical_id, canonical_name),
        )
        counters = [
            {"counter_champion": row["counter_champion"], "advantage_delta": row["advantage_delta"]}
            for row in cursor.fetchall()
        ]

        # Champions that counter this champion (disadvantage for champ)
        cursor.execute(
            """
            SELECT champion, advantage_delta
            FROM counters
            WHERE LOWER(counter_champion) = LOWER(?) OR LOWER(counter_champion) = LOWER(?);
            """,
            (canonical_id, canonical_name),
        )
        countered_by = [
            {"champion": row["champion"], "advantage_delta": row["advantage_delta"]}
            for row in cursor.fetchall()
        ]

        # Synergies
        cursor.execute(
            """
            SELECT champ_a, champ_b, synergy_score, combo_type
            FROM synergies
            WHERE LOWER(champ_a) = LOWER(?) OR LOWER(champ_a) = LOWER(?)
               OR LOWER(champ_b) = LOWER(?) OR LOWER(champ_b) = LOWER(?);
            """,
            (canonical_id, canonical_name, canonical_id, canonical_name),
        )
        synergies = []
        for row in cursor.fetchall():
            partner = row["champ_b"] if row["champ_a"].lower() in (canonical_id.lower(), canonical_name.lower()) else row["champ_a"]
            synergies.append({
                "partner": partner,
                "synergy_score": row["synergy_score"],
                "combo_type": row["combo_type"],
            })

        result = dict(champ)
        result["counters"] = counters
        result["countered_by"] = countered_by
        result["synergies"] = synergies
        return result

    def get_synergy(self, champ_a: str, champ_b: str) -> float:
        """Get pairwise synergy score between two champions."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT synergy_score FROM synergies
            WHERE (LOWER(champ_a) = LOWER(?) AND LOWER(champ_b) = LOWER(?))
               OR (LOWER(champ_a) = LOWER(?) AND LOWER(champ_b) = LOWER(?));
            """,
            (champ_a, champ_b, champ_b, champ_a),
        )
        row = cursor.fetchone()
        return float(row["synergy_score"]) if row else 0.0

    def get_counter_delta(self, champ: str, enemy: str) -> float:
        """Calculate net counter delta advantage for champ against enemy."""
        cursor = self.conn.cursor()
        # Champ counters enemy -> positive
        cursor.execute(
            """
            SELECT advantage_delta FROM counters
            WHERE LOWER(champion) = LOWER(?) AND LOWER(counter_champion) = LOWER(?);
            """,
            (champ, enemy),
        )
        row = cursor.fetchone()
        pos = float(row["advantage_delta"]) if row else 0.0

        # Enemy counters champ -> negative
        cursor.execute(
            """
            SELECT advantage_delta FROM counters
            WHERE LOWER(champion) = LOWER(?) AND LOWER(counter_champion) = LOWER(?);
            """,
            (enemy, champ),
        )
        row2 = cursor.fetchone()
        neg = float(row2["advantage_delta"]) if row2 else 0.0

        return pos - neg

    def close(self) -> None:
        """Safely close database connection."""
        try:
            self.conn.close()
        except Exception:
            pass
