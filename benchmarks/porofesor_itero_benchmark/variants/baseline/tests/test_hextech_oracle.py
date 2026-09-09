"""Comprehensive Test Suite for Hextech Oracle (Aegis-LoL)."""

import os
import shutil
import tempfile
import unittest

from src.analytics.summoner_profiler import SummonerProfiler
from src.core.lcu_connector import LCUConnector, MockLCUDaemon
from src.draft.draft_coach import DraftCoach
from src.storage.db import Database
from src.ui.desktop_app import DesktopApp


class TestHextechOracle(unittest.TestCase):
    """Rigorous unit and integration test suite for all Hextech Oracle components."""

    def setUp(self):
        """Create isolated temporary directory and database instance."""
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_hextech.db")
        self.db = Database(db_path=self.db_path, auto_seed=True)

    def tearDown(self):
        """Clean up database connection and test directory."""
        self.db.close()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # --------------------------------------------------------------------------
    # 1. Database Operations & WAL Mode
    # --------------------------------------------------------------------------
    def test_01_db_schema_and_wal_mode(self):
        """Verify schema tables, indexes, and SQLite WAL journal mode."""
        cursor = self.db.conn.cursor()

        # Check WAL mode
        cursor.execute("PRAGMA journal_mode;")
        journal_mode = cursor.fetchone()[0]
        self.assertEqual(journal_mode.lower(), "wal")

        # Check tables existence
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row[0] for row in cursor.fetchall()}
        expected_tables = {"champions", "synergies", "counters", "summoner_cache", "match_history"}
        self.assertTrue(expected_tables.issubset(tables))

        # Check indexes
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index';")
        indexes = {row[0] for row in cursor.fetchall()}
        self.assertIn("idx_match_puuid", indexes)
        self.assertIn("idx_champions_name", indexes)

    def test_02_db_seeding_and_champion_queries(self):
        """Verify auto-seeding of champions, synergies, and counters from seed_data.json."""
        champs = self.db.get_all_champions()
        self.assertGreaterEqual(len(champs), 20)

        # Query champion stats with counters & synergies
        yasuo = self.db.get_champion_stats("Yasuo")
        self.assertIsNotNone(yasuo)
        self.assertEqual(yasuo["name"], "Yasuo")
        self.assertIn("AIRBORNE_WOMBO", [s["combo_type"] for s in yasuo["synergies"]])

        # Verify counter query
        kassadin = self.db.get_champion_stats("Kassadin")
        self.assertIsNotNone(kassadin)
        self.assertIn("LeBlanc", [c["counter_champion"] for c in kassadin["counters"]])

    def test_03_db_summoner_and_match_history_crud(self):
        """Verify CRUD operations for summoner caching and match history."""
        # Upsert summoner
        profile = {
            "puuid": "test-puuid-123",
            "name": "OraclePlayer",
            "tag_line": "TEST",
            "level": 150,
            "tier": "DIAMOND",
            "rank": "II",
            "lp": 75,
            "wins": 120,
            "losses": 80,
            "last_updated": 1700000000.0,
        }
        self.db.upsert_summoner(profile)

        cached = self.db.get_summoner("test-puuid-123")
        self.assertIsNotNone(cached)
        self.assertEqual(cached["name"], "OraclePlayer")
        self.assertEqual(cached["tier"], "DIAMOND")

        by_name = self.db.get_summoner_by_name("oracleplayer", "test")
        self.assertIsNotNone(by_name)
        self.assertEqual(by_name["puuid"], "test-puuid-123")

        # Record matches
        matches = [
            {
                "match_id": f"TEST-MATCH-{i}",
                "puuid": "test-puuid-123",
                "champion": "Ahri",
                "kills": 8,
                "deaths": 2,
                "assists": 6,
                "cs": 200,
                "vision_score": 30,
                "win": 1,
                "duration": 1800,
                "role": "MID",
                "timestamp": 1700000000.0 + i * 100,
            }
            for i in range(25)
        ]
        self.db.record_matches(matches)

        history = self.db.get_summoner_history("test-puuid-123", limit=20)
        self.assertEqual(len(history), 20)
        self.assertEqual(history[0]["champion"], "Ahri")

    # --------------------------------------------------------------------------
    # 2. LCU Connector & Mock Daemon
    # --------------------------------------------------------------------------
    def test_04_lcu_connector_live_and_mock_detection(self):
        """Verify LCU connector offline fallback and status indicator."""
        connector = LCUConnector(use_mock_fallback=True, force_mock=True)
        self.assertFalse(connector.is_client_running())
        self.assertEqual(connector.get_connection_status(), "SIMULATED [OFFLINE MOCK]")

        active = connector.get_active_summoner()
        self.assertIsNotNone(active)
        self.assertEqual(active["name"], "Hide on bush")
        self.assertEqual(active["tag_line"], "KR1")

    def test_05_mock_lcu_daemon_faker_profile_and_live_game(self):
        """Verify MockLCUDaemon generates valid 5v5 live match data and Faker profile."""
        daemon = MockLCUDaemon()
        summoner = daemon.get_active_summoner()
        self.assertEqual(summoner["puuid"], "kr-faker-001")
        self.assertEqual(summoner["tier"], "CHALLENGER")

        live_game = daemon.get_live_game_data()
        self.assertEqual(len(live_game["blue_team"]), 5)
        self.assertEqual(len(live_game["red_team"]), 5)
        self.assertEqual(live_game["game_id"], 6948211029)

        mock_matches = daemon.generate_mock_matches(count=20)
        self.assertEqual(len(mock_matches), 20)

    # --------------------------------------------------------------------------
    # 3. Porofesor Summoner Profiler & Tag Engine
    # --------------------------------------------------------------------------
    def test_06_summoner_profiler_performance_aggregation(self):
        """Verify statistical aggregations over match histories."""
        matches = [
            {"win": 1, "kills": 6, "deaths": 2, "assists": 6, "cs": 180, "vision_score": 30, "duration": 1800, "champion": "Ahri", "role": "MID"},
            {"win": 0, "kills": 2, "deaths": 4, "assists": 2, "cs": 150, "vision_score": 20, "duration": 1800, "champion": "Ahri", "role": "MID"},
        ]
        perf = SummonerProfiler.analyze_performance(matches)
        self.assertEqual(perf["total_matches"], 2)
        self.assertEqual(perf["wins"], 1)
        self.assertEqual(perf["losses"], 1)
        self.assertEqual(perf["win_rate"], 0.5)
        self.assertEqual(perf["avg_kills"], 4.0)
        self.assertEqual(perf["avg_deaths"], 3.0)
        self.assertEqual(perf["avg_kda"], 2.67)
        self.assertEqual(perf["avg_cs_per_min"], 5.5)

    def test_07_tag_rule_vision_prodigy(self):
        """Verify VISION_PRODIGY tag: vision_score / (duration / 60) >= 1.4."""
        # 45 vision score in 30 minutes (1800s) = 1.5/min -> Triggers tag
        high_vis = [{"win": 1, "kills": 3, "deaths": 1, "assists": 5, "cs": 120, "vision_score": 45, "duration": 1800, "champion": "Thresh", "role": "SUPPORT"}]
        tags_high = SummonerProfiler.generate_tags(high_vis)
        self.assertIn("VISION_PRODIGY", tags_high)

        # 20 vision score in 30 minutes = 0.67/min -> Does not trigger
        low_vis = [{"win": 1, "kills": 3, "deaths": 1, "assists": 5, "cs": 120, "vision_score": 20, "duration": 1800, "champion": "Thresh", "role": "SUPPORT"}]
        tags_low = SummonerProfiler.generate_tags(low_vis)
        self.assertNotIn("VISION_PRODIGY", tags_low)

    def test_08_tag_rule_aggressive_laner(self):
        """Verify AGGRESSIVE_LANER tag: avg_kills >= 6 and kda >= 2.5."""
        agg_matches = [
            {"win": 1, "kills": 8, "deaths": 2, "assists": 4, "cs": 180, "vision_score": 15, "duration": 1800, "champion": "Zed", "role": "MID"},
            {"win": 1, "kills": 7, "deaths": 3, "assists": 5, "cs": 190, "vision_score": 15, "duration": 1800, "champion": "Zed", "role": "MID"},
        ]
        tags = SummonerProfiler.generate_tags(agg_matches)
        self.assertIn("AGGRESSIVE_LANER", tags)

        passive_matches = [
            {"win": 1, "kills": 3, "deaths": 1, "assists": 8, "cs": 180, "vision_score": 15, "duration": 1800, "champion": "Lulu", "role": "SUPPORT"},
        ]
        tags_pass = SummonerProfiler.generate_tags(passive_matches)
        self.assertNotIn("AGGRESSIVE_LANER", tags_pass)

    def test_09_tag_rule_farm_machine(self):
        """Verify FARM_MACHINE tag: cs_per_min >= 7.5."""
        # 240 CS in 30 minutes = 8.0 CS/min -> Triggers
        farmer = [{"win": 1, "kills": 2, "deaths": 1, "assists": 2, "cs": 240, "vision_score": 10, "duration": 1800, "champion": "Caitlyn", "role": "ADC"}]
        tags = SummonerProfiler.generate_tags(farmer)
        self.assertIn("FARM_MACHINE", tags)

        # 150 CS in 30 minutes = 5.0 CS/min -> Does not trigger
        low_cs = [{"win": 1, "kills": 2, "deaths": 1, "assists": 2, "cs": 150, "vision_score": 10, "duration": 1800, "champion": "Caitlyn", "role": "ADC"}]
        tags_low = SummonerProfiler.generate_tags(low_cs)
        self.assertNotIn("FARM_MACHINE", tags_low)

    def test_10_tag_rule_tilt_prone(self):
        """Verify TILT_PRONE tag: current losing streak >= 3 with recent kda < 1.8."""
        tilt_matches = [
            {"win": 0, "kills": 1, "deaths": 6, "assists": 2, "cs": 130, "vision_score": 10, "duration": 1500, "champion": "Yasuo", "role": "MID"},
            {"win": 0, "kills": 0, "deaths": 7, "assists": 1, "cs": 120, "vision_score": 8, "duration": 1400, "champion": "Yasuo", "role": "MID"},
            {"win": 0, "kills": 2, "deaths": 8, "assists": 3, "cs": 140, "vision_score": 12, "duration": 1600, "champion": "Yasuo", "role": "MID"},
            {"win": 1, "kills": 8, "deaths": 2, "assists": 5, "cs": 220, "vision_score": 25, "duration": 1900, "champion": "Yasuo", "role": "MID"},
        ]
        tags = SummonerProfiler.generate_tags(tilt_matches)
        self.assertIn("TILT_PRONE", tags)

    def test_11_tag_rule_hyper_carry(self):
        """Verify HYPER_CARRY tag: win rate >= 62% with >= 5 matches."""
        hc_matches = [
            {"win": 1, "kills": 7, "deaths": 2, "assists": 6, "cs": 220, "vision_score": 20, "duration": 1800, "champion": "Jinx", "role": "ADC"},
            {"win": 1, "kills": 9, "deaths": 1, "assists": 7, "cs": 240, "vision_score": 22, "duration": 1800, "champion": "Jinx", "role": "ADC"},
            {"win": 1, "kills": 6, "deaths": 2, "assists": 5, "cs": 210, "vision_score": 18, "duration": 1800, "champion": "Jinx", "role": "ADC"},
            {"win": 1, "kills": 8, "deaths": 3, "assists": 8, "cs": 230, "vision_score": 24, "duration": 1800, "champion": "Jinx", "role": "ADC"},
            {"win": 0, "kills": 3, "deaths": 4, "assists": 3, "cs": 190, "vision_score": 15, "duration": 1800, "champion": "Jinx", "role": "ADC"},
        ]
        # 4 wins out of 5 = 80% win rate
        tags = SummonerProfiler.generate_tags(hc_matches)
        self.assertIn("HYPER_CARRY", tags)

    def test_12_tag_rule_one_trick_pony_and_cold_streak(self):
        """Verify ONE_TRICK_PONY (>= 60% on 1 champ) and COLD_STREAK (>= 4 losses in 5)."""
        otp_matches = [
            {"win": 1, "kills": 5, "deaths": 2, "assists": 5, "cs": 200, "vision_score": 20, "duration": 1800, "champion": "Ahri", "role": "MID"},
            {"win": 1, "kills": 6, "deaths": 1, "assists": 6, "cs": 210, "vision_score": 22, "duration": 1800, "champion": "Ahri", "role": "MID"},
            {"win": 1, "kills": 7, "deaths": 2, "assists": 4, "cs": 205, "vision_score": 21, "duration": 1800, "champion": "Ahri", "role": "MID"},
            {"win": 1, "kills": 8, "deaths": 3, "assists": 5, "cs": 215, "vision_score": 23, "duration": 1800, "champion": "Ahri", "role": "MID"},
            {"win": 0, "kills": 4, "deaths": 4, "assists": 2, "cs": 180, "vision_score": 15, "duration": 1800, "champion": "Orianna", "role": "MID"},
        ]
        tags_otp = SummonerProfiler.generate_tags(otp_matches)
        self.assertIn("ONE_TRICK_PONY", tags_otp)

        cold_matches = [
            {"win": 0, "kills": 2, "deaths": 5, "assists": 3, "cs": 160, "vision_score": 12, "duration": 1700, "champion": "Ahri", "role": "MID"},
            {"win": 0, "kills": 1, "deaths": 4, "assists": 2, "cs": 170, "vision_score": 14, "duration": 1650, "champion": "Ahri", "role": "MID"},
            {"win": 0, "kills": 3, "deaths": 6, "assists": 4, "cs": 180, "vision_score": 15, "duration": 1800, "champion": "Ahri", "role": "MID"},
            {"win": 0, "kills": 2, "deaths": 5, "assists": 1, "cs": 150, "vision_score": 11, "duration": 1550, "champion": "Ahri", "role": "MID"},
            {"win": 1, "kills": 6, "deaths": 2, "assists": 8, "cs": 220, "vision_score": 25, "duration": 1900, "champion": "Ahri", "role": "MID"},
        ]
        tags_cold = SummonerProfiler.generate_tags(cold_matches)
        self.assertIn("COLD_STREAK", tags_cold)

    # --------------------------------------------------------------------------
    # 4. iTero Draft Coach Intelligence Engine
    # --------------------------------------------------------------------------
    def test_13_draft_coach_composition_radar_and_damage_ratios(self):
        """Verify team comp radar (CC, Engage, Poke, Waveclear, Scaling) and damage breakdown."""
        coach = DraftCoach(self.db)
        blue_team = ["Aatrox", "LeeSin", "Ahri", "Jinx", "Thresh"]
        comp = coach.analyze_team_composition(blue_team)

        dmg = comp["damage_profile"]
        self.assertGreater(dmg["ad_ratio"], 0.0)
        self.assertGreater(dmg["ap_ratio"], 0.0)
        self.assertAlmostEqual(dmg["ad_ratio"] + dmg["ap_ratio"] + dmg["true_ratio"], 1.0, places=2)

        radar = comp["utility_radar"]
        self.assertGreaterEqual(radar["cc_rating"], 0.0)
        self.assertLessEqual(radar["cc_rating"], 100.0)
        self.assertGreaterEqual(radar["engage_rating"], 0.0)

        spike = comp["power_spike"]
        self.assertIn("early_game", spike)
        self.assertIn("late_game", spike)

    def test_14_draft_coach_damage_overload_warning(self):
        """Verify critical warning when a team has >82% AD or AP."""
        coach = DraftCoach(self.db)
        # All-AD comp
        all_ad_team = ["Aatrox", "LeeSin", "Darius", "Jinx", "Caitlyn"]
        comp = coach.analyze_team_composition(all_ad_team)
        self.assertGreater(comp["damage_profile"]["ad_ratio"], 0.82)
        self.assertIsNotNone(comp["damage_profile"]["warning"])
        self.assertIn("AD OVERLOAD", comp["damage_profile"]["warning"])

    def test_15_draft_coach_synergies_and_counters(self):
        """Verify pairwise synergy bonuses and counter advantage calculations."""
        coach = DraftCoach(self.db)

        # Malphite + Yasuo synergy
        synergy_score = coach.compute_synergy_score(["Malphite", "Yasuo", "Ahri"])
        self.assertAlmostEqual(synergy_score, 0.12, places=2)

        # Kassadin counters LeBlanc
        counter_score = coach.compute_counter_score(["Kassadin"], ["LeBlanc"])
        self.assertGreater(counter_score, 0.0)

    def test_16_draft_coach_monte_carlo_simulation(self):
        """Verify 10,000-run Monte Carlo draft simulation consistency and determinism."""
        coach = DraftCoach(self.db)
        # Blue has high synergy (Malphite + Yasuo + Jinx + Lulu)
        blue = ["Malphite", "Yasuo", "Jinx", "Lulu", "Orianna"]
        red = ["Darius", "Amumu", "LeBlanc", "Caitlyn", "Blitzcrank"]

        sim = coach.simulate_win_probability(blue, red, iterations=10000, seed=42)
        self.assertEqual(sim["iterations"], 10000)
        self.assertAlmostEqual(sim["blue_win_rate"] + sim["red_win_rate"], 1.0, places=3)
        self.assertGreater(sim["blue_win_rate"], 0.55)

    def test_17_draft_coach_recommend_picks(self):
        """Verify AI draft assistant candidate ranking and role filtering."""
        coach = DraftCoach(self.db)
        current_team = ["Yasuo"]
        enemy_team = ["LeBlanc"]

        recs = coach.recommend_picks(current_team, enemy_team, role="MID", top_n=3)
        self.assertGreaterEqual(len(recs), 1)
        self.assertEqual(recs[0]["champion"], "Kassadin")  # Hard counters LeBlanc
        self.assertIn("Matchup counter advantage", recs[0]["reasoning"])

    # --------------------------------------------------------------------------
    # 5. UI Initialization & End-to-End Integration
    # --------------------------------------------------------------------------
    def test_18_desktop_app_headless_initialization(self):
        """Verify DesktopApp initializes headless, builds all tabs, and triggers updates."""
        app = DesktopApp(headless=True, db=self.db)
        self.assertIsNotNone(app.root)

        # Switch tabs and verify no exceptions
        app.select_tab("DRAFT COACH")
        self.assertEqual(app.current_tab, "DRAFT COACH")
        app.update_draft_analysis()

        app.select_tab("SUMMONER PROFILE")
        self.assertEqual(app.current_tab, "SUMMONER PROFILE")
        app.search_summoner_profile()

        app.select_tab("LIVE GAME")
        self.assertEqual(app.current_tab, "LIVE GAME")
        app.refresh_live_game()

        app.root.destroy()

    def test_19_end_to_end_integration(self):
        """Verify end-to-end flow from LCU -> Profiler -> DB -> Draft Coach."""
        connector = LCUConnector(use_mock_fallback=True)
        live_game = connector.get_live_game_data()
        self.assertIsNotNone(live_game)

        # Extract champions and simulate
        blue_champs = [p["champion"] for p in live_game["blue_team"]]
        red_champs = [p["champion"] for p in live_game["red_team"]]

        coach = DraftCoach(self.db)
        sim = coach.simulate_win_probability(blue_champs, red_champs, iterations=5000)
        self.assertGreater(sim["blue_win_rate"], 0.0)
        self.assertLess(sim["blue_win_rate"], 1.0)

        # Extract Faker performance and tags
        faker_p = [p for p in live_game["blue_team"] if p["summoner_name"] == "Hide on bush"][0]
        tags = SummonerProfiler.generate_tags([], live_stats={**faker_p, "game_time": live_game["game_time"]})
        self.assertIn("VISION_PRODIGY", tags)
        self.assertIn("FARM_MACHINE", tags)


if __name__ == "__main__":
    unittest.main()
