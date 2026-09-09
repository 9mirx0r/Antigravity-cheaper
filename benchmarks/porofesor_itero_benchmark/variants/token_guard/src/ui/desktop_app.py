"""
Native Desktop GUI application for Hextech Oracle (Aegis-LoL).
Strictly implements the Hextech Dark theme with ZERO emojis.
Synthesizes Porofesor live match analysis and iTero AI draft intelligence.
"""

from __future__ import annotations

import logging
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Dict, List, Optional

from src.analytics.summoner_profiler import SummonerProfiler
from src.core.lcu_connector import LCUConnector
from src.draft.draft_coach import DraftCoach
from src.storage.db import HextechDatabase

logger = logging.getLogger(__name__)

# Hextech Dark Design Palette
COLOR_BG = "#010A13"
COLOR_SURFACE = "#0A1428"
COLOR_CONTAINER = "#0E1A2E"
COLOR_CARD = "#06101E"
COLOR_BORDER = "#1E282D"
COLOR_GOLD = "#C89B3C"
COLOR_GOLD_BRIGHT = "#F0E6D2"
COLOR_TEAL = "#0AC8B9"
COLOR_TEXT = "#F0E6D2"
COLOR_TEXT_MUTED = "#A09B8C"
COLOR_BLUE_TEAM = "#1E90FF"
COLOR_RED_TEAM = "#E84057"
COLOR_WIN = "#0AC8B9"
COLOR_LOSS = "#E84057"

FONT_TITLE = ("Consolas", 16, "bold")
FONT_SUBTITLE = ("Consolas", 12, "bold")
FONT_SECTION = ("Consolas", 11, "bold")
FONT_BODY = ("Consolas", 9)
FONT_BODY_BOLD = ("Consolas", 9, "bold")
FONT_BADGE = ("Consolas", 8, "bold")
FONT_STATUS = ("Consolas", 10, "bold")


