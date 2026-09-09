"""
LCU (League Client Update) and Live Client Data Connector for Hextech Oracle.
Includes deterministic MockLCUDaemon fixture simulator for offline testing.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import socket
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

# Standard Riot Live Client Data API endpoint
LIVE_CLIENT_URL = "http://127.0.0.1:2999/liveclientdata/allgamedata"
LIVE_ACTIVE_PLAYER_URL = "http://127.0.0.1:2999/liveclientdata/activeplayername"


class MockLCUDaemon:
    """
    Deterministic fixture simulator providing active summoner 'Faker#KR1'
    and a live 5v5 game state (Blue Team vs Red Team) for offline development and testing.
    """

    DEFAULT_SUMMONER: Dict[str, Any] = {
        "puuid": "kr-faker-001",
        "name": "Hide on bush",
        "tag_line": "KR1",
        "level": 642,
        "tier": "CHALLENGER",
        "rank": "I",
        "lp": 984,
        "wins": 240,
        "losses": 155,
    }

    DEFAULT_LIVE_GAME: Dict[str, Any] = {
        "game_id": 6948211029,
        "game_mode": "CLASSIC",
        "game_time": 940.5,
        "blue_team": [
            {
                "summoner_name": "T1 Zeus",
                "champion": "Aatrox",
                "role": "TOP",
                "kills": 3,
                "deaths": 1,
                "assists": 2,
                "cs": 148,
                "gold": 5600,
            },
            {
                "summoner_name": "T1 Oner",
                "champion": "LeeSin",
                "role": "JUNGLE",
                "kills": 4,
                "deaths": 2,
                "assists": 5,
                "cs": 98,
                "gold": 5100,
            },
            {
                "summoner_name": "Hide on bush",
                "champion": "Ahri",
                "role": "MID",
                "kills": 5,
                "deaths": 0,
                "assists": 6,
                "cs": 162,
                "gold": 6800,
            },
            {
                "summoner_name": "T1 Gumayusi",
                "champion": "Jinx",
                "role": "ADC",
                "kills": 2,
                "deaths": 1,
                "assists": 4,
                "cs": 175,
                "gold": 6200,
            },
            {
                "summoner_name": "T1 Keria",
                "champion": "Thresh",
                "role": "SUPPORT",
                "kills": 0,
                "deaths": 1,
                "assists": 8,
                "cs": 18,
                "gold": 3800,
            },
        ],
        "red_team": [
            {
                "summoner_name": "GenG Kiin",
                "champion": "Darius",
                "role": "TOP",
                "kills": 1,
                "deaths": 3,
                "assists": 0,
                "cs": 130,
                "gold": 4800,
            },
            {
                "summoner_name": "GenG Canyon",
                "champion": "Amumu",
                "role": "JUNGLE",
                "kills": 1,
                "deaths": 3,
                "assists": 2,
                "cs": 90,
                "gold": 4300,
            },
            {
                "summoner_name": "GenG Chovy",
                "champion": "LeBlanc",
                "role": "MID",
                "kills": 2,
                "deaths": 3,
                "assists": 1,
                "cs": 155,
                "gold": 5400,
            },
            {
                "summoner_name": "GenG Peyz",
                "champion": "Caitlyn",
                "role": "ADC",
                "kills": 1,
                "deaths": 2,
                "assists": 1,
                "cs": 160,
                "gold": 5300,
            },
            {
                "summoner_name": "GenG Lehends",
                "champion": "Blitzcrank",
                "role": "SUPPORT",
                "kills": 0,
                "deaths": 3,
                "assists": 2,
                "cs": 22,
                "gold": 3400,
            },
        ],
    }

    def __init__(self, seed_file_path: Optional[str] = None) -> None:
        self.active_summoner: Dict[str, Any] = dict(self.DEFAULT_SUMMONER)
        self.live_game: Dict[str, Any] = json.loads(json.dumps(self.DEFAULT_LIVE_GAME))
        self._running: bool = True

        if seed_file_path:
            self.load_from_seed(seed_file_path)
        else:
            self._try_load_default_seed()

    def _try_load_default_seed(self) -> None:
        """Attempt to find and load from seed_data.json if present."""
        possible_paths = [
            Path(__file__).resolve().parent.parent.parent / "mock_data" / "seed_data.json",
            Path(__file__).resolve().parent.parent.parent.parent / "mock_data" / "seed_data.json",
            Path.cwd() / "mock_data" / "seed_data.json",
            Path.cwd().parent / "mock_data" / "seed_data.json",
            Path.cwd().parent.parent / "mock_data" / "seed_data.json",
        ]
        for p in possible_paths:
            if p.exists():
                self.load_from_seed(str(p))
                break

    def load_from_seed(self, seed_path: str) -> None:
        """Load mock state from external seed file."""
        try:
            with open(seed_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            mock_state = data.get("mock_lcu_state", {})
            if "active_summoner" in mock_state:
                self.active_summoner = mock_state["active_summoner"]
            if "live_game" in mock_state:
                self.live_game = mock_state["live_game"]
        except Exception as err:
            logger.warning("Failed to load seed file %s into MockLCUDaemon: %s", seed_path, err)

    def is_running(self) -> bool:
        """Mock daemon status flag."""
        return self._running

    def set_running(self, running: bool) -> None:
        self._running = running

    def get_active_summoner(self) -> Dict[str, Any]:
        """Return the mock active summoner (Faker#KR1)."""
        return dict(self.active_summoner)

    def get_live_game_data(self) -> Dict[str, Any]:
        """Return deterministic 5v5 match state."""
        return json.loads(json.dumps(self.live_game))

    def advance_game_time(self, delta_seconds: float = 10.0) -> None:
        """Advance game time and incrementally update stats."""
        self.live_game["game_time"] += delta_seconds
        for player in self.live_game.get("blue_team", []) + self.live_game.get("red_team", []):
            player["gold"] += int(delta_seconds * 3.5)
            if player["role"] != "SUPPORT":
                player["cs"] += int(delta_seconds * 0.15)


class LCUConnector:
    """
    Live Client Data API connector with automatic process polling
    and fallback to deterministic MockLCUDaemon.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 2999,
        timeout: float = 0.5,
        use_mock_fallback: bool = True,
        seed_file_path: Optional[str] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.use_mock_fallback = use_mock_fallback
        self.mock_daemon = MockLCUDaemon(seed_file_path=seed_file_path)
        self.live_endpoint = f"http://{self.host}:{self.port}/liveclientdata/allgamedata"
        self.active_player_endpoint = f"http://{self.host}:{self.port}/liveclientdata/activeplayername"

    def is_client_running(self) -> bool:
        """Probe live client port 2999 to check if active game is running."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.timeout)
                result = sock.connect_ex((self.host, self.port))
                return result == 0
        except (socket.error, OSError):
            return False

    def get_status(self) -> str:
        """Return human-readable connection status."""
        if self.is_client_running():
            return "CONNECTED [LIVE]"
        if self.use_mock_fallback and self.mock_daemon.is_running():
            return "SIMULATED [OFFLINE MOCK]"
        return "DISCONNECTED"

    def get_active_summoner(self) -> Optional[Dict[str, Any]]:
        """
        Returns current active summoner profile.
        Queries live client or falls back to mock daemon.
        """
        if self.is_client_running():
            try:
                req = urllib.request.Request(
                    self.active_player_endpoint,
                    headers={"User-Agent": "Hextech-Oracle/1.0"},
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    raw_data = response.read().decode("utf-8").strip()
                    # Endpoint returns raw quoted string e.g. "Hide on bush"
                    summoner_name = json.loads(raw_data) if raw_data.startswith('"') else raw_data
                    return {
                        "puuid": "live-active-puuid",
                        "name": summoner_name,
                        "tag_line": "LIVE",
                        "level": 30,
                        "tier": "UNRANKED",
                        "rank": "I",
                        "lp": 0,
                        "wins": 0,
                        "losses": 0,
                    }
            except Exception as err:
                logger.debug("Live active summoner query failed: %s", err)

        if self.use_mock_fallback and self.mock_daemon.is_running():
            return self.mock_daemon.get_active_summoner()

        return None

    def get_live_game_data(self) -> Optional[Dict[str, Any]]:
        """
        Polls current 5v5 match state.
        Returns parsed live game dict or falls back to MockLCUDaemon.
        """
        if self.is_client_running():
            try:
                req = urllib.request.Request(
                    self.live_endpoint,
                    headers={"User-Agent": "Hextech-Oracle/1.0"},
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    raw_data = response.read().decode("utf-8")
                    data = json.loads(raw_data)
                    return self._normalize_live_client_data(data)
            except Exception as err:
                logger.debug("Live game data query failed: %s", err)

        if self.use_mock_fallback and self.mock_daemon.is_running():
            return self.mock_daemon.get_live_game_data()

        return None

    def _normalize_live_client_data(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert official Riot Live Client Data API structure into standard 5v5 model."""
        all_players = raw_data.get("allPlayers", [])
        game_data = raw_data.get("gameData", {})

        blue_team: List[Dict[str, Any]] = []
        red_team: List[Dict[str, Any]] = []

        for p in all_players:
            scores = p.get("scores", {})
            team_str = p.get("team", "ORDER")  # ORDER = Blue, CHAOS = Red
            player_obj = {
                "summoner_name": p.get("summonerName", "Unknown"),
                "champion": p.get("championName", "Unknown"),
                "role": p.get("position", "NONE"),
                "kills": int(scores.get("kills", 0)),
                "deaths": int(scores.get("deaths", 0)),
                "assists": int(scores.get("assists", 0)),
                "cs": int(scores.get("creepScore", 0)),
                "gold": int(p.get("currentGold", 0)),
            }
            if team_str == "ORDER":
                blue_team.append(player_obj)
            else:
                red_team.append(player_obj)

        return {
            "game_id": game_data.get("gameId", 1),
            "game_mode": game_data.get("gameMode", "CLASSIC"),
            "game_time": float(game_data.get("gameTime", 0.0)),
            "blue_team": blue_team,
            "red_team": red_team,
        }
