"""Hextech Oracle - Native Python Desktop UI with Hextech Dark Theme."""

import logging
import os
import tkinter as tk
from tkinter import ttk
from typing import Any, Dict, List, Optional

from src.analytics.summoner_profiler import SummonerProfiler
from src.core.lcu_connector import LCUConnector, MockLCUDaemon
from src.draft.draft_coach import DraftCoach
from src.storage.db import Database

logger = logging.getLogger(__name__)

# Hextech Dark Theme Color Palette (Strictly Zero Emojis)
COLOR_BG = "#010A13"            # Base Background
COLOR_SURFACE = "#0A1428"       # Container / Surface
COLOR_SURFACE_LIGHT = "#0E1E38" # Card / Raised Surface
COLOR_GOLD = "#C89B3C"          # Accent Gold
COLOR_GOLD_MUTED = "#785A28"    # Subdued Gold
COLOR_TEAL = "#0AC8B9"          # Accent Teal
COLOR_BORDER = "#1E282D"        # Subdued Border
COLOR_TEXT_PRIMARY = "#F0E6D2"  # Foreground Primary Text
COLOR_TEXT_MUTED = "#A09B8C"    # Secondary Muted Text
COLOR_RED = "#E05A47"           # Defeat / Red Team
COLOR_BLUE = "#0AC8B9"          # Victory / Blue Team
COLOR_DARK_BAR = "#050D1A"