class HextechOracleApp:
    """
    Main desktop window controller for Hextech Oracle.
    3 Core Tabs: LIVE GAME, DRAFT COACH, SUMMONER PROFILE.
    """

    def __init__(
        self,
        db: Optional[HextechDatabase] = None,
        connector: Optional[LCUConnector] = None,
        profiler: Optional[SummonerProfiler] = None,
        coach: Optional[DraftCoach] = None,
        headless: bool = False,
    ) -> None:
        self.headless = headless

        # Core Engines
        self.db = db if db is not None else HextechDatabase()
        self.connector = connector if connector is not None else LCUConnector()
        self.profiler = profiler if profiler is not None else SummonerProfiler()
        self.coach = coach if coach is not None else DraftCoach(self.db)

        # Ensure baseline Faker sample matches exist for rich profile exploration
        self._ensure_sample_matches()

        # Build UI Root
        self.root = tk.Tk()
        self.root.title("HEXTECH ORACLE // AEGIS-LOL [SYSTEM v1.0]")
        self.root.geometry("1140x740")
        self.root.minsize(1020, 680)
        self.root.configure(bg=COLOR_BG)

        # Center on primary monitor and force to foreground
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = max(0, (sw - 1140) // 2)
        y = max(0, (sh - 740) // 2)
        self.root.geometry(f"1140x740+{x}+{y}")
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(300, lambda: self.root.attributes("-topmost", False))
        self.root.focus_force()

        # Style TTK widgets
        self._setup_styles()

        # Build Layout
        self._build_header()
        self._build_tabs()
        self._build_status_bar()

        # Populate Initial Data
        self.refresh_live_game()
        self.load_summoner_profile("kr-faker-001")

        if self.headless:
            self.root.withdraw()
            self.root.update_idletasks()

    def _ensure_sample_matches(self) -> None:
        """Seed 20 realistic match history records for Faker if empty."""
        faker_puuid = "kr-faker-001"
        existing = self.db.get_summoner_history(faker_puuid, limit=1)
        if not existing:
            sample_matches = [
                {"match_id": "KR_6948211029", "puuid": faker_puuid, "champion": "Ahri", "kills": 8, "deaths": 1, "assists": 9, "cs": 242, "vision_score": 45, "win": 1, "duration": 1850},
                {"match_id": "KR_6948211028", "puuid": faker_puuid, "champion": "Orianna", "kills": 6, "deaths": 2, "assists": 11, "cs": 268, "vision_score": 48, "win": 1, "duration": 1920},
                {"match_id": "KR_6948211027", "puuid": faker_puuid, "champion": "LeBlanc", "kills": 9, "deaths": 3, "assists": 5, "cs": 210, "vision_score": 38, "win": 1, "duration": 1710},
                {"match_id": "KR_6948211026", "puuid": faker_puuid, "champion": "Sylas", "kills": 7, "deaths": 2, "assists": 8, "cs": 225, "vision_score": 40, "win": 1, "duration": 1800},
                {"match_id": "KR_6948211025", "puuid": faker_puuid, "champion": "Ahri", "kills": 6, "deaths": 4, "assists": 7, "cs": 255, "vision_score": 52, "win": 0, "duration": 1980},
                {"match_id": "KR_6948211024", "puuid": faker_puuid, "champion": "Orianna", "kills": 7, "deaths": 1, "assists": 14, "cs": 280, "vision_score": 46, "win": 1, "duration": 2040},
                {"match_id": "KR_6948211023", "puuid": faker_puuid, "champion": "Ahri", "kills": 10, "deaths": 2, "assists": 8, "cs": 245, "vision_score": 44, "win": 1, "duration": 1780},
                {"match_id": "KR_6948211022", "puuid": faker_puuid, "champion": "Zed", "kills": 11, "deaths": 3, "assists": 4, "cs": 230, "vision_score": 36, "win": 1, "duration": 1650},
                {"match_id": "KR_6948211021", "puuid": faker_puuid, "champion": "Sylas", "kills": 4, "deaths": 3, "assists": 6, "cs": 195, "vision_score": 34, "win": 0, "duration": 1720},
                {"match_id": "KR_6948211020", "puuid": faker_puuid, "champion": "Ahri", "kills": 8, "deaths": 0, "assists": 10, "cs": 260, "vision_score": 50, "win": 1, "duration": 1820},
                {"match_id": "KR_6948211019", "puuid": faker_puuid, "champion": "LeBlanc", "kills": 9, "deaths": 2, "assists": 6, "cs": 215, "vision_score": 39, "win": 1, "duration": 1680},
                {"match_id": "KR_6948211018", "puuid": faker_puuid, "champion": "Orianna", "kills": 5, "deaths": 2, "assists": 12, "cs": 290, "vision_score": 47, "win": 1, "duration": 2100},
                {"match_id": "KR_6948211017", "puuid": faker_puuid, "champion": "Ahri", "kills": 7, "deaths": 3, "assists": 7, "cs": 238, "vision_score": 43, "win": 1, "duration": 1790},
                {"match_id": "KR_6948211016", "puuid": faker_puuid, "champion": "Kassadin", "kills": 8, "deaths": 4, "assists": 5, "cs": 270, "vision_score": 41, "win": 1, "duration": 2010},
                {"match_id": "KR_6948211015", "puuid": faker_puuid, "champion": "Ahri", "kills": 3, "deaths": 5, "assists": 4, "cs": 220, "vision_score": 38, "win": 0, "duration": 1690},
                {"match_id": "KR_6948211014", "puuid": faker_puuid, "champion": "Sylas", "kills": 8, "deaths": 1, "assists": 9, "cs": 240, "vision_score": 42, "win": 1, "duration": 1830},
                {"match_id": "KR_6948211013", "puuid": faker_puuid, "champion": "Orianna", "kills": 6, "deaths": 2, "assists": 10, "cs": 275, "vision_score": 49, "win": 1, "duration": 1950},
                {"match_id": "KR_6948211012", "puuid": faker_puuid, "champion": "Ahri", "kills": 9, "deaths": 2, "assists": 8, "cs": 250, "vision_score": 46, "win": 1, "duration": 1810},
                {"match_id": "KR_6948211011", "puuid": faker_puuid, "champion": "LeBlanc", "kills": 10, "deaths": 1, "assists": 5, "cs": 225, "vision_score": 37, "win": 1, "duration": 1640},
                {"match_id": "KR_6948211010", "puuid": faker_puuid, "champion": "Ahri", "kills": 6, "deaths": 3, "assists": 9, "cs": 248, "vision_score": 45, "win": 1, "duration": 1840},
            ]
            self.db.record_matches(sample_matches)

    def _setup_styles(self) -> None:
        """Configure dark ttk theme elements."""
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(".", background=COLOR_BG, foreground=COLOR_TEXT, font=FONT_BODY)
        style.configure(
            "TNotebook",
            background=COLOR_BG,
            borderwidth=0,
            tabmargins=[2, 5, 2, 0],
        )
        style.configure(
            "TNotebook.Tab",
            background=COLOR_SURFACE,
            foreground=COLOR_TEXT_MUTED,
            font=FONT_SECTION,
            padding=[16, 8],
            borderwidth=1,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", COLOR_CONTAINER), ("active", COLOR_SURFACE)],
            foreground=[("selected", COLOR_GOLD), ("active", COLOR_TEXT)],
        )

        style.configure(
            "TCombobox",
            fieldbackground=COLOR_SURFACE,
            background=COLOR_SURFACE,
            foreground=COLOR_GOLD,
            arrowcolor=COLOR_GOLD,
            bordercolor=COLOR_BORDER,
            darkcolor=COLOR_BORDER,
            lightcolor=COLOR_BORDER,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", COLOR_SURFACE)],
            selectbackground=[("readonly", COLOR_SURFACE)],
            selectforeground=[("readonly", COLOR_GOLD)],
        )

    def _build_header(self) -> None:
        """Build top application banner and global status badge."""
        header = tk.Frame(self.root, bg=COLOR_SURFACE, height=54, bd=0)
        header.pack(fill=tk.X, side=tk.TOP)

        title_frame = tk.Frame(header, bg=COLOR_SURFACE)
        title_frame.pack(side=tk.LEFT, padx=16, pady=8)

        lbl_title = tk.Label(
            title_frame,
            text="HEXTECH ORACLE",
            font=FONT_TITLE,
            fg=COLOR_GOLD,
            bg=COLOR_SURFACE,
        )
        lbl_title.pack(side=tk.LEFT)

        lbl_pipe = tk.Label(
            title_frame,
            text=" // ",
            font=FONT_TITLE,
            fg=COLOR_BORDER,
            bg=COLOR_SURFACE,
        )
        lbl_pipe.pack(side=tk.LEFT)

        lbl_sub = tk.Label(
            title_frame,
            text="AEGIS-LOL TACTICAL DRAFT & PROFILE ENGINE",
            font=FONT_SUBTITLE,
            fg=COLOR_TEXT_MUTED,
            bg=COLOR_SURFACE,
        )
        lbl_sub.pack(side=tk.LEFT)

        # Right Header Actions
        action_frame = tk.Frame(header, bg=COLOR_SURFACE)
        action_frame.pack(side=tk.RIGHT, padx=16, pady=8)

        self.lbl_client_status = tk.Label(
            action_frame,
            text=f"STATUS: {self.connector.get_status()}",
            font=FONT_STATUS,
            fg=COLOR_TEAL,
            bg=COLOR_CONTAINER,
            padx=10,
            pady=4,
            relief=tk.SOLID,
            bd=1,
        )
        self.lbl_client_status.pack(side=tk.LEFT, padx=8)

        btn_poll = tk.Button(
            action_frame,
            text="[POLL CLIENT]",
            font=FONT_BADGE,
            fg=COLOR_GOLD,
            bg=COLOR_CONTAINER,
            activebackground=COLOR_GOLD,
            activeforeground=COLOR_BG,
            bd=1,
            relief=tk.FLAT,
            command=self.refresh_live_game,
            padx=8,
            pady=2,
            cursor="hand2",
        )
        btn_poll.pack(side=tk.LEFT)

    def _build_status_bar(self) -> None:
        """Bottom technical status bar."""
        bar = tk.Frame(self.root, bg=COLOR_CONTAINER, height=24, bd=0)
        bar.pack(fill=tk.X, side=tk.BOTTOM)

        lbl_foot_left = tk.Label(
            bar,
            text="SYSTEM READY // ZERO EMOJIS ENFORCED // WAL SQLITE3 CONNECTED",
            font=FONT_BADGE,
            fg=COLOR_TEXT_MUTED,
            bg=COLOR_CONTAINER,
        )
        lbl_foot_left.pack(side=tk.LEFT, padx=12, pady=3)

        lbl_foot_right = tk.Label(
            bar,
            text="MONTE CARLO SAMPLER: ACTIVE // POROFESOR ENGINE: ONLINE",
            font=FONT_BADGE,
            fg=COLOR_TEAL,
            bg=COLOR_CONTAINER,
        )
        lbl_foot_right.pack(side=tk.RIGHT, padx=12, pady=3)

    def _build_tabs(self) -> None:
        """Instantiate Tab Container and views."""
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)

        # Tab 1: Live Game
        self.tab_live = tk.Frame(self.notebook, bg=COLOR_BG)
        self.notebook.add(self.tab_live, text="  LIVE GAME  ")
        self._build_live_game_tab()

        # Tab 2: Draft Coach
        self.tab_draft = tk.Frame(self.notebook, bg=COLOR_BG)
        self.notebook.add(self.tab_draft, text="  DRAFT COACH  ")
        self._build_draft_coach_tab()

        # Tab 3: Summoner Profile
        self.tab_profile = tk.Frame(self.notebook, bg=COLOR_BG)
        self.notebook.add(self.tab_profile, text="  SUMMONER PROFILE  ")
        self._build_profile_tab()

    # =========================================================================
    # TAB 1: LIVE GAME
    # =========================================================================
    def _build_live_game_tab(self) -> None:
        """Construct Live Game detection view."""
        # Top match overview banner
        self.live_banner = tk.Frame(self.tab_live, bg=COLOR_SURFACE, bd=1, relief=tk.SOLID)
        self.live_banner.pack(fill=tk.X, padx=8, pady=6)

        self.lbl_game_info = tk.Label(
            self.live_banner,
            text="GAME ID: -- | MODE: -- | TIME: --",
            font=FONT_SECTION,
            fg=COLOR_TEXT,
            bg=COLOR_SURFACE,
            padx=12,
            pady=6,
        )
        self.lbl_game_info.pack(side=tk.LEFT)

        self.lbl_gold_diff = tk.Label(
            self.live_banner,
            text="BLUE: 0 KILLS (0k G)  vs  RED: 0 KILLS (0k G) [DIFF: 0k]",
            font=FONT_SECTION,
            fg=COLOR_GOLD,
            bg=COLOR_SURFACE,
            padx=12,
            pady=6,
        )
        self.lbl_gold_diff.pack(side=tk.RIGHT)

        # 5v5 Split view
        teams_frame = tk.Frame(self.tab_live, bg=COLOR_BG)
        teams_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # Blue Team Panel
        self.blue_frame = tk.Frame(teams_frame, bg=COLOR_CONTAINER, bd=1, relief=tk.SOLID)
        self.blue_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 4))

        lbl_blue_hdr = tk.Label(
            self.blue_frame,
            text="[ORDER] BLUE TEAM",
            font=FONT_SECTION,
            fg=COLOR_BLUE_TEAM,
            bg=COLOR_SURFACE,
            pady=6,
        )
        lbl_blue_hdr.pack(fill=tk.X)

        self.blue_players_container = tk.Frame(self.blue_frame, bg=COLOR_CONTAINER)
        self.blue_players_container.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        # Red Team Panel
        self.red_frame = tk.Frame(teams_frame, bg=COLOR_CONTAINER, bd=1, relief=tk.SOLID)
        self.red_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(4, 0))

        lbl_red_hdr = tk.Label(
            self.red_frame,
            text="[CHAOS] RED TEAM",
            font=FONT_SECTION,
            fg=COLOR_RED_TEAM,
            bg=COLOR_SURFACE,
            pady=6,
        )
        lbl_red_hdr.pack(fill=tk.X)

        self.red_players_container = tk.Frame(self.red_frame, bg=COLOR_CONTAINER)
        self.red_players_container.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

    def refresh_live_game(self) -> None:
        """Poll connector and refresh 5v5 view."""
        status_text = self.connector.get_status()
        self.lbl_client_status.config(text=f"STATUS: {status_text}")

        live_data = self.connector.get_live_game_data()
        if not live_data:
            self.lbl_game_info.config(text="NO ACTIVE MATCH DETECTED // POLLING LCU")
            return

        game_id = live_data.get("game_id", "N/A")
        game_mode = live_data.get("game_mode", "CLASSIC")
        game_time = float(live_data.get("game_time", 0.0))
        minutes = int(game_time // 60)
        seconds = int(game_time % 60)

        self.lbl_game_info.config(
            text=f"MATCH: #{game_id} | MODE: {game_mode} | TIME: {minutes:02d}:{seconds:02d}"
        )

        blue_players = live_data.get("blue_team", [])
        red_players = live_data.get("red_team", [])

        blue_kills = sum(p.get("kills", 0) for p in blue_players)
        blue_gold = sum(p.get("gold", 0) for p in blue_players)
        red_kills = sum(p.get("kills", 0) for p in red_players)
        red_gold = sum(p.get("gold", 0) for p in red_players)

        gold_diff = blue_gold - red_gold
        diff_str = (
            f"[BLUE +{gold_diff // 1000}.{abs(gold_diff % 1000) // 100}k G]"
            if gold_diff >= 0
            else f"[RED +{abs(gold_diff) // 1000}.{abs(gold_diff % 1000) // 100}k G]"
        )

        self.lbl_gold_diff.config(
            text=f"BLUE: {blue_kills}K ({blue_gold // 1000}k G)  vs  RED: {red_kills}K ({red_gold // 1000}k G)  {diff_str}"
        )

        self._render_team_roster(self.blue_players_container, blue_players, is_blue=True)
        self._render_team_roster(self.red_players_container, red_players, is_blue=False)

    def _render_team_roster(
        self, container: tk.Frame, players: List[Dict[str, Any]], is_blue: bool
    ) -> None:
        """Render player cards in live game tab."""
        for child in container.winfo_children():
            child.destroy()

        for idx, p in enumerate(players):
            card = tk.Frame(
                container,
                bg=COLOR_CARD,
                bd=1,
                relief=tk.SOLID,
            )
            card.pack(fill=tk.X, pady=3, padx=2)

            # Role + Name row
            row1 = tk.Frame(card, bg=COLOR_CARD)
            row1.pack(fill=tk.X, padx=6, pady=(4, 2))

            role_lbl = tk.Label(
                row1,
                text=f"[{p.get('role', 'ROLE')}]",
                font=FONT_BADGE,
                fg=COLOR_GOLD,
                bg=COLOR_CARD,
                width=8,
                anchor="w",
            )
            role_lbl.pack(side=tk.LEFT)

            champ_lbl = tk.Label(
                row1,
                text=p.get("champion", "Unknown"),
                font=FONT_SECTION,
                fg=COLOR_TEXT,
                bg=COLOR_CARD,
                width=12,
                anchor="w",
            )
            champ_lbl.pack(side=tk.LEFT, padx=4)

            name_lbl = tk.Label(
                row1,
                text=p.get("summoner_name", "Unknown"),
                font=FONT_BODY,
                fg=COLOR_TEXT_MUTED,
                bg=COLOR_CARD,
            )
            name_lbl.pack(side=tk.LEFT)

            # KDA and Stats row
            row2 = tk.Frame(card, bg=COLOR_CARD)
            row2.pack(fill=tk.X, padx=6, pady=(0, 4))

            kda_text = f"KDA: {p.get('kills', 0)}/{p.get('deaths', 0)}/{p.get('assists', 0)}"
            stats_lbl = tk.Label(
                row2,
                text=f"{kda_text:<16} CS: {p.get('cs', 0):<4} GOLD: {p.get('gold', 0)}",
                font=FONT_BODY,
                fg=COLOR_TEAL,
                bg=COLOR_CARD,
            )
            stats_lbl.pack(side=tk.LEFT)

            # Evaluate instant tags for player
            player_history = self.db.get_summoner_history(
                p.get("summoner_name", ""), limit=10
            )
            tags = self.profiler.generate_tags(player_history, live_stats=p)
            if tags:
                tag_str = " ".join(f"[{t}]" for t in tags[:2])
                tag_lbl = tk.Label(
                    row2,
                    text=tag_str,
                    font=FONT_BADGE,
                    fg=COLOR_GOLD,
                    bg=COLOR_CARD,
                )
                tag_lbl.pack(side=tk.RIGHT)

    # =========================================================================
    # TAB 2: DRAFT COACH
    # =========================================================================
    def _build_draft_coach_tab(self) -> None:
        """Construct pick/ban draft board and Monte Carlo simulator."""
        champs_list = sorted([c["name"] for c in self.db.get_all_champions()])
        if not champs_list:
            champs_list = ["Aatrox", "Ahri", "Amumu", "Blitzcrank", "Caitlyn", "Jinx", "LeeSin", "Malphite", "Yasuo", "Zed"]

        # Main horizontal split: Draft Selection (Left) vs Analysis & Prediction (Right)
        draft_split = tk.Frame(self.tab_draft, bg=COLOR_BG)
        draft_split.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        # LEFT: Pick/Ban Selectors
        sel_frame = tk.Frame(draft_split, bg=COLOR_CONTAINER, bd=1, relief=tk.SOLID, width=420)
        sel_frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 4))

        lbl_draft_title = tk.Label(
            sel_frame,
            text="DRAFT ROSTER SELECTION",
            font=FONT_SECTION,
            fg=COLOR_GOLD,
            bg=COLOR_SURFACE,
            pady=6,
        )
        lbl_draft_title.pack(fill=tk.X)

        self.blue_picks_vars: List[tk.StringVar] = []
        self.red_picks_vars: List[tk.StringVar] = []

        default_blue = ["Malphite", "Lee Sin", "Ahri", "Jinx", "Lulu"]
        default_red = ["Darius", "Amumu", "LeBlanc", "Caitlyn", "Blitzcrank"]

        # Blue Picks Subframe
        b_box = tk.LabelFrame(
            sel_frame,
            text="BLUE TEAM (ORDER)",
            font=FONT_BADGE,
            fg=COLOR_BLUE_TEAM,
            bg=COLOR_CONTAINER,
            padx=8,
            pady=6,
        )
        b_box.pack(fill=tk.X, padx=8, pady=4)

        roles = ["TOP", "JGL", "MID", "ADC", "SUP"]
        for i in range(5):
            row = tk.Frame(b_box, bg=COLOR_CONTAINER)
            row.pack(fill=tk.X, pady=2)
            tk.Label(row, text=f"[{roles[i]}]", font=FONT_BADGE, fg=COLOR_TEXT_MUTED, bg=COLOR_CONTAINER, width=6, anchor="w").pack(side=tk.LEFT)
            var = tk.StringVar(value=default_blue[i] if i < len(default_blue) else "")
            cb = ttk.Combobox(row, textvariable=var, values=champs_list, state="readonly", width=18)
            cb.pack(side=tk.LEFT, padx=4)
            cb.bind("<<ComboboxSelected>>", lambda e: self.update_draft_analysis())
            self.blue_picks_vars.append(var)

        # Red Picks Subframe
        r_box = tk.LabelFrame(
            sel_frame,
            text="RED TEAM (CHAOS)",
            font=FONT_BADGE,
            fg=COLOR_RED_TEAM,
            bg=COLOR_CONTAINER,
            padx=8,
            pady=6,
        )
        r_box.pack(fill=tk.X, padx=8, pady=4)

        for i in range(5):
            row = tk.Frame(r_box, bg=COLOR_CONTAINER)
            row.pack(fill=tk.X, pady=2)
            tk.Label(row, text=f"[{roles[i]}]", font=FONT_BADGE, fg=COLOR_TEXT_MUTED, bg=COLOR_CONTAINER, width=6, anchor="w").pack(side=tk.LEFT)
            var = tk.StringVar(value=default_red[i] if i < len(default_red) else "")
            cb = ttk.Combobox(row, textvariable=var, values=champs_list, state="readonly", width=18)
            cb.pack(side=tk.LEFT, padx=4)
            cb.bind("<<ComboboxSelected>>", lambda e: self.update_draft_analysis())
            self.red_picks_vars.append(var)

        # Recommended picks sub-panel
        rec_box = tk.LabelFrame(
            sel_frame,
            text="AI PICK RECOMMENDATIONS",
            font=FONT_BADGE,
            fg=COLOR_TEAL,
            bg=COLOR_CONTAINER,
            padx=8,
            pady=6,
        )
        rec_box.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        rec_ctrl = tk.Frame(rec_box, bg=COLOR_CONTAINER)
        rec_ctrl.pack(fill=tk.X, pady=2)

        tk.Label(rec_ctrl, text="ROLE:", font=FONT_BADGE, fg=COLOR_TEXT, bg=COLOR_CONTAINER).pack(side=tk.LEFT)
        self.var_rec_role = tk.StringVar(value="MID")
        cb_role = ttk.Combobox(rec_ctrl, textvariable=self.var_rec_role, values=["TOP", "JUNGLE", "MID", "ADC", "SUPPORT"], state="readonly", width=10)
        cb_role.pack(side=tk.LEFT, padx=6)
        cb_role.bind("<<ComboboxSelected>>", lambda e: self.refresh_recommendations())

        btn_calc_rec = tk.Button(
            rec_ctrl,
            text="[ANALYZE]",
            font=FONT_BADGE,
            fg=COLOR_GOLD,
            bg=COLOR_SURFACE,
            bd=1,
            command=self.refresh_recommendations,
            cursor="hand2",
        )
        btn_calc_rec.pack(side=tk.RIGHT)

        self.rec_text = tk.Text(
            rec_box,
            bg=COLOR_CARD,
            fg=COLOR_TEXT,
            font=FONT_BODY,
            height=6,
            bd=1,
            relief=tk.SOLID,
            wrap=tk.WORD,
        )
        self.rec_text.pack(fill=tk.BOTH, expand=True, pady=4)

        # RIGHT: Analysis, Radar, Synergy, Monte Carlo
        analytics_frame = tk.Frame(draft_split, bg=COLOR_CONTAINER, bd=1, relief=tk.SOLID)
        analytics_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(4, 0))

        lbl_ana_title = tk.Label(
            analytics_frame,
            text="DRAFT INTELLIGENCE & PREDICTIVE FORECAST",
            font=FONT_SECTION,
            fg=COLOR_GOLD,
            bg=COLOR_SURFACE,
            pady=6,
        )
        lbl_ana_title.pack(fill=tk.X)

        # Monte Carlo Simulation Gauge Panel
        mc_panel = tk.Frame(analytics_frame, bg=COLOR_SURFACE, bd=1, relief=tk.SOLID)
        mc_panel.pack(fill=tk.X, padx=8, pady=8)

        mc_head = tk.Frame(mc_panel, bg=COLOR_SURFACE)
        mc_head.pack(fill=tk.X, padx=8, pady=4)

        self.lbl_mc_header = tk.Label(
            mc_head,
            text="MONTE CARLO WIN RATE PREDICTION (10,000 RUNS)",
            font=FONT_SECTION,
            fg=COLOR_TEXT,
            bg=COLOR_SURFACE,
        )
        self.lbl_mc_header.pack(side=tk.LEFT)

        btn_run_mc = tk.Button(
            mc_head,
            text="[RUN MONTE CARLO]",
            font=FONT_BADGE,
            fg=COLOR_GOLD,
            bg=COLOR_CONTAINER,
            bd=1,
            command=self.run_monte_carlo,
            cursor="hand2",
        )
        btn_run_mc.pack(side=tk.RIGHT)

        # Prediction Visual Gauge Bar (Canvas)
        self.mc_canvas = tk.Canvas(
            mc_panel,
            bg=COLOR_CARD,
            height=34,
            bd=1,
            relief=tk.SOLID,
            highlightthickness=0,
        )
        self.mc_canvas.pack(fill=tk.X, padx=8, pady=(2, 6))

        self.lbl_mc_numbers = tk.Label(
            mc_panel,
            text="BLUE: 50.0%  |  RED: 50.0%  [BASELINE]",
            font=FONT_SECTION,
            fg=COLOR_GOLD,
            bg=COLOR_SURFACE,
        )
        self.lbl_mc_numbers.pack(pady=(0, 6))

        # Comp Radar & Metrics Text
        self.ana_text = tk.Text(
            analytics_frame,
            bg=COLOR_CARD,
            fg=COLOR_TEXT,
            font=FONT_BODY,
            bd=1,
            relief=tk.SOLID,
            wrap=tk.WORD,
        )
        self.ana_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        # Trigger initial analysis
        self.update_draft_analysis()
        self.refresh_recommendations()

    def update_draft_analysis(self) -> None:
        """Recalculate composition damage profile, utility radar, synergies, and counters."""
        blue_champs = [v.get().strip() for v in self.blue_picks_vars if v.get().strip()]
        red_champs = [v.get().strip() for v in self.red_picks_vars if v.get().strip()]

        blue_comp = self.coach.analyze_team_composition(blue_champs)
        red_comp = self.coach.analyze_team_composition(red_champs)

        blue_syn = self.coach.compute_synergy_score(blue_champs)
        red_syn = self.coach.compute_synergy_score(red_champs)
        counter_delta = self.coach.compute_counter_score(blue_champs, red_champs)

        # Format breakdown report
        report = []
        report.append("=" * 64)
        report.append("  TEAM COMPOSITION & DAMAGE PROFILE")
        report.append("=" * 64)
        b_dmg = blue_comp["damage_profile"]
        r_dmg = red_comp["damage_profile"]
        report.append(f"BLUE DAMAGE : AD: {int(b_dmg['ad_ratio']*100)}% | AP: {int(b_dmg['ap_ratio']*100)}% | TRUE: {int(b_dmg['true_ratio']*100)}%")
        report.append(f"RED DAMAGE  : AD: {int(r_dmg['ad_ratio']*100)}% | AP: {int(r_dmg['ap_ratio']*100)}% | TRUE: {int(r_dmg['true_ratio']*100)}%")

        if blue_comp["warnings"]:
            for w in blue_comp["warnings"]:
                report.append(f"  [!] BLUE ALERT: {w}")
        if red_comp["warnings"]:
            for w in red_comp["warnings"]:
                report.append(f"  [!] RED ALERT: {w}")

        report.append("\n" + "=" * 64)
        report.append("  UTILITY RADAR (0 - 100)")
        report.append("=" * 64)
        b_rad = blue_comp["utility_radar"]
        r_rad = red_comp["utility_radar"]
        report.append(f"{'METRIC':<14} | {'BLUE TEAM':<12} | {'RED TEAM':<12}")
        report.append("-" * 46)
        report.append(f"{'CC Rating':<14} | {b_rad['cc_rating']:<12} | {r_rad['cc_rating']:<12}")
        report.append(f"{'Engage':<14} | {b_rad['engage_rating']:<12} | {r_rad['engage_rating']:<12}")
        report.append(f"{'Poke':<14} | {b_rad['poke_rating']:<12} | {r_rad['poke_rating']:<12}")
        report.append(f"{'Waveclear':<14} | {b_rad['waveclear_rating']:<12} | {r_rad['waveclear_rating']:<12}")
        report.append(f"{'Scaling':<14} | {b_rad['scaling_rating']:<12} | {r_rad['scaling_rating']:<12}")

        report.append("\n" + "=" * 64)
        report.append("  SYNERGY & COUNTER SCORING MATRIX")
        report.append("=" * 64)
        report.append(f"BLUE SYNERGY SCORE : +{blue_syn:.3f}")
        report.append(f"RED SYNERGY SCORE  : +{red_syn:.3f}")
        ctr_sign = "+" if counter_delta >= 0 else ""
        report.append(f"NET COUNTER DELTA  : {ctr_sign}{counter_delta:.3f} (Advantage: {'BLUE' if counter_delta >= 0 else 'RED'})")

        self.ana_text.delete("1.0", tk.END)
        self.ana_text.insert(tk.END, "\n".join(report))

        # Run quick Monte Carlo
        self.run_monte_carlo(iterations=2000)

    def run_monte_carlo(self, iterations: int = 10000) -> None:
        """Execute Monte Carlo simulation and update visual gauge."""
        blue_champs = [v.get().strip() for v in self.blue_picks_vars if v.get().strip()]
        red_champs = [v.get().strip() for v in self.red_picks_vars if v.get().strip()]

        result = self.coach.simulate_win_probability(blue_champs, red_champs, iterations=iterations)
        b_wr = result["blue_win_rate"]
        r_wr = result["red_win_rate"]

        b_pct = b_wr * 100.0
        r_pct = r_wr * 100.0

        diff = b_pct - r_pct
        leader = "BLUE" if diff >= 0 else "RED"
        self.lbl_mc_numbers.config(
            text=f"BLUE: {b_pct:.1f}%  |  RED: {r_pct:.1f}%  [{leader} ADVANTAGE: {abs(diff):.1f}%]"
        )

        # Draw gauge bar on canvas
        self.mc_canvas.delete("all")
        width = self.mc_canvas.winfo_width()
        if width <= 1:
            width = 560

        b_width = int(width * b_wr)

        # Blue section
        self.mc_canvas.create_rectangle(0, 0, b_width, 34, fill=COLOR_BLUE_TEAM, outline="")
        # Red section
        self.mc_canvas.create_rectangle(b_width, 0, width, 34, fill=COLOR_RED_TEAM, outline="")
        # Divider line
        self.mc_canvas.create_line(b_width, 0, b_width, 34, fill=COLOR_GOLD, width=2)

        # Text labels on canvas
        self.mc_canvas.create_text(
            12, 17, text=f"BLUE {b_pct:.1f}%", anchor="w", fill=COLOR_BG, font=FONT_BADGE
        )
        self.mc_canvas.create_text(
            width - 12, 17, text=f"{r_pct:.1f}% RED", anchor="e", fill=COLOR_BG, font=FONT_BADGE
        )

    def refresh_recommendations(self) -> None:
        """Query DraftCoach recommend_picks and display suggestions."""
        role = self.var_rec_role.get()
        blue_champs = [v.get().strip() for v in self.blue_picks_vars if v.get().strip()]
        red_champs = [v.get().strip() for v in self.red_picks_vars if v.get().strip()]

        recs = self.coach.recommend_picks(blue_champs, red_champs, role=role, top_n=3)

        lines = []
        lines.append(f"AI RECOMMENDATIONS FOR ROLE: [{role}]")
        lines.append("-" * 44)
        if not recs:
            lines.append("No suitable candidates found in pool.")
        else:
            for idx, r in enumerate(recs, 1):
                score_str = f"+{r['score']:.3f}" if r["score"] >= 0 else f"{r['score']:.3f}"
                lines.append(f"{idx}. {r['champion'].upper():<12} [SCORE: {score_str}] (WR: {int(r['win_rate']*100)}%)")
                if r["synergies"]:
                    lines.append(f"   Synergy : {', '.join(r['synergies'])}")
                if r["counters"]:
                    lines.append(f"   Counters: {', '.join(r['counters'])}")

        self.rec_text.delete("1.0", tk.END)
        self.rec_text.insert(tk.END, "\n".join(lines))

    # =========================================================================
    # TAB 3: SUMMONER PROFILE
    # =========================================================================
    def _build_profile_tab(self) -> None:
        """Construct Porofesor-style profile search and match history cards."""
        # Top Search Bar
        search_bar = tk.Frame(self.tab_profile, bg=COLOR_SURFACE, bd=1, relief=tk.SOLID)
        search_bar.pack(fill=tk.X, padx=8, pady=6)

        tk.Label(
            search_bar,
            text="SUMMONER LOOKUP:",
            font=FONT_SECTION,
            fg=COLOR_GOLD,
            bg=COLOR_SURFACE,
        ).pack(side=tk.LEFT, padx=12, pady=6)

        self.var_search_name = tk.StringVar(value="Hide on bush#KR1")
        entry_search = tk.Entry(
            search_bar,
            textvariable=self.var_search_name,
            font=FONT_SECTION,
            bg=COLOR_CONTAINER,
            fg=COLOR_TEXT,
            insertbackground=COLOR_GOLD,
            bd=1,
            relief=tk.SOLID,
            width=24,
        )
        entry_search.pack(side=tk.LEFT, padx=6)
        entry_search.bind("<Return>", lambda e: self.on_search_summoner())

        btn_search = tk.Button(
            search_bar,
            text="[SEARCH]",
            font=FONT_BADGE,
            fg=COLOR_GOLD,
            bg=COLOR_CONTAINER,
            bd=1,
            command=self.on_search_summoner,
            cursor="hand2",
            padx=10,
        )
        btn_search.pack(side=tk.LEFT, padx=4)

        btn_faker = tk.Button(
            search_bar,
            text="[PRESET: FAKER]",
            font=FONT_BADGE,
            fg=COLOR_TEAL,
            bg=COLOR_CONTAINER,
            bd=1,
            command=lambda: self.load_summoner_profile("kr-faker-001"),
            cursor="hand2",
            padx=8,
        )
        btn_faker.pack(side=tk.RIGHT, padx=12)

        # Profile Card Header (Name, Rank, Badges, Metrics)
        self.profile_card = tk.Frame(
            self.tab_profile, bg=COLOR_CONTAINER, bd=1, relief=tk.SOLID
        )
        self.profile_card.pack(fill=tk.X, padx=8, pady=4)

        # Row 1: Identity & Rank
        p_row1 = tk.Frame(self.profile_card, bg=COLOR_CONTAINER)
        p_row1.pack(fill=tk.X, padx=12, pady=(8, 4))

        self.lbl_prof_name = tk.Label(
            p_row1,
            text="--",
            font=FONT_TITLE,
            fg=COLOR_GOLD,
            bg=COLOR_CONTAINER,
        )
        self.lbl_prof_name.pack(side=tk.LEFT)

        self.lbl_prof_rank = tk.Label(
            p_row1,
            text="TIER: --",
            font=FONT_SECTION,
            fg=COLOR_TEAL,
            bg=COLOR_CONTAINER,
        )
        self.lbl_prof_rank.pack(side=tk.RIGHT)

        # Row 2: Behavioral Badges Container
        self.badges_frame = tk.Frame(self.profile_card, bg=COLOR_CONTAINER)
        self.badges_frame.pack(fill=tk.X, padx=12, pady=4)

        # Row 3: 20-Match Performance Metrics Aggregation
        self.metrics_frame = tk.Frame(
            self.profile_card, bg=COLOR_CARD, bd=1, relief=tk.SOLID
        )
        self.metrics_frame.pack(fill=tk.X, padx=12, pady=(4, 8))

        self.lbl_prof_metrics = tk.Label(
            self.metrics_frame,
            text="ANALYZING HISTORICAL METRICS...",
            font=FONT_BODY,
            fg=COLOR_TEXT,
            bg=COLOR_CARD,
            padx=8,
            pady=6,
        )
        self.lbl_prof_metrics.pack(fill=tk.X)

        # Recent Match History Cards List (Scrollable)
        lbl_history_hdr = tk.Label(
            self.tab_profile,
            text="RECENT MATCH HISTORY (PAST 20 MATCHES)",
            font=FONT_SECTION,
            fg=COLOR_GOLD,
            bg=COLOR_BG,
            anchor="w",
        )
        lbl_history_hdr.pack(fill=tk.X, padx=10, pady=(6, 2))

        # Canvas with scrollbar for match cards
        history_box = tk.Frame(self.tab_profile, bg=COLOR_BG)
        history_box.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 6))

        self.history_canvas = tk.Canvas(
            history_box,
            bg=COLOR_BG,
            bd=0,
            highlightthickness=0,
        )
        scrollbar = ttk.Scrollbar(
            history_box, orient="vertical", command=self.history_canvas.yview
        )
        self.history_cards_frame = tk.Frame(self.history_canvas, bg=COLOR_BG)

        self.history_cards_frame.bind(
            "<Configure>",
            lambda e: self.history_canvas.configure(
                scrollregion=self.history_canvas.bbox("all")
            ),
        )
        self.history_canvas_window = self.history_canvas.create_window(
            (0, 0), window=self.history_cards_frame, anchor="nw"
        )
        self.history_canvas.configure(yscrollcommand=scrollbar.set)

        self.history_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Bind canvas resize to frame width
        self.history_canvas.bind(
            "<Configure>",
            lambda e: self.history_canvas.itemconfig(
                self.history_canvas_window, width=e.width
            ),
        )

    def on_search_summoner(self) -> None:
        """Trigger summoner search from entry."""
        raw_query = self.var_search_name.get().strip()
        if not raw_query:
            return

        name_part = raw_query.split("#")[0].strip()
        summoner = self.db.get_summoner(name=name_part)
        if summoner:
            self.load_summoner_profile(summoner["puuid"])
        else:
            # Fallback to faker if not found
            self.load_summoner_profile("kr-faker-001")

    def load_summoner_profile(self, puuid: str) -> None:
        """Load profile header, tags, and 20 match history records."""
        summoner = self.db.get_summoner(puuid=puuid)
        if not summoner:
            # Try by name if puuid lookup fails
            summoner = self.db.get_summoner(name="Hide on bush")

        if not summoner:
            return

        name = summoner.get("name", "Unknown")
        tag = summoner.get("tag_line", "KR1")
        tier = summoner.get("tier", "CHALLENGER")
        rank = summoner.get("rank", "I")
        lp = summoner.get("lp", 0)
        wins = summoner.get("wins", 0)
        losses = summoner.get("losses", 0)
        total = wins + losses
        wr_pct = round((wins / total) * 100.0, 1) if total > 0 else 0.0

        self.lbl_prof_name.config(text=f"{name.upper()} #{tag} [LVL {summoner.get('level', 30)}]")
        self.lbl_prof_rank.config(
            text=f"{tier} {rank} ({lp} LP) | {wins}W {losses}L ({wr_pct}% WR)"
        )

        # Fetch match history
        matches = self.db.get_summoner_history(puuid, limit=20)
        if not matches:
            matches = self.db.get_summoner_history("kr-faker-001", limit=20)

        # Compute stats & Porofesor tags
        stats = self.profiler.analyze_performance(matches)
        tags = self.profiler.generate_tags(matches)

        # Render Badges
        for w in self.badges_frame.winfo_children():
            w.destroy()

        if not tags:
            lbl_no_tags = tk.Label(
                self.badges_frame,
                text="[NO DIAGNOSTIC TAGS RECORDED]",
                font=FONT_BADGE,
                fg=COLOR_TEXT_MUTED,
                bg=COLOR_CONTAINER,
            )
            lbl_no_tags.pack(side=tk.LEFT)
        else:
            for t in tags:
                badge = tk.Label(
                    self.badges_frame,
                    text=f"[{t}]",
                    font=FONT_BADGE,
                    fg=COLOR_GOLD,
                    bg=COLOR_CARD,
                    padx=8,
                    pady=3,
                    bd=1,
                    relief=tk.SOLID,
                )
                badge.pack(side=tk.LEFT, padx=3)

        # Render Metrics
        self.lbl_prof_metrics.config(
            text=(
                f"20-MATCH AGGREGATION:  "
                f"WIN RATE: {stats['win_rate_pct']}% ({stats['wins']}W - {stats['losses']}L)  |  "
                f"KDA: {stats['kda']} ({stats['avg_kills']} / {stats['avg_deaths']} / {stats['avg_assists']})  |  "
                f"CS/MIN: {stats['avg_cs_per_min']}  |  "
                f"VISION/MIN: {stats['avg_vision_per_min']}"
            )
        )

        # Render Match Cards
        for child in self.history_cards_frame.winfo_children():
            child.destroy()

        for m in matches:
            is_win = 1 if m.get("win") in (1, True, "1", "True") else 0
            card_bg = COLOR_CARD
            border_color = COLOR_WIN if is_win else COLOR_LOSS
            outcome_text = "[VICTORY]" if is_win else "[DEFEAT]"
            outcome_fg = COLOR_WIN if is_win else COLOR_LOSS

            card = tk.Frame(
                self.history_cards_frame,
                bg=card_bg,
                bd=1,
                relief=tk.SOLID,
            )
            card.pack(fill=tk.X, pady=3, padx=2)

            # Left side: Outcome + Champion
            left_f = tk.Frame(card, bg=card_bg)
            left_f.pack(side=tk.LEFT, padx=8, pady=6)

            lbl_outcome = tk.Label(
                left_f,
                text=outcome_text,
                font=FONT_SECTION,
                fg=outcome_fg,
                bg=card_bg,
                width=10,
                anchor="w",
            )
            lbl_outcome.pack(side=tk.LEFT)

            lbl_champ = tk.Label(
                left_f,
                text=m.get("champion", "Unknown"),
                font=FONT_SECTION,
                fg=COLOR_TEXT,
                bg=card_bg,
                width=12,
                anchor="w",
            )
            lbl_champ.pack(side=tk.LEFT, padx=6)

            # Middle: KDA
            mid_f = tk.Frame(card, bg=card_bg)
            mid_f.pack(side=tk.LEFT, padx=12, pady=6)

            kda_str = f"{m.get('kills', 0)} / {m.get('deaths', 0)} / {m.get('assists', 0)}"
            lbl_kda = tk.Label(
                mid_f,
                text=f"KDA: {kda_str:<12}",
                font=FONT_BODY_BOLD,
                fg=COLOR_GOLD,
                bg=card_bg,
            )
            lbl_kda.pack(side=tk.LEFT)

            # Right: CS, Vision, Duration
            dur_sec = int(m.get("duration", 1800))
            dur_min = dur_sec // 60
            dur_rem_sec = dur_sec % 60
            cs_cnt = int(m.get("cs", 0))
            vis_score = int(m.get("vision_score", 0))

            right_f = tk.Frame(card, bg=card_bg)
            right_f.pack(side=tk.RIGHT, padx=12, pady=6)

            lbl_stats = tk.Label(
                right_f,
                text=f"CS: {cs_cnt:<4} | VISION: {vis_score:<3} | TIME: {dur_min:02d}:{dur_rem_sec:02d}",
                font=FONT_BODY,
                fg=COLOR_TEXT_MUTED,
                bg=card_bg,
            )
            lbl_stats.pack(side=tk.RIGHT)

    def run(self) -> None:
        """Start GUI event loop."""
        self.root.mainloop()

    def destroy(self) -> None:
        """Clean up and close window."""
        try:
            self.root.destroy()
        except Exception:
            pass


if __name__ == "__main__":
    app = HextechOracleApp()
    app.run()
