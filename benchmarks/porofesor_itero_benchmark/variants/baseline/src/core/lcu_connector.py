"""Hextech Oracle - Live Client Data & LCU Connector with Mock Daemon."""

import json
import logging
import os
import socket
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_LIVE_CLIENT_URL = "http://127.0.0.1:2999/liveclientdata/allgamedata"
DEFAULT_ACTIVE_PLAYER_URL = "http://127.0.0.1:2999/liveclientdata/activeplayer"


class MockLCUDaemon:
    """Deterministic fixture simulator providing active summoner and live match states."""

    def __init__(self, seed_file_path: Optional[str] = None):
        """Initialize mock daemon with deterministic seed data."""
        self.active_summoner: Dict[str, Any] = {
            "puuid": "kr-faker-001",
            "name": "Hide on bush",
            "tag_line": "KR1",
            "level": 642,
            "tier": "CHALLENGER",
            "rank": "I",
            "lp": 984,
            "wins": 240,
            "losses": 155,
            "last_updated": time.time(),
        }

        self.live_game: Dict[str, Any] = {
            "game_id": 6948211029,
            "game_mode": "CLASSIC",
            "game_time": 940.5,
            "blue_team": [
                {"summoner_name": "T1 Zeus", "champion": "Aatrox", "role": "TOP", "kills": 3, "deaths": 1, "assists": 2, "cs": 148, "gold": 5600, "vision_score": 18},
                {"summoner_name": "T1 Oner", "champion": "LeeSin", "role": "JUNGLE", "kills": 4, "deaths": 2, "assists": 5, "cs": 98, "gold": 5100, "vision_score": 24},
                {"summoner_name": "Hide on bush", "champion": "Ahri", "role": "MID", "kills": 5, "deaths": 0, "assists": 6, "cs": 162, "gold": 6800, "vision_score": 28},
                {"summoner_name": "T1 Gumayusi", "champion": "Jinx", "role": "ADC", "kills": 2, "deaths": 1, "assists": 4, "cs": 175, "gold": 6200, "vision_score": 14},
                {"summoner_name": "T1 Keria", "champion": "Thresh", "role": "SUPPORT", "kills": 0, "deaths": 1, "assists": 8, "cs": 18, "gold": 3800, "vision_score": 42},
            ],
            "red_team": [
                {"summoner_name": "GenG Kiin", "champion": "Darius", "role": "TOP", "kills": 1, "deaths": 3, "assists": 0, "cs": 130, "gold": 4800, "vision_score": 12},
                {"summoner_name": "GenG Canyon", "champion": "Amumu", "role": "JUNGLE", "kills": 1, "deaths": 3, "assists": 2, "cs": 90, "gold": 4300, "vision_score": 19},
                {"summoner_name": "GenG Chovy", "champion": "LeBlanc", "role": "MID", "kills": 2, "deaths": 3, "assists": 1, "cs": 155, "gold": 5400, "vision_score": 20},
                {"summoner_name": "GenG Peyz", "champion": "Caitlyn", "role": "ADC", "kills": 1, "deaths": 2, "assists": 1, "cs": 160, "gold": 5300, "vision_score": 15},
                {"summoner_name": "GenG Lehends", "champion": "Blitzcrank", "role": "SUPPORT", "kills": 0, "deaths": 3, "assists": 2, "cs": 22, "gold": 3400, "vision_score": 30},
            ],
        }

        self._load_from_seed(seed_file_path)

    def _load_from_seed(self, file_path: Optional[str]) -> None:
        """Attempt to load mock state from seed_data.json."""
        paths = [
            file_path,
            os.environ.get("HEXTECH_SEED_DATA"),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "mock_data", "seed_data.json")),
            os.path.abspath(os.path.join(os.getcwd(), "mock_data", "seed_data.json")),
        ]
        for p in paths:
            if p and os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    mock_state = data.get("mock_lcu_state", {})
                    if "active_summoner" in mock_state:
                        self.active_summoner = mock_state["active_summoner"]
                        self.active_summoner["last_updated"] = time.time()
                    if "live_game" in mock_state:
                        self.live_game = mock_state["live_game"]
                    break
                except Exception as e:
                    logger.debug(f"Could not load seed file {p}: {e}")

    def get_active_summoner(self) -> Dict[str, Any]:
        """Return active mock summoner."""
        return dict(self.active_summoner)

    def get_live_game_data(self) -> Dict[str, Any]:
        """Return live mock 5v5 match state."""
        return dict(self.live_game)

    def generate_mock_matches(self, puuid: str = "kr-faker-001", count: int = 20) -> List[Dict[str, Any]]:
        """Generate 20 deterministic match history records for testing and profiling."""
        templates = [
            {"champ": "Ahri", "role": "MID", "k": 7, "d": 1, "a": 9, "cs": 240, "vis": 46, "win": 1, "dur": 1820},
            {"champ": "Ahri", "role": "MID", "k": 8, "d": 2, "a": 6, "cs": 265, "vis": 48, "win": 1, "dur": 1910},
            {"champ": "Orianna", "role": "MID", "k": 6, "d": 1, "a": 11, "cs": 280, "vis": 52, "win": 1, "dur": 2040},
            {"champ": "LeBlanc", "role": "MID", "k": 10, "d": 2, "a": 4, "cs": 220, "vis": 42, "win": 1, "dur": 1650},
            {"champ": "Ahri", "role": "MID", "k": 5, "d": 3, "a": 7, "cs": 230, "vis": 44, "win": 0, "dur": 1780},
            {"champ": "Sylas", "role": "MID", "k": 9, "d": 3, "a": 8, "cs": 245, "vis": 47, "win": 1, "dur": 1890},
            {"champ": "Ahri", "role": "MID", "k": 6, "d": 1, "a": 10, "cs": 270, "vis": 50, "win": 1, "dur": 1950},
            {"champ": "Orianna", "role": "MID", "k": 4, "d": 2, "a": 12, "cs": 290, "vis": 54, "win": 1, "dur": 2100},
            {"champ": "Ahri", "role": "MID", "k": 7, "d": 2, "a": 5, "cs": 250, "vis": 49, "win": 1, "dur": 1830},
            {"champ": "LeBlanc", "role": "MID", "k": 3, "d": 4, "a": 2, "cs": 190, "vis": 38, "win": 0, "dur": 1580},
            {"champ": "Ahri", "role": "MID", "k": 8, "d": 1, "a": 7, "cs": 260, "vis": 51, "win": 1, "dur": 1870},
            {"champ": "Sylas", "role": "MID", "k": 7, "d": 2, "a": 6, "cs": 235, "vis": 45, "win": 1, "dur": 1790},
            {"champ": "Ahri", "role": "MID", "k": 9, "d": 0, "a": 8, "cs": 285, "vis": 53, "win": 1, "dur": 1920},
            {"champ": "Orianna", "role": "MID", "k": 5, "d": 2, "a": 9, "cs": 275, "vis": 50, "win": 1, "dur": 1980},
            {"champ": "Ahri", "role": "MID", "k": 4, "d": 3, "a": 5, "cs": 210, "vis": 43, "win": 0, "dur": 1720},
            {"champ": "LeBlanc", "role": "MID", "k": 11, "d": 2, "a": 6, "cs": 240, "vis": 48, "win": 1, "dur": 1810},
            {"champ": "Ahri", "role": "MID", "k": 7, "d": 1, "a": 8, "cs": 255, "vis": 52, "win": 1, "dur": 1860},
            {"champ": "Sylas", "role": "MID", "k": 6, "d": 3, "a": 7, "cs": 225, "vis": 45, "win": 1, "dur": 1740},
            {"champ": "Ahri", "role": "MID", "k": 8, "d": 2, "a": 9, "cs": 270, "vis": 54, "win": 1, "dur": 1940},
            {"champ": "Orianna", "role": "MID", "k": 6, "d": 1, "a": 13, "cs": 300, "vis": 58, "win": 1, "dur": 2150},
        ]

        now = time.time()
        matches = []
        for i in range(min(count, len(templates))):
            t = templates[i]
            matches.append({
                "match_id": f"KR-{6948200000 + i}",
                "puuid": puuid,
                "champion": t["champ"],
                "kills": t["k"],
                "deaths": t["d"],
                "assists": t["a"],
                "cs": t["cs"],
                "vision_score": t["vis"],
                "win": t["win"],
                "duration": t["dur"],
                "role": t["role"],
                "timestamp": now - (i * 3600),
            })
        return matches


