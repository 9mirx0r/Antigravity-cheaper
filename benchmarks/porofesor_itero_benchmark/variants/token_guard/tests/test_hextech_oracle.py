"""
Comprehensive Test Suite for Hextech Oracle (Aegis-LoL).
Verifies database schema & WAL, LCU connector & mock daemon, Porofesor profiler tags,
iTero draft coach algorithms & Monte Carlo simulations, and headless UI launch.
"""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from src.analytics.summoner_profiler import SummonerProfiler
from src.core.lcu_connector import LCUConnector, MockLCUDaemon
from src.draft.draft_coach import DraftCoach
from src.storage.db import HextechDatabase
from src.ui.desktop_app import HextechOracleApp


class TestHextechOracle(unittest.TestCase):
    """Rigorous unit and integration tests for Hextech Oracle."""

    @classmethod
    def setUpClass(cls) -> None:
        # Locate seed_data.json
        possible_paths = [
            Path(__file__).resolve().parent.parent.parent.parent / "mock_data" / "seed_data.json",
            Path(__file__).resolve().parent.parent / "mock_data" / "seed_data.json",
            Path.cwd().parent.parent / "mock_data" / "seed_data.json",
            Path.cwd() / "mock_data" / "seed_data.json",
        ]
        cls.seed_path = None
        for p in possible_paths:
            if p.exists():
                cls.seed_path = str(p)
                break
        assert cls.seed_path is not None, "seed_data.json fixture could not be located"

    def setUp(self) -> None:
        # In-memory database seeded from fixture for isolated tests
        self.db = HextechDatabase(db_path=":memory:", auto_seed=True, seed_file_path=self.seed_path)
        self.profiler = SummonerProfiler()
        self.coach = DraftCoach(self.db)
        self.connector = LCUConnector(seed_file_path=self.seed_path)

    def tearDown(self) -> None:
        self.db.close()

    # -------------------------------------------------------------------------
    # 1. DATABASE & STORAGE TESTS
    # -------------------------------------------------------------------------
    def test_01_db_schema_initialization_and_wal(self) -> None:
        """Verify schema tables, indexes, and WAL pragma configuration."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            temp_db_path = tf.name

        try:
            file_db = HextechDatabase(db_path=temp_db_path, auto_seed=False)
            cursor = file_db.connection.cursor()

            # Verify tables exist
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = {row[0] for row in cursor.fetchall()}
            expected_tables = {"champions", "synergies", "counters", "summoner_cache", "match_history"}
            for t in expected_tables:
                self.assertIn(t, tables, f"Expected table {t} missing from schema")

            # Verify WAL journal mode
            cursor.execute("PRAGMA journal_mode;")
            journal_mode = cursor.fetchone()[0].upper()
            self.assertEqual(journal_mode, "WAL", "Database must be initialized in WAL mode")

            # Verify indexes exist
            cursor.execute("SELECT name FROM sqlite_master WHERE type='index';")
            indexes = {row[0] for row in cursor.fetchall()}
            self.assertIn("idx_match_history_puuid", indexes)
            self.assertIn("idx_champions_name", indexes)

            file_db.close()
        finally:
            if os.path.exists(temp_db_path):
                try:
                    os.remove(temp_db_path)
                except OSError:
                    pass

    def test_02_db_seeding_from_file(self) -> None:
        """Verify static metadata seeding loads champions, synergies, and counters."""
        cursor = self.db.connection.cursor()

        cursor.execute("SELECT COUNT(*) FROM champions;")
        champ_count = cursor.fetchone()[0]
        self.assertGreaterEqual(champ_count, 20, "Should have seeded at least 20 champions")

        cursor.execute("SELECT COUNT(*) FROM synergies;")
        syn_count = cursor.fetchone()[0]
        self.assertGreaterEqual(syn_count, 5, "Should have seeded synergy combos")

        cursor.execute("SELECT COUNT(*) FROM counters;")
        counter_count = cursor.fetchone()[0]
        self.assertGreaterEqual(counter_count, 5, "Should have seeded counter matchups")

    def test_03_db_summoner_cache_crud(self) -> None:
        """Verify summoner upsert, update, and retrieval by puuid and name."""
        profile = {
            "puuid": "test-user-001",
            "name": "OraclePlayer",
            "tag_line": "EUW",
            "level": 150,
            "tier": "DIAMOND",
            "rank": "II",
            "lp": 75,
            "wins": 120,
            "losses": 95,
        }
        self.db.upsert_summoner(profile)

        # Query by PUUID
        retrieved = self.db.get_summoner(puuid="test-user-001")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["name"], "OraclePlayer")
        self.assertEqual(retrieved["tier"], "DIAMOND")
        self.assertEqual(retrieved["lp"], 75)

        # Query by Name (case-insensitive)
        by_name = self.db.get_summoner(name="oracleplayer")
        self.assertIsNotNone(by_name)
        self.assertEqual(by_name["puuid"], "test-user-001")

        # Update
        profile["lp"] = 99
        self.db.upsert_summoner(profile)
        updated = self.db.get_summoner(puuid="test-user-001")
        self.assertEqual(updated["lp"], 99)

    def test_04_db_match_history_bulk_insert_and_query(self) -> None:
        """Verify recording match history records and limit retrieval."""
        test_puuid = "puuid-match-test"
        matches = [
            {
                "match_id": f"TEST_M_{i}",
                "puuid": test_puuid,
                "champion": "Ahri" if i % 2 == 0 else "Yasuo",
                "kills": 5 + i,
                "deaths": 2,
                "assists": 8,
                "cs": 200 + i * 10,
                "vision_score": 30 + i,
                "win": 1 if i % 3 != 0 else 0,
                "duration": 1800,
            }
            for i in range(25)
        ]
        self.db.record_matches(matches)

        # Retrieve with limit 20
        history = self.db.get_summoner_history(test_puuid, limit=20)
        self.assertEqual(len(history), 20)
        self.assertEqual(history[0]["puuid"], test_puuid)

    def test_05_db_champion_stats_synergies_and_counters(self) -> None:
        """Verify champion queries, synergy scores, and counter deltas."""
        stats = self.db.get_champion_stats("Yasuo")
        self.assertIsNotNone(stats)
        self.assertEqual(stats["name"], "Yasuo")
        self.assertEqual(stats["damage_type"], "AD")

        # Verify synergies link with Malphite
        syn_score = self.db.get_synergy("Malphite", "Yasuo")
        self.assertAlmostEqual(syn_score, 0.12, places=2)
        # Symmetric check
        syn_score_rev = self.db.get_synergy("Yasuo", "Malphite")
        self.assertEqual(syn_score, syn_score_rev)

        # Counter check: Vayne counters Cho'Gath
        delta_vayne = self.db.get_counter_delta("Vayne", "Chogath")
        self.assertAlmostEqual(delta_vayne, 0.085, places=3)
        delta_chogath = self.db.get_counter_delta("Chogath", "Vayne")
        self.assertAlmostEqual(delta_chogath, -0.085, places=3)

    # -------------------------------------------------------------------------
    # 2. CORE & LCU CONNECTOR TESTS
    # -------------------------------------------------------------------------
    def test_06_mock_lcu_daemon_structure(self) -> None:
        """Verify MockLCUDaemon active summoner and live 5v5 game state."""
        daemon = MockLCUDaemon(seed_file_path=self.seed_path)
        self.assertTrue(daemon.is_running())

        summoner = daemon.get_active_summoner()
        self.assertEqual(summoner["name"], "Hide on bush")
        self.assertEqual(summoner["tag_line"], "KR1")
        self.assertEqual(summoner["tier"], "CHALLENGER")

        live_game = daemon.get_live_game_data()
        self.assertIn("blue_team", live_game)
        self.assertIn("red_team", live_game)
        self.assertEqual(len(live_game["blue_team"]), 5)
        self.assertEqual(len(live_game["red_team"]), 5)

        # Check Faker is on Blue team
        blue_names = [p["summoner_name"] for p in live_game["blue_team"]]
        self.assertIn("Hide on bush", blue_names)

    def test_07_lcu_connector_offline_fallback(self) -> None:
        """Verify connector falls back safely to MockLCUDaemon when offline."""
        connector = LCUConnector(port=39999, use_mock_fallback=True, seed_file_path=self.seed_path)
        self.assertFalse(connector.is_client_running())
        self.assertEqual(connector.get_status(), "SIMULATED [OFFLINE MOCK]")

        summoner = connector.get_active_summoner()
        self.assertIsNotNone(summoner)
        self.assertEqual(summoner["name"], "Hide on bush")

        live_data = connector.get_live_game_data()
        self.assertIsNotNone(live_data)
        self.assertEqual(len(live_data["blue_team"]), 5)

    # -------------------------------------------------------------------------
    # 3. ANALYTICS & PROFILER TESTS
    # -------------------------------------------------------------------------
    def test_08_summoner_profiler_performance_metrics(self) -> None:
        """Verify calculation of win rate, KDA, CS/min, and Vision/min."""
        matches = [
            {"match_id": "1", "puuid": "p", "champion": "Ahri", "kills": 6, "deaths": 2, "assists": 8, "cs": 240, "vision_score": 45, "win": 1, "duration": 1800},
            {"match_id": "2", "puuid": "p", "champion": "Ahri", "kills": 4, "deaths": 4, "assists": 4, "cs": 210, "vision_score": 35, "win": 0, "duration": 1800},
        ]
        stats = self.profiler.analyze_performance(matches)
        self.assertEqual(stats["total_matches"], 2)
        self.assertEqual(stats["wins"], 1)
        self.assertEqual(stats["losses"], 1)
        self.assertAlmostEqual(stats["win_rate"], 0.50, places=2)
        # Total kills: 10, total assists: 12, total deaths: 6 => KDA: 22 / 6 = 3.67
        self.assertAlmostEqual(stats["kda"], 3.67, places=2)
        # Total CS: 450, total minutes: 60 => CS/min: 7.5
        self.assertAlmostEqual(stats["avg_cs_per_min"], 7.5, places=2)
        # Total Vision: 80, total minutes: 60 => Vision/min: 1.33
        self.assertAlmostEqual(stats["avg_vision_per_min"], 1.33, places=2)

    def test_09_summoner_profiler_tags_vision_and_farm(self) -> None:
        """Verify VISION_PRODIGY and FARM_MACHINE tags."""
        # Vision prodigy: vision/min >= 1.4
        vision_matches = [
            {"match_id": "1", "puuid": "p", "champion": "Janna", "kills": 1, "deaths": 2, "assists": 15, "cs": 20, "vision_score": 50, "win": 1, "duration": 1800},
        ]
        tags = self.profiler.generate_tags(vision_matches)
        self.assertIn("VISION_PRODIGY", tags)

        # Farm machine: cs/min >= 7.5
        farm_matches = [
            {"match_id": "2", "puuid": "p", "champion": "Jinx", "kills": 3, "deaths": 2, "assists": 5, "cs": 270, "vision_score": 20, "win": 1, "duration": 1800},
        ]
        tags_farm = self.profiler.generate_tags(farm_matches)
        self.assertIn("FARM_MACHINE", tags_farm)

    def test_10_summoner_profiler_tags_aggressive_cold_tilt(self) -> None:
        """Verify AGGRESSIVE_LANER, COLD_STREAK, and TILT_PRONE tags."""
        # Aggressive laner: avg_kills >= 6 and kda >= 2.5
        aggro_matches = [
            {"match_id": "1", "puuid": "p", "champion": "Zed", "kills": 10, "deaths": 2, "assists": 5, "cs": 180, "vision_score": 20, "win": 1, "duration": 1800},
            {"match_id": "2", "puuid": "p", "champion": "Zed", "kills": 8, "deaths": 3, "assists": 4, "cs": 190, "vision_score": 20, "win": 1, "duration": 1800},
        ]
        tags_aggro = self.profiler.generate_tags(aggro_matches)
        self.assertIn("AGGRESSIVE_LANER", tags_aggro)

        # Cold streak: >= 4 losses in last 5 matches
        cold_matches = [
            {"match_id": f"c_{i}", "puuid": "p", "champion": "LeeSin", "kills": 2, "deaths": 5, "assists": 3, "cs": 100, "vision_score": 20, "win": 0, "duration": 1500}
            for i in range(4)
        ] + [
            {"match_id": "c_5", "puuid": "p", "champion": "LeeSin", "kills": 5, "deaths": 2, "assists": 5, "cs": 120, "vision_score": 20, "win": 1, "duration": 1500}
        ]
        tags_cold = self.profiler.generate_tags(cold_matches)
        self.assertIn("COLD_STREAK", tags_cold)

        # Tilt prone: current loss streak >= 3 with kda < 1.8
        tilt_matches = [
            {"match_id": f"t_{i}", "puuid": "p", "champion": "Yasuo", "kills": 1, "deaths": 6, "assists": 1, "cs": 120, "vision_score": 10, "win": 0, "duration": 1500}
            for i in range(3)
        ]
        tags_tilt = self.profiler.generate_tags(tilt_matches)
        self.assertIn("TILT_PRONE", tags_tilt)

    def test_11_summoner_profiler_tags_hypercarry_and_otp(self) -> None:
        """Verify HYPER_CARRY and ONE_TRICK_PONY tags."""
        # Hyper carry: win rate >= 62% with >= 5 matches
        carry_matches = [
            {"match_id": f"hc_{i}", "puuid": "p", "champion": "Jinx", "role": "ADC", "kills": 8, "deaths": 2, "assists": 6, "cs": 220, "vision_score": 25, "win": 1 if i < 4 else 0, "duration": 1800}
            for i in range(5)
        ]
        # 4 wins out of 5 matches = 80% win rate
        tags_carry = self.profiler.generate_tags(carry_matches)
        self.assertIn("HYPER_CARRY", tags_carry)

        # One trick pony: >= 60% of total matches played on a single champion
        otp_matches = [
            {"match_id": f"otp_{i}", "puuid": "p", "champion": "Ahri" if i < 4 else "Sylas", "kills": 5, "deaths": 3, "assists": 5, "cs": 200, "vision_score": 25, "win": 1, "duration": 1800}
            for i in range(5)
        ]
        # 4 out of 5 matches on Ahri = 80%
        tags_otp = self.profiler.generate_tags(otp_matches)
        self.assertIn("ONE_TRICK_PONY", tags_otp)

    # -------------------------------------------------------------------------
    # 4. DRAFT INTELLIGENCE & MONTE CARLO TESTS
    # -------------------------------------------------------------------------
    def test_12_draft_coach_composition_damage_and_warnings(self) -> None:
        """Verify team damage profile ratios and mono-damage warning (>82%)."""
        # All AD team: Aatrox, Darius, Jinx, Caitlyn, Zed
        ad_comp = ["Aatrox", "Darius", "Jinx", "Caitlyn", "Zed"]
        analysis = self.coach.analyze_team_composition(ad_comp)

        damage = analysis["damage_profile"]
        self.assertAlmostEqual(damage["ad_ratio"], 1.0, places=2)
        self.assertAlmostEqual(damage["ap_ratio"], 0.0, places=2)

        # Check for warning
        has_heavy_ad_warning = any("HEAVY_PHYSICAL_DAMAGE" in w for w in analysis["warnings"])
        self.assertTrue(has_heavy_ad_warning, "Comp >82% AD must trigger HEAVY_PHYSICAL_DAMAGE warning")

        # Check radar metrics are between 0 and 100
        radar = analysis["utility_radar"]
        for key in ["cc_rating", "engage_rating", "poke_rating", "waveclear_rating", "scaling_rating"]:
            self.assertGreaterEqual(radar[key], 0.0)
            self.assertLessEqual(radar[key], 100.0)

    def test_13_draft_coach_synergy_and_counter_scoring(self) -> None:
        """Verify synergy summation and counter advantage calculations."""
        # Malphite + Yasuo synergy
        team = ["Malphite", "Yasuo", "Ahri"]
        syn_score = self.coach.compute_synergy_score(team)
        self.assertAlmostEqual(syn_score, 0.12, places=2)

        # Counter matchup: Kassadin counters LeBlanc (+0.075)
        blue = ["Kassadin"]
        red = ["LeBlanc"]
        counter_delta = self.coach.compute_counter_score(blue, red)
        self.assertAlmostEqual(counter_delta, 0.075, places=3)

    def test_14_draft_coach_monte_carlo_simulation(self) -> None:
        """Verify Monte Carlo simulation bounds, sum, and advantage bias with 10,000 runs."""
        # Blue team with strong synergy and counters: Malphite, Yasuo, Kassadin, Jinx, Lulu
        # Red team countered: Jax, Cho'Gath, LeBlanc, Caitlyn, Blitzcrank
        blue_team = ["Malphite", "Yasuo", "Kassadin", "Jinx", "Lulu"]
        red_team = ["Jax", "Cho'Gath", "LeBlanc", "Caitlyn", "Blitzcrank"]

        sim = self.coach.simulate_win_probability(blue_team, red_team, iterations=10000)
        b_wr = sim["blue_win_rate"]
        r_wr = sim["red_win_rate"]

        # Probabilities must sum to 1.0
        self.assertAlmostEqual(b_wr + r_wr, 1.0, places=3)
        self.assertGreater(b_wr, 0.05)
        self.assertLess(b_wr, 0.95)
        # Blue has massive synergy and counters => should have favorable win rate
        self.assertGreater(b_wr, 0.50)

    def test_15_draft_coach_recommend_picks(self) -> None:
        """Verify recommend_picks respects role filter, excludes picked champs, and sorts by score."""
        current_team = ["Malphite"]  # Yasuo has synergy with Malphite
        enemy_team = ["Cho'Gath"]     # Vayne counters Cho'Gath

        recs = self.coach.recommend_picks(current_team, enemy_team, role="MID", top_n=3)
        self.assertLessEqual(len(recs), 3)
        self.assertGreater(len(recs), 0)

        # Verify no picked champions appear
        for r in recs:
            self.assertNotIn(r["champion"], current_team)
            self.assertNotIn(r["champion"], enemy_team)
            # Verify role match
            roles = [x.strip().upper() for x in r["roles"].split(",")]
            self.assertIn("MID", roles)

        # Verify descending score order
        scores = [r["score"] for r in recs]
        self.assertEqual(scores, sorted(scores, reverse=True))

    # -------------------------------------------------------------------------
    # 5. DESKTOP APP HEADLESS INTEGRATION TEST
    # -------------------------------------------------------------------------
    def test_16_desktop_app_headless_init_and_destroy(self) -> None:
        """Verify full Desktop GUI initializes headless, builds all tabs, and shuts down cleanly."""
        app = HextechOracleApp(
            db=self.db,
            connector=self.connector,
            profiler=self.profiler,
            coach=self.coach,
            headless=True,
        )
        self.assertIsNotNone(app.root)
        self.assertIsNotNone(app.notebook)
        self.assertEqual(app.notebook.index("end"), 3, "App must have exactly 3 tabs")

        # Verify live tab elements
        self.assertIsNotNone(app.lbl_game_info)
        self.assertIsNotNone(app.lbl_gold_diff)

        # Verify draft coach elements
        self.assertIsNotNone(app.mc_canvas)
        self.assertIsNotNone(app.rec_text)

        # Verify summoner profile elements
        self.assertIsNotNone(app.lbl_prof_name)
        self.assertIsNotNone(app.lbl_prof_rank)
        self.assertIsNotNone(app.lbl_prof_metrics)

        # Clean shutdown
        app.destroy()


if __name__ == "__main__":
    unittest.main()