class DesktopApp:
    """Hextech Oracle Native Desktop Application."""

    def __init__(
        self,
        root: Optional[tk.Tk] = None,
        headless: bool = False,
        db: Optional[Database] = None,
    ):
        """Initialize Desktop Application.

        Args:
            root: Optional existing tk.Tk instance. If None, creates a new one.
            headless: If True, withdraws window for headless test execution.
            db: Optional Database instance. If None, initializes default.
        """
        self.headless = headless
        if root is None:
            self.root = tk.Tk()
        else:
            self.root = root

        self.root.title("Hextech Oracle (Aegis-LoL) - Draft Coach & Summoner Analytics")
        self.root.geometry("1100x720")
        self.root.minsize(1000, 680)
        self.root.configure(bg=COLOR_BG)

        if self.headless:
            self.root.withdraw()

        # Initialize engines
        self.db = db or Database()
        self.lcu = LCUConnector(use_mock_fallback=True)
        self.mock_daemon = self.lcu.mock_daemon
        self.draft_coach = DraftCoach(self.db)
        self.profiler = SummonerProfiler()

        # State cache
        self.current_live_game: Optional[Dict[str, Any]] = None
        self.active_summoner: Optional[Dict[str, Any]] = None
        self.current_tab: str = "LIVE GAME"
        self.tab_buttons: Dict[str, tk.Button] = {}
        self.tab_frames: Dict[str, tk.Frame] = {}

        # Prepopulate database with mock matches for Faker if empty
        self._ensure_summoner_mock_data()

        # Build UI layout
        self._setup_styles()
        self._build_header()
        self._build_tab_container()
        self._build_live_game_tab()
        self._build_draft_coach_tab()
        self._build_summoner_profile_tab()
        self._build_status_bar()

        # Load initial view
        self.select_tab("LIVE GAME")
        self.refresh_live_game()

    def _ensure_summoner_mock_data(self) -> None:
        """Seed initial summoner profile and matches into SQLite cache."""
        summoner = self.lcu.get_active_summoner()
        if summoner:
            self.db.upsert_summoner(summoner)
            history = self.db.get_summoner_history(summoner.get("puuid", "kr-faker-001"))
            if not history:
                mock_matches = self.mock_daemon.generate_mock_matches(
                    puuid=summoner.get("puuid", "kr-faker-001"), count=20
                )
                self.db.record_matches(mock_matches)

    def _setup_styles(self) -> None:
        """Configure ttk styles to match Hextech dark theme."""
        self.style = ttk.Style()
        try:
            self.style.theme_use("clam")
        except Exception:
            pass

        self.style.configure(
            "TCombobox",
            fieldbackground=COLOR_SURFACE_LIGHT,
            background=COLOR_GOLD,
            foreground=COLOR_TEXT_PRIMARY,
            darkcolor=COLOR_BORDER,
            lightcolor=COLOR_BORDER,
            bordercolor=COLOR_BORDER,
            arrowcolor=COLOR_GOLD,
        )

    def _build_header(self) -> None:
        """Build top Hextech application banner."""
        self.header_frame = tk.Frame(self.root, bg=COLOR_SURFACE, height=54, bd=0)
        self.header_frame.pack(side=tk.TOP, fill=tk.X)
        self.header_frame.pack_propagate(False)

        # Title & Subtitle
        title_box = tk.Frame(self.header_frame, bg=COLOR_SURFACE)
        title_box.pack(side=tk.LEFT, padx=16, pady=8)

        lbl_title = tk.Label(
            title_box,
            text="HEXTECH ORACLE",
            font=("Segoe UI", 14, "bold"),
            fg=COLOR_GOLD,
            bg=COLOR_SURFACE,
        )
        lbl_title.pack(side=tk.LEFT)

        lbl_sep = tk.Label(
            title_box,
            text=" | ",
            font=("Segoe UI", 12),
            fg=COLOR_TEXT_MUTED,
            bg=COLOR_SURFACE,
        )
        lbl_sep.pack(side=tk.LEFT)

        lbl_sub = tk.Label(
            title_box,
            text="AEGIS-LOL COMPANION",
            font=("Segoe UI", 10, "bold"),
            fg=COLOR_TEAL,
            bg=COLOR_SURFACE,
        )
        lbl_sub.pack(side=tk.LEFT)

        # Navigation Bar Buttons
        nav_box = tk.Frame(self.header_frame, bg=COLOR_SURFACE)
        nav_box.pack(side=tk.LEFT, padx=30, pady=8)

        for tab_name in ["LIVE GAME", "DRAFT COACH", "SUMMONER PROFILE"]:
            btn = tk.Button(
                nav_box,
                text=f"[{tab_name}]",
                font=("Segoe UI", 9, "bold"),
                bg=COLOR_SURFACE,
                fg=COLOR_TEXT_MUTED,
                activebackground=COLOR_SURFACE_LIGHT,
                activeforeground=COLOR_GOLD,
                bd=0,
                padx=12,
                pady=4,
                cursor="hand2",
                command=lambda t=tab_name: self.select_tab(t),
            )
            btn.pack(side=tk.LEFT, padx=4)
            self.tab_buttons[tab_name] = btn

        # Connection status chip
        chip_box = tk.Frame(self.header_frame, bg=COLOR_SURFACE)
        chip_box.pack(side=tk.RIGHT, padx=16, pady=12)

        self.lbl_lcu_chip = tk.Label(
            chip_box,
            text=f"LCU: {self.lcu.get_connection_status()}",
            font=("Consolas", 9, "bold"),
            fg=COLOR_TEAL,
            bg=COLOR_DARK_BAR,
            padx=8,
            pady=3,
            relief=tk.FLAT,
        )
        self.lbl_lcu_chip.pack()

        # Subdued bottom line under header
        divider = tk.Frame(self.root, bg=COLOR_BORDER, height=1)
        divider.pack(side=tk.TOP, fill=tk.X)

    def _build_tab_container(self) -> None:
        """Create container for tab frames."""
        self.container = tk.Frame(self.root, bg=COLOR_BG)
        self.container.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=14, pady=10)

    def select_tab(self, tab_name: str) -> None:
        """Switch active tab."""
        self.current_tab = tab_name
        for name, frame in self.tab_frames.items():
            if name == tab_name:
                frame.pack(fill=tk.BOTH, expand=True)
            else:
                frame.pack_forget()

        for name, btn in self.tab_buttons.items():
            if name == tab_name:
                btn.configure(fg=COLOR_GOLD, bg=COLOR_SURFACE_LIGHT)
            else:
                btn.configure(fg=COLOR_TEXT_MUTED, bg=COLOR_SURFACE)

    # --------------------------------------------------------------------------
    # TAB 1: LIVE GAME
    # --------------------------------------------------------------------------
    def _build_live_game_tab(self) -> None:
        """Construct the Live Game analysis dashboard."""
        frame = tk.Frame(self.container, bg=COLOR_BG)
        self.tab_frames["LIVE GAME"] = frame

        # Top Control & Match Info Bar
        top_bar = tk.Frame(frame, bg=COLOR_SURFACE, padx=12, pady=8, highlightbackground=COLOR_BORDER, highlightthickness=1)
        top_bar.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))

        self.lbl_live_match_info = tk.Label(
            top_bar,
            text="MATCH STATUS: INITIALIZING...",
            font=("Segoe UI", 10, "bold"),
            fg=COLOR_TEXT_PRIMARY,
            bg=COLOR_SURFACE,
        )
        self.lbl_live_match_info.pack(side=tk.LEFT)

        btn_refresh = tk.Button(
            top_bar,
            text="REFRESH LIVE DATA",
            font=("Segoe UI", 8, "bold"),
            bg=COLOR_SURFACE_LIGHT,
            fg=COLOR_TEAL,
            activebackground=COLOR_GOLD,
            activeforeground=COLOR_BG,
            bd=1,
            relief=tk.FLAT,
            padx=10,
            pady=3,
            cursor="hand2",
            command=self.refresh_live_game,
        )
        btn_refresh.pack(side=tk.RIGHT, padx=4)

        btn_toggle_sim = tk.Button(
            top_bar,
            text="TOGGLE SIMULATED FEED",
            font=("Segoe UI", 8, "bold"),
            bg=COLOR_SURFACE_LIGHT,
            fg=COLOR_GOLD,
            activebackground=COLOR_GOLD,
            activeforeground=COLOR_BG,
            bd=1,
            relief=tk.FLAT,
            padx=10,
            pady=3,
            cursor="hand2",
            command=self.toggle_simulated_feed,
        )
        btn_toggle_sim.pack(side=tk.RIGHT, padx=4)

        # Match Score Differential Banner
        diff_bar = tk.Frame(frame, bg=COLOR_SURFACE_LIGHT, padx=12, pady=6, highlightbackground=COLOR_BORDER, highlightthickness=1)
        diff_bar.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))

        self.lbl_diff_kills = tk.Label(
            diff_bar,
            text="BLUE 0 - 0 RED",
            font=("Segoe UI", 10, "bold"),
            fg=COLOR_GOLD,
            bg=COLOR_SURFACE_LIGHT,
        )
        self.lbl_diff_kills.pack(side=tk.LEFT)

        self.lbl_diff_gold = tk.Label(
            diff_bar,
            text="GOLD DIFFERENTIAL: +0 BLUE LEAD",
            font=("Segoe UI", 10, "bold"),
            fg=COLOR_TEAL,
            bg=COLOR_SURFACE_LIGHT,
        )
        self.lbl_diff_gold.pack(side=tk.RIGHT)

        # Teams Split View
        teams_box = tk.Frame(frame, bg=COLOR_BG)
        teams_box.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Blue Team Panel
        self.blue_frame = tk.Frame(teams_box, bg=COLOR_SURFACE, highlightbackground=COLOR_BORDER, highlightthickness=1)
        self.blue_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))

        lbl_blue_header = tk.Label(
            self.blue_frame,
            text="BLUE TEAM [ORDER]",
            font=("Segoe UI", 10, "bold"),
            fg=COLOR_TEAL,
            bg=COLOR_SURFACE,
            padx=10,
            pady=6,
        )
        lbl_blue_header.pack(side=tk.TOP, anchor="w")

        self.blue_roster_container = tk.Frame(self.blue_frame, bg=COLOR_SURFACE)
        self.blue_roster_container.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # Red Team Panel
        self.red_frame = tk.Frame(teams_box, bg=COLOR_SURFACE, highlightbackground=COLOR_BORDER, highlightthickness=1)
        self.red_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(6, 0))

        lbl_red_header = tk.Label(
            self.red_frame,
            text="RED TEAM [CHAOS]",
            font=("Segoe UI", 10, "bold"),
            fg=COLOR_RED,
            bg=COLOR_SURFACE,
            padx=10,
            pady=6,
        )
        lbl_red_header.pack(side=tk.TOP, anchor="w")

        self.red_roster_container = tk.Frame(self.red_frame, bg=COLOR_SURFACE)
        self.red_roster_container.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

    def toggle_simulated_feed(self) -> None:
        """Toggle force mock mode in LCUConnector."""
        self.lcu.force_mock = not self.lcu.force_mock
        status = self.lcu.get_connection_status()
        self.lbl_lcu_chip.configure(text=f"LCU: {status}")
        self.lbl_status_left.configure(text=f"LCU STATUS: {status}")
        self.refresh_live_game()

    def refresh_live_game(self) -> None:
        """Query live game data and refresh roster widgets."""
        data = self.lcu.get_live_game_data()
        self.current_live_game = data
        if not data:
            self.lbl_live_match_info.configure(text="MATCH STATUS: NO ACTIVE MATCH DETECTED")
            return

        game_id = data.get("game_id", "N/A")
        mode = data.get("game_mode", "CLASSIC")
        gt = float(data.get("game_time", 0.0))
        mins = int(gt // 60)
        secs = int(gt % 60)

        self.lbl_live_match_info.configure(
            text=f"GAME ID: {game_id} | MODE: {mode} | MATCH TIME: {mins:02d}:{secs:02d} | STATUS: ACTIVE"
        )

        blue_team = data.get("blue_team", [])
        red_team = data.get("red_team", [])

        # Calculate totals
        blue_kills = sum(p.get("kills", 0) for p in blue_team)
        red_kills = sum(p.get("kills", 0) for p in red_team)
        blue_gold = sum(p.get("gold", 0) for p in blue_team)
        red_gold = sum(p.get("gold", 0) for p in red_team)
        gold_diff = blue_gold - red_gold

        self.lbl_diff_kills.configure(
            text=f"BLUE KILLS: {blue_kills}   vs   RED KILLS: {red_kills}"
        )
        if gold_diff >= 0:
            self.lbl_diff_gold.configure(
                text=f"GOLD DIFFERENTIAL: +{gold_diff:,} BLUE LEAD",
                fg=COLOR_TEAL,
            )
        else:
            self.lbl_diff_gold.configure(
                text=f"GOLD DIFFERENTIAL: +{abs(gold_diff):,} RED LEAD",
                fg=COLOR_RED,
            )

        # Re-render blue roster
        for child in self.blue_roster_container.winfo_children():
            child.destroy()
        for p in blue_team:
            self._render_player_card(self.blue_roster_container, p, gt, is_blue=True)

        # Re-render red roster
        for child in self.red_roster_container.winfo_children():
            child.destroy()
        for p in red_team:
            self._render_player_card(self.red_roster_container, p, gt, is_blue=False)

    def _render_player_card(
        self, parent: tk.Frame, player: Dict[str, Any], game_time: float, is_blue: bool
    ) -> None:
        """Render individual summoner card inside team roster."""
        card = tk.Frame(
            parent,
            bg=COLOR_SURFACE_LIGHT,
            padx=8,
            pady=6,
            highlightbackground=COLOR_BORDER,
            highlightthickness=1,
        )
        card.pack(fill=tk.X, pady=3)

        # Top row: Role, Summoner, Champion
        row1 = tk.Frame(card, bg=COLOR_SURFACE_LIGHT)
        row1.pack(fill=tk.X)

        role = player.get("role", "MID")
        lbl_role = tk.Label(
            row1,
            text=f"[{role}]",
            font=("Consolas", 8, "bold"),
            fg=COLOR_GOLD,
            bg=COLOR_SURFACE_LIGHT,
        )
        lbl_role.pack(side=tk.LEFT)

        name = player.get("summoner_name", "Unknown")
        lbl_name = tk.Label(
            row1,
            text=f" {name}",
            font=("Segoe UI", 9, "bold"),
            fg=COLOR_TEXT_PRIMARY,
            bg=COLOR_SURFACE_LIGHT,
        )
        lbl_name.pack(side=tk.LEFT)

        champ = player.get("champion", "Unknown")
        lbl_champ = tk.Label(
            row1,
            text=f"({champ})",
            font=("Segoe UI", 9),
            fg=COLOR_TEAL if is_blue else COLOR_RED,
            bg=COLOR_SURFACE_LIGHT,
        )
        lbl_champ.pack(side=tk.LEFT, padx=4)

        # Mid row: K/D/A, CS, Gold
        k = player.get("kills", 0)
        d = player.get("deaths", 0)
        a = player.get("assists", 0)
        cs = player.get("cs", 0)
        gold = player.get("gold", 0)
        vis = player.get("vision_score", 0)

        cs_min = (cs / (game_time / 60.0)) if game_time > 60 else 0.0

        row2 = tk.Frame(card, bg=COLOR_SURFACE_LIGHT)
        row2.pack(fill=tk.X, pady=(2, 2))

        lbl_kda = tk.Label(
            row2,
            text=f"KDA: {k}/{d}/{a}  |  CS: {cs} ({cs_min:.1f}/m)  |  VIS: {vis}  |  GOLD: {gold:,}",
            font=("Segoe UI", 8),
            fg=COLOR_TEXT_MUTED,
            bg=COLOR_SURFACE_LIGHT,
        )
        lbl_kda.pack(side=tk.LEFT)

        # Tags row (Porofesor-style)
        live_stats = {
            "kills": k,
            "deaths": d,
            "assists": a,
            "cs": cs,
            "vision_score": vis,
            "game_time": game_time,
        }
        tags = SummonerProfiler.generate_tags([], live_stats=live_stats)
        if tags:
            tag_row = tk.Frame(card, bg=COLOR_SURFACE_LIGHT)
            tag_row.pack(fill=tk.X, pady=(2, 0))
            for t in tags:
                lbl_tag = tk.Label(
                    tag_row,
                    text=f"[{t}]",
                    font=("Consolas", 7, "bold"),
                    fg=COLOR_TEAL if "PRODIGY" in t or "MACHINE" in t else COLOR_GOLD,
                    bg=COLOR_DARK_BAR,
                    padx=4,
                    pady=1,
                )
                lbl_tag.pack(side=tk.LEFT, padx=(0, 4))

    # --------------------------------------------------------------------------
    # TAB 2: DRAFT COACH
    # --------------------------------------------------------------------------
    def _build_draft_coach_tab(self) -> None:
        """Construct the iTero-style draft intelligence dashboard."""
        frame = tk.Frame(self.container, bg=COLOR_BG)
        self.tab_frames["DRAFT COACH"] = frame

        # Top: Draft Pick Roster Selection
        roster_bar = tk.Frame(frame, bg=COLOR_SURFACE, padx=12, pady=10, highlightbackground=COLOR_BORDER, highlightthickness=1)
        roster_bar.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))

        # Champion options from DB
        all_champs = [c["name"] for c in self.db.get_all_champions()]
        if not all_champs:
            all_champs = ["Aatrox", "Ahri", "Amumu", "Blitzcrank", "Caitlyn", "Darius", "Jacc", "Jinx", "Kassadin", "LeBlanc", "LeeSin", "Lucian", "Lulu", "Malphite", "Morgana", "Nami", "Orianna", "Sylas", "Thresh", "Vayne", "Yasuo", "Zed"]

        # Blue Slots
        blue_box = tk.Frame(roster_bar, bg=COLOR_SURFACE)
        blue_box.pack(side=tk.LEFT, fill=tk.X, expand=True)

        lbl_b_title = tk.Label(blue_box, text="BLUE TEAM PICKS", font=("Segoe UI", 9, "bold"), fg=COLOR_TEAL, bg=COLOR_SURFACE)
        lbl_b_title.pack(anchor="w", pady=(0, 4))

        self.blue_picks: List[ttk.Combobox] = []
        default_blue = ["Malphite", "LeeSin", "Yasuo", "Jinx", "Lulu"]
        for i in range(5):
            cb = ttk.Combobox(blue_box, values=all_champs, width=12, state="readonly")
            val = default_blue[i] if i < len(default_blue) else all_champs[0]
            cb.set(val)
            cb.pack(side=tk.LEFT, padx=2)
            cb.bind("<<ComboboxSelected>>", lambda e: self.update_draft_analysis())
            self.blue_picks.append(cb)

        # Sync and Run buttons in center
        mid_actions = tk.Frame(roster_bar, bg=COLOR_SURFACE)
        mid_actions.pack(side=tk.LEFT, padx=10)

        btn_sync = tk.Button(
            mid_actions,
            text="IMPORT LIVE GAME",
            font=("Segoe UI", 8, "bold"),
            bg=COLOR_SURFACE_LIGHT,
            fg=COLOR_GOLD,
            bd=1,
            relief=tk.FLAT,
            padx=6,
            pady=3,
            cursor="hand2",
            command=self.import_live_game_to_draft,
        )
        btn_sync.pack(pady=2)

        btn_run_sim = tk.Button(
            mid_actions,
            text="SIMULATE (10K)",
            font=("Segoe UI", 8, "bold"),
            bg=COLOR_SURFACE_LIGHT,
            fg=COLOR_TEAL,
            bd=1,
            relief=tk.FLAT,
            padx=6,
            pady=3,
            cursor="hand2",
            command=self.update_draft_analysis,
        )
        btn_run_sim.pack(pady=2)

        # Red Slots
        red_box = tk.Frame(roster_bar, bg=COLOR_SURFACE)
        red_box.pack(side=tk.RIGHT, fill=tk.X, expand=True)

        lbl_r_title = tk.Label(red_box, text="RED TEAM PICKS", font=("Segoe UI", 9, "bold"), fg=COLOR_RED, bg=COLOR_SURFACE)
        lbl_r_title.pack(anchor="w", pady=(0, 4))

        self.red_picks: List[ttk.Combobox] = []
        default_red = ["Darius", "Amumu", "LeBlanc", "Caitlyn", "Blitzcrank"]
        for i in range(5):
            cb = ttk.Combobox(red_box, values=all_champs, width=12, state="readonly")
            val = default_red[i] if i < len(default_red) else all_champs[0]
            cb.set(val)
            cb.pack(side=tk.LEFT, padx=2)
            cb.bind("<<ComboboxSelected>>", lambda e: self.update_draft_analysis())
            self.red_picks.append(cb)

        # Center area: 2 columns (Left: Comp Radar & Damage, Right: Monte Carlo & AI Recommendations)
        split_frame = tk.Frame(frame, bg=COLOR_BG)
        split_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Left Column: Team Comp Radar & Damage Ratios
        left_col = tk.Frame(split_frame, bg=COLOR_SURFACE, padx=12, pady=10, highlightbackground=COLOR_BORDER, highlightthickness=1)
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))

        lbl_comp_title = tk.Label(left_col, text="TEAM COMPOSITION RADAR & DAMAGE PROFILE", font=("Segoe UI", 10, "bold"), fg=COLOR_GOLD, bg=COLOR_SURFACE)
        lbl_comp_title.pack(anchor="w", pady=(0, 8))

        # Damage Profile Canvas
        self.lbl_dmg_header = tk.Label(left_col, text="DAMAGE DISTRIBUTION (BLUE TEAM)", font=("Segoe UI", 8, "bold"), fg=COLOR_TEXT_PRIMARY, bg=COLOR_SURFACE)
        self.lbl_dmg_header.pack(anchor="w")

        self.canvas_damage = tk.Canvas(left_col, bg=COLOR_DARK_BAR, height=24, highlightthickness=0)
        self.canvas_damage.pack(fill=tk.X, pady=(2, 4))

        self.lbl_dmg_legend = tk.Label(
            left_col,
            text="AD: 0%  |  AP: 0%  |  TRUE: 0%",
            font=("Consolas", 8),
            fg=COLOR_TEXT_MUTED,
            bg=COLOR_SURFACE,
        )
        self.lbl_dmg_legend.pack(anchor="w")

        self.lbl_dmg_warning = tk.Label(
            left_col,
            text="",
            font=("Segoe UI", 8, "bold"),
            fg=COLOR_RED,
            bg=COLOR_SURFACE,
            wraplength=420,
            justify=tk.LEFT,
        )
        self.lbl_dmg_warning.pack(anchor="w", pady=(2, 8))

        # Utility Ratings Bars
        lbl_util_title = tk.Label(left_col, text="UTILITY RADAR METRICS (0 - 100)", font=("Segoe UI", 8, "bold"), fg=COLOR_TEXT_PRIMARY, bg=COLOR_SURFACE)
        lbl_util_title.pack(anchor="w", pady=(4, 2))

        self.util_labels: Dict[str, tk.Label] = {}
        self.util_canvases: Dict[str, tk.Canvas] = {}
        for attr in ["CC", "ENGAGE", "POKE", "WAVECLEAR", "SCALING"]:
            row = tk.Frame(left_col, bg=COLOR_SURFACE)
            row.pack(fill=tk.X, pady=2)
            lbl = tk.Label(row, text=f"{attr:<10}", width=10, anchor="w", font=("Consolas", 8, "bold"), fg=COLOR_TEXT_MUTED, bg=COLOR_SURFACE)
            lbl.pack(side=tk.LEFT)
            canv = tk.Canvas(row, bg=COLOR_DARK_BAR, height=14, width=240, highlightthickness=0)
            canv.pack(side=tk.LEFT, padx=6)
            val_lbl = tk.Label(row, text="50", width=4, font=("Consolas", 8), fg=COLOR_TEXT_PRIMARY, bg=COLOR_SURFACE)
            val_lbl.pack(side=tk.LEFT)
            self.util_labels[attr] = val_lbl
            self.util_canvases[attr] = canv

        # Right Column: Monte Carlo Win Gauge & Recommendations
        right_col = tk.Frame(split_frame, bg=COLOR_SURFACE, padx=12, pady=10, highlightbackground=COLOR_BORDER, highlightthickness=1)
        right_col.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(6, 0))

        lbl_sim_title = tk.Label(right_col, text="MONTE CARLO WIN FORECAST (10,000 RUNS)", font=("Segoe UI", 10, "bold"), fg=COLOR_GOLD, bg=COLOR_SURFACE)
        lbl_sim_title.pack(anchor="w", pady=(0, 6))

        # Win Gauge Canvas
        self.canvas_gauge = tk.Canvas(right_col, bg=COLOR_DARK_BAR, height=44, highlightthickness=0)
        self.canvas_gauge.pack(fill=tk.X, pady=(0, 6))

        self.lbl_sim_meta = tk.Label(
            right_col,
            text="BLUE WIN RATE: 50.0%  |  RED WIN RATE: 50.0%",
            font=("Segoe UI", 9, "bold"),
            fg=COLOR_TEXT_PRIMARY,
            bg=COLOR_SURFACE,
        )
        self.lbl_sim_meta.pack(anchor="w")

        self.lbl_synergy_counter = tk.Label(
            right_col,
            text="SYNERGIES: BLUE +0.00 / RED +0.00  |  MATCHUP DELTA: +0.00",
            font=("Consolas", 8),
            fg=COLOR_TEAL,
            bg=COLOR_SURFACE,
        )
        self.lbl_synergy_counter.pack(anchor="w", pady=(2, 8))

        # AI Pick Recommendation Subpanel
        lbl_rec_title = tk.Label(right_col, text="AI PICK ASSISTANT - TOP RECOMMENDATIONS", font=("Segoe UI", 9, "bold"), fg=COLOR_GOLD, bg=COLOR_SURFACE)
        lbl_rec_title.pack(anchor="w", pady=(4, 4))

        # Role Filter
        role_filter_box = tk.Frame(right_col, bg=COLOR_SURFACE)
        role_filter_box.pack(anchor="w", pady=(0, 6))

        tk.Label(role_filter_box, text="ROLE FILTER: ", font=("Segoe UI", 8), fg=COLOR_TEXT_MUTED, bg=COLOR_SURFACE).pack(side=tk.LEFT)
        self.cb_rec_role = ttk.Combobox(role_filter_box, values=["ALL", "TOP", "JUNGLE", "MID", "ADC", "SUPPORT"], width=10, state="readonly")
        self.cb_rec_role.set("ALL")
        self.cb_rec_role.pack(side=tk.LEFT)
        self.cb_rec_role.bind("<<ComboboxSelected>>", lambda e: self.update_draft_analysis())

        self.rec_cards_container = tk.Frame(right_col, bg=COLOR_SURFACE)
        self.rec_cards_container.pack(fill=tk.BOTH, expand=True)

        self.update_draft_analysis()

    def import_live_game_to_draft(self) -> None:
        """Import current live match picks into draft selectors."""
        data = self.lcu.get_live_game_data()
        if not data:
            return
        blue_team = data.get("blue_team", [])
        red_team = data.get("red_team", [])

        for i, p in enumerate(blue_team[:5]):
            champ = p.get("champion")
            if champ and champ in self.blue_picks[i]["values"]:
                self.blue_picks[i].set(champ)

        for i, p in enumerate(red_team[:5]):
            champ = p.get("champion")
            if champ and champ in self.red_picks[i]["values"]:
                self.red_picks[i].set(champ)

        self.update_draft_analysis()

    def update_draft_analysis(self) -> None:
        """Execute composition analysis, Monte Carlo simulation, and pick suggestions."""
        blue_team = [cb.get() for cb in self.blue_picks if cb.get()]
        red_team = [cb.get() for cb in self.red_picks if cb.get()]

        comp = self.draft_coach.analyze_team_composition(blue_team)
        dmg = comp["damage_profile"]
        radar = comp["utility_radar"]

        # Render Damage Distribution Bar
        self.canvas_damage.delete("all")
        w = max(10, self.canvas_damage.winfo_width())
        if w <= 1:
            w = 400
        h = 24

        ad_w = w * dmg["ad_ratio"]
        ap_w = w * dmg["ap_ratio"]
        tr_w = w * dmg["true_ratio"]

        self.canvas_damage.create_rectangle(0, 0, ad_w, h, fill=COLOR_GOLD, outline="")
        self.canvas_damage.create_rectangle(ad_w, 0, ad_w + ap_w, h, fill=COLOR_TEAL, outline="")
        self.canvas_damage.create_rectangle(ad_w + ap_w, 0, w, h, fill=COLOR_TEXT_PRIMARY, outline="")

        self.lbl_dmg_legend.configure(
            text=f"AD: {dmg['ad_ratio']*100:.1f}%  |  AP: {dmg['ap_ratio']*100:.1f}%  |  TRUE: {dmg['true_ratio']*100:.1f}%"
        )
        if dmg["warning"]:
            self.lbl_dmg_warning.configure(text=dmg["warning"], fg=COLOR_RED)
        else:
            self.lbl_dmg_warning.configure(text="DAMAGE PROFILE: BALANCED", fg=COLOR_TEAL)

        # Render Utility Radar Bars
        mapping = {
            "CC": radar["cc_rating"],
            "ENGAGE": radar["engage_rating"],
            "POKE": radar["poke_rating"],
            "WAVECLEAR": radar["waveclear_rating"],
            "SCALING": radar["scaling_rating"],
        }
        for attr, val in mapping.items():
            self.util_labels[attr].configure(text=f"{val:.0f}")
            canv = self.util_canvases[attr]
            canv.delete("all")
            cw = max(10, canv.winfo_width())
            if cw <= 1:
                cw = 240
            bar_len = (val / 100.0) * cw
            bar_color = COLOR_TEAL if val >= 70 else (COLOR_GOLD if val >= 45 else COLOR_RED)
            canv.create_rectangle(0, 0, bar_len, 14, fill=bar_color, outline="")

        # Monte Carlo Simulation
        sim = self.draft_coach.simulate_win_probability(blue_team, red_team, iterations=10000)
        b_wr = sim["blue_win_rate"]
        r_wr = sim["red_win_rate"]

        # Render Gauge
        self.canvas_gauge.delete("all")
        gw = max(10, self.canvas_gauge.winfo_width())
        if gw <= 1:
            gw = 400
        gh = 44
        split_x = gw * b_wr

        self.canvas_gauge.create_rectangle(0, 0, split_x, gh, fill=COLOR_TEAL, outline="")
        self.canvas_gauge.create_rectangle(split_x, 0, gw, gh, fill=COLOR_RED, outline="")
        self.canvas_gauge.create_line(split_x, 0, split_x, gh, fill=COLOR_TEXT_PRIMARY, width=2)

        self.lbl_sim_meta.configure(
            text=f"BLUE WIN PROBABILITY: {b_wr*100:.1f}%   |   RED WIN PROBABILITY: {r_wr*100:.1f}%"
        )
        self.lbl_synergy_counter.configure(
            text=f"SYNERGY: BLUE +{sim['blue_synergy']:.2f} / RED +{sim['red_synergy']:.2f}  |  COUNTER DELTA: {sim['counter_delta']:+.2f}"
        )

        # AI Recommendations
        role_filter = self.cb_rec_role.get()
        role_arg = None if role_filter == "ALL" else role_filter
        recs = self.draft_coach.recommend_picks(blue_team, red_team, role=role_arg, top_n=3)

        for child in self.rec_cards_container.winfo_children():
            child.destroy()

        for rec in recs:
            rcard = tk.Frame(self.rec_cards_container, bg=COLOR_SURFACE_LIGHT, padx=8, pady=4, highlightbackground=COLOR_BORDER, highlightthickness=1)
            rcard.pack(fill=tk.X, pady=2)

            r_row1 = tk.Frame(rcard, bg=COLOR_SURFACE_LIGHT)
            r_row1.pack(fill=tk.X)

            lbl_cname = tk.Label(
                r_row1,
                text=f"{rec['champion']} ({rec['roles']})",
                font=("Segoe UI", 9, "bold"),
                fg=COLOR_GOLD,
                bg=COLOR_SURFACE_LIGHT,
            )
            lbl_cname.pack(side=tk.LEFT)

            delta_sign = "+" if rec["net_win_delta"] >= 0 else ""
            lbl_delta = tk.Label(
                r_row1,
                text=f"WIN DELTA: {delta_sign}{rec['net_win_delta']*100:.2f}%",
                font=("Consolas", 8, "bold"),
                fg=COLOR_TEAL if rec["net_win_delta"] >= 0 else COLOR_RED,
                bg=COLOR_SURFACE_LIGHT,
            )
            lbl_delta.pack(side=tk.RIGHT)

            lbl_reason = tk.Label(
                rcard,
                text=rec["reasoning"],
                font=("Segoe UI", 8),
                fg=COLOR_TEXT_MUTED,
                bg=COLOR_SURFACE_LIGHT,
                anchor="w",
            )
            lbl_reason.pack(fill=tk.X)

    # --------------------------------------------------------------------------
    # TAB 3: SUMMONER PROFILE
    # --------------------------------------------------------------------------
    def _build_summoner_profile_tab(self) -> None:
        """Construct the Porofesor-style Summoner Profiler dashboard."""
        frame = tk.Frame(self.container, bg=COLOR_BG)
        self.tab_frames["SUMMONER PROFILE"] = frame

        # Search Bar Header
        search_bar = tk.Frame(frame, bg=COLOR_SURFACE, padx=12, pady=8, highlightbackground=COLOR_BORDER, highlightthickness=1)
        search_bar.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))

        tk.Label(
            search_bar,
            text="SUMMONER LOOKUP:",
            font=("Segoe UI", 9, "bold"),
            fg=COLOR_GOLD,
            bg=COLOR_SURFACE,
        ).pack(side=tk.LEFT, padx=(0, 8))

        self.entry_summoner = tk.Entry(
            search_bar,
            font=("Segoe UI", 9),
            bg=COLOR_SURFACE_LIGHT,
            fg=COLOR_TEXT_PRIMARY,
            insertbackground=COLOR_GOLD,
            bd=1,
            relief=tk.FLAT,
            width=26,
        )
        self.entry_summoner.pack(side=tk.LEFT, padx=(0, 8))
        self.entry_summoner.insert(0, "Hide on bush#KR1")

        btn_search = tk.Button(
            search_bar,
            text="SEARCH PROFILE",
            font=("Segoe UI", 8, "bold"),
            bg=COLOR_SURFACE_LIGHT,
            fg=COLOR_TEAL,
            bd=1,
            relief=tk.FLAT,
            padx=10,
            pady=3,
            cursor="hand2",
            command=self.search_summoner_profile,
        )
        btn_search.pack(side=tk.LEFT)

        btn_faker = tk.Button(
            search_bar,
            text="LOAD FAKER #KR1",
            font=("Segoe UI", 8, "bold"),
            bg=COLOR_SURFACE_LIGHT,
            fg=COLOR_GOLD,
            bd=1,
            relief=tk.FLAT,
            padx=10,
            pady=3,
            cursor="hand2",
            command=lambda: self._set_and_search("Hide on bush#KR1"),
        )
        btn_faker.pack(side=tk.RIGHT)

        # Profile Overview Card
        self.profile_overview = tk.Frame(frame, bg=COLOR_SURFACE, padx=14, pady=10, highlightbackground=COLOR_BORDER, highlightthickness=1)
        self.profile_overview.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))

        self.lbl_profile_name = tk.Label(
            self.profile_overview,
            text="Hide on bush #KR1",
            font=("Segoe UI", 13, "bold"),
            fg=COLOR_TEXT_PRIMARY,
            bg=COLOR_SURFACE,
        )
        self.lbl_profile_name.pack(anchor="w")

        self.lbl_profile_tier = tk.Label(
            self.profile_overview,
            text="CHALLENGER I - 984 LP  |  LEVEL 642  |  WIN RATE: 60.8% (240W 155L)",
            font=("Segoe UI", 9, "bold"),
            fg=COLOR_GOLD,
            bg=COLOR_SURFACE,
        )
        self.lbl_profile_tier.pack(anchor="w", pady=(2, 6))

        # Porofesor Behavioral Badges Frame
        self.badges_frame = tk.Frame(self.profile_overview, bg=COLOR_SURFACE)
        self.badges_frame.pack(anchor="w", pady=(2, 2))

        # Match History List Header
        lbl_hist_title = tk.Label(
            frame,
            text="RECENT MATCH HISTORY (PAST 20 MATCHES)",
            font=("Segoe UI", 10, "bold"),
            fg=COLOR_GOLD,
            bg=COLOR_BG,
        )
        lbl_hist_title.pack(anchor="w", pady=(4, 4))

        # Scrollable Matches Canvas
        hist_container = tk.Frame(frame, bg=COLOR_BG)
        hist_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.canvas_history = tk.Canvas(hist_container, bg=COLOR_BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(hist_container, orient=tk.VERTICAL, command=self.canvas_history.yview)
        self.matches_scrollable = tk.Frame(self.canvas_history, bg=COLOR_BG)

        self.matches_scrollable.bind(
            "<Configure>",
            lambda e: self.canvas_history.configure(scrollregion=self.canvas_history.bbox("all")),
        )
        self.canvas_history.create_window((0, 0), window=self.matches_scrollable, anchor="nw")
        self.canvas_history.configure(yscrollcommand=scrollbar.set)

        self.canvas_history.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.search_summoner_profile()

    def _set_and_search(self, query: str) -> None:
        """Fill search entry and execute profile search."""
        self.entry_summoner.delete(0, tk.END)
        self.entry_summoner.insert(0, query)
        self.search_summoner_profile()

    def search_summoner_profile(self) -> None:
        """Look up summoner stats, assign behavioral tags, and populate match cards."""
        query = self.entry_summoner.get().strip()
        name_part = query
        tag_part = None
        if "#" in query:
            name_part, tag_part = query.split("#", 1)

        summoner = self.db.get_summoner_by_name(name_part, tag_part)
        if not summoner:
            # Fallback to active summoner
            summoner = self.lcu.get_active_summoner()

        if not summoner:
            return

        puuid = summoner.get("puuid", "kr-faker-001")
        name = summoner.get("name", "Hide on bush")
        tag = summoner.get("tag_line", "KR1")
        tier = summoner.get("tier", "CHALLENGER")
        rank = summoner.get("rank", "I")
        lp = summoner.get("lp", 984)
        lvl = summoner.get("level", 642)
        wins = summoner.get("wins", 240)
        losses = summoner.get("losses", 155)
        tot = max(1, wins + losses)
        wr = (wins / tot) * 100.0

        self.lbl_profile_name.configure(text=f"{name} #{tag}")
        self.lbl_profile_tier.configure(
            text=f"{tier} {rank} - {lp} LP  |  LEVEL {lvl}  |  WIN RATE: {wr:.1f}% ({wins}W {losses}L)"
        )

        matches = self.db.get_summoner_history(puuid, limit=20)
        if not matches:
            matches = self.mock_daemon.generate_mock_matches(puuid=puuid, count=20)
            self.db.record_matches(matches)

        # Generate Behavioral Tags
        tags = SummonerProfiler.generate_tags(matches)
        for child in self.badges_frame.winfo_children():
            child.destroy()

        for t in tags:
            badge = tk.Label(
                self.badges_frame,
                text=f"[{t}]",
                font=("Consolas", 8, "bold"),
                fg=COLOR_TEAL if "PRODIGY" in t or "MACHINE" in t else COLOR_GOLD,
                bg=COLOR_DARK_BAR,
                padx=6,
                pady=2,
            )
            badge.pack(side=tk.LEFT, padx=(0, 6))

        # Render Match History Cards
        for child in self.matches_scrollable.winfo_children():
            child.destroy()

        for m in matches:
            mcard = tk.Frame(
                self.matches_scrollable,
                bg=COLOR_SURFACE,
                padx=10,
                pady=6,
                highlightbackground=COLOR_BORDER,
                highlightthickness=1,
            )
            mcard.pack(fill=tk.X, expand=True, pady=3, padx=2)

            is_win = bool(m.get("win"))
            outcome_text = "[VICTORY]" if is_win else "[DEFEAT]"
            outcome_fg = COLOR_TEAL if is_win else COLOR_RED

            r_top = tk.Frame(mcard, bg=COLOR_SURFACE)
            r_top.pack(fill=tk.X)

            lbl_outcome = tk.Label(
                r_top,
                text=outcome_text,
                font=("Segoe UI", 9, "bold"),
                fg=outcome_fg,
                bg=COLOR_SURFACE,
            )
            lbl_outcome.pack(side=tk.LEFT)

            dur_sec = m.get("duration", 1800)
            dur_str = f"{dur_sec // 60}:{dur_sec % 60:02d}"

            lbl_detail = tk.Label(
                r_top,
                text=f"  {m.get('champion')}  |  {m.get('role', 'MID')}  |  DURATION: {dur_str}",
                font=("Segoe UI", 9),
                fg=COLOR_TEXT_PRIMARY,
                bg=COLOR_SURFACE,
            )
            lbl_detail.pack(side=tk.LEFT)

            # Metrics
            k = m.get("kills", 0)
            d = m.get("deaths", 0)
            a = m.get("assists", 0)
            cs = m.get("cs", 0)
            vis = m.get("vision_score", 0)
            cs_pm = (cs / (dur_sec / 60.0)) if dur_sec > 60 else 0.0
            vis_pm = (vis / (dur_sec / 60.0)) if dur_sec > 60 else 0.0

            lbl_stats = tk.Label(
                r_top,
                text=f"KDA: {k}/{d}/{a}  |  CS: {cs} ({cs_pm:.1f}/m)  |  VIS: {vis} ({vis_pm:.1f}/m)",
                font=("Consolas", 8),
                fg=COLOR_TEXT_MUTED,
                bg=COLOR_SURFACE,
            )
            lbl_stats.pack(side=tk.RIGHT)

    # --------------------------------------------------------------------------
    # BOTTOM STATUS BAR
    # --------------------------------------------------------------------------
    def _build_status_bar(self) -> None:
        """Construct bottom status and engine indicators."""
        bar = tk.Frame(self.root, bg=COLOR_SURFACE, height=26)
        bar.pack(side=tk.BOTTOM, fill=tk.X)
        bar.pack_propagate(False)

        conn_status = self.lcu.get_connection_status()
        self.lbl_status_left = tk.Label(
            bar,
            text=f"LCU STATUS: {conn_status}",
            font=("Segoe UI", 8),
            fg=COLOR_TEAL,
            bg=COLOR_SURFACE,
            padx=12,
        )
        self.lbl_status_left.pack(side=tk.LEFT)

        champ_count = len(self.db.get_all_champions())
        lbl_status_mid = tk.Label(
            bar,
            text=f"STORAGE: SQLITE (WAL MODE) - {champ_count} CHAMPIONS SEEDED",
            font=("Segoe UI", 8),
            fg=COLOR_TEXT_MUTED,
            bg=COLOR_SURFACE,
        )
        lbl_status_mid.pack(side=tk.LEFT, padx=20)

        lbl_status_right = tk.Label(
            bar,
            text="HEXTECH ORACLE (AEGIS-LOL) | READY",
            font=("Segoe UI", 8, "bold"),
            fg=COLOR_GOLD,
            bg=COLOR_SURFACE,
            padx=12,
        )
        lbl_status_right.pack(side=tk.RIGHT)

    def run(self) -> None:
        """Start the Tkinter event loop."""
        self.root.mainloop()