class LCUConnector:
    """Connector for Riot Client Live Client Data API with deterministic fallback."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 2999,
        timeout: float = 0.5,
        use_mock_fallback: bool = True,
        force_mock: bool = False,
    ):
        """Initialize LCUConnector.

        Args:
            host: Live Client Data API host.
            port: Live Client Data API port (default: 2999).
            timeout: Network socket timeout in seconds.
            use_mock_fallback: If True, falls back to MockLCUDaemon when client is offline.
            force_mock: If True, bypasses network probe and always serves mock data.
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.use_mock_fallback = use_mock_fallback
        self.force_mock = force_mock
        self.mock_daemon = MockLCUDaemon()

    def is_client_running(self) -> bool:
        """Probe if the real League of Legends Live Client API is accessible."""
        if self.force_mock:
            return False

        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout):
                return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            return False

    def get_connection_status(self) -> str:
        """Return human-readable connection status indicator."""
        if self.is_client_running():
            return "CONNECTED [LIVE]"
        elif self.use_mock_fallback:
            return "SIMULATED [OFFLINE MOCK]"
        else:
            return "DISCONNECTED"

    def get_active_summoner(self) -> Optional[Dict[str, Any]]:
        """Fetch current active summoner account details."""
        if self.is_client_running():
            try:
                req = urllib.request.Request(
                    DEFAULT_ACTIVE_PLAYER_URL,
                    headers={"User-Agent": "HextechOracle/1.0"},
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        return {
                            "puuid": data.get("summonerName", "live-player"),
                            "name": data.get("summonerName", "Summoner"),
                            "tag_line": "LIVE",
                            "level": data.get("level", 30),
                            "tier": "RANKED",
                            "rank": "LIVE",
                            "lp": 100,
                            "wins": 0,
                            "losses": 0,
                            "last_updated": time.time(),
                        }
            except Exception as e:
                logger.debug(f"Live player endpoint unreachable: {e}")

        if self.use_mock_fallback:
            return self.mock_daemon.get_active_summoner()
        return None

    def get_live_game_data(self) -> Optional[Dict[str, Any]]:
        """Fetch current 5v5 live match state."""
        if self.is_client_running():
            try:
                req = urllib.request.Request(
                    DEFAULT_LIVE_CLIENT_URL,
                    headers={"User-Agent": "HextechOracle/1.0"},
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    if resp.status == 200:
                        raw = json.loads(resp.read().decode("utf-8"))
                        return self._normalize_live_game_data(raw)
            except Exception as e:
                logger.debug(f"Live match endpoint unreachable: {e}")

        if self.use_mock_fallback:
            return self.mock_daemon.get_live_game_data()
        return None

    def _normalize_live_game_data(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize Riot Live Client Data API structure to Hextech Oracle standard."""
        all_players = raw.get("allPlayers", [])
        game_data = raw.get("gameData", {})

        blue_team = []
        red_team = []

        for p in all_players:
            team_str = p.get("team", "ORDER")  # ORDER = Blue, CHAOS = Red
            player_obj = {
                "summoner_name": p.get("summonerName", "Unknown"),
                "champion": p.get("championName", "Unknown"),
                "role": p.get("position", "MID"),
                "kills": p.get("scores", {}).get("kills", 0),
                "deaths": p.get("scores", {}).get("deaths", 0),
                "assists": p.get("scores", {}).get("assists", 0),
                "cs": p.get("scores", {}).get("creepScore", 0),
                "gold": 0,
                "vision_score": p.get("scores", {}).get("wardScore", 0),
            }
            if team_str == "ORDER":
                blue_team.append(player_obj)
            else:
                red_team.append(player_obj)

        return {
            "game_id": raw.get("gameId", 0),
            "game_mode": game_data.get("gameMode", "CLASSIC"),
            "game_time": game_data.get("gameTime", 0.0),
            "blue_team": blue_team,
            "red_team": red_team,
        }
