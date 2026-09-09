# Hextech Oracle - Architecture & Benchmark Specification

## 1. Executive Summary
Hextech Oracle is a high-performance, native Desktop companion application for League of Legends. It synthesizes the real-time player diagnosis and LCU autodetection of **Porofesor** with the algorithmic draft coaching, synergy clustering, and Monte Carlo predictive modeling of **iTero**.

### Architectural Invariants
- **Platform**: Native Python Desktop UI (`customtkinter` or clean `tkinter` with Canvas/themed widgets). No web servers, browsers, or Electron wrappers.
- **Design Language**: Hextech Dark Theme:
  - Base Background: `#010A13`
  - Container / Surface: `#0A1428`
  - Accent Gold: `#C89B3C`
  - Accent Teal: `#0AC8B9`
  - Subdued Border: `#1E282D`
  - Foreground Text: `#F0E6D2` / `#A09B8C`
  - **Zero Emojis**: Use technical labels, uppercase tags, and ASCII/vector indicators only.
- **Autodetection & Offline Testing**: Automatic discovery of the Riot Client / LCU API, accompanied by a deterministic `MockLCUDaemon` for offline CI/CD execution without an active League of Legends process.
- **Storage**: SQLite 3 with Write-Ahead Logging (WAL) and index optimization.

---

## 2. Core Modules Specification

### 2.1 Storage Engine (`src/storage/db.py`)
- SQLite schema:
  - `champions`: `id TEXT PRIMARY KEY, name TEXT, title TEXT, roles TEXT, attack INT, defense INT, magic INT, difficulty INT, win_rate REAL, ban_rate REAL`
  - `synergies`: `champ_a TEXT, champ_b TEXT, synergy_score REAL, combo_type TEXT, PRIMARY KEY(champ_a, champ_b)`
  - `counters`: `champion TEXT, counter_champion TEXT, advantage_delta REAL, PRIMARY KEY(champion, counter_champion)`
  - `summoner_cache`: `puuid TEXT PRIMARY KEY, name TEXT, tag_line TEXT, level INT, tier TEXT, rank TEXT, lp INT, wins INT, losses INT, last_updated REAL`
  - `match_history`: `match_id TEXT, puuid TEXT, champion TEXT, kills INT, deaths INT, assists INT, cs INT, vision_score INT, win INT, duration INT, PRIMARY KEY(match_id, puuid)`
- Methods:
  - `initialize_schema()`: Idempotent table & index creation.
  - `seed_static_data(champions_data, synergies_data, counters_data)`: Populate baseline meta stats.
  - `upsert_summoner(profile_dict)`: Cache summoner details.
  - `record_matches(matches_list)`: Bulk insert historical records.
  - `get_champion_stats(champ_name)`: Returns stats, counters, and synergy partners.
  - `get_summoner_history(puuid)`: Returns past 20 matches.

### 2.2 LCU & Live Client Connector (`src/core/lcu_connector.py`)
- Live Client Data Endpoint: `http://127.0.0.1:2999/liveclientdata/allgamedata`
- Class `LCUConnector`:
  - `is_client_running() -> bool`: Probes process list or port 2999.
  - `get_active_summoner() -> Optional[Dict[str, Any]]`: Returns current account name, level, rank.
  - `get_live_game_data() -> Optional[Dict[str, Any]]`: Polls current 5v5 match state.
- Class `MockLCUDaemon`:
  - Deterministic fixture simulator providing active summoner `"Faker#KR1"` and a live 5v5 game state (Blue Team vs Red Team) with full inventory, kills, and team objectives.

### 2.3 Porofesor-Style Summoner Profiler (`src/analytics/summoner_profiler.py`)
- Class `SummonerProfiler`:
  - `analyze_performance(matches: List[Dict[str, Any]]) -> Dict[str, Any]`: Computes win rate, avg KDA, avg CS/min, avg Vision/min.
  - `generate_tags(matches: List[Dict[str, Any]], live_stats: Optional[Dict[str, Any]] = None) -> List[str]`:
    - `VISION_PRODIGY`: `vision_score / (duration / 60) >= 1.4`
    - `AGGRESSIVE_LANER`: `avg_kills >= 6` and `kda >= 2.5`
    - `FARM_MACHINE`: `cs_per_min >= 7.5`
    - `TILT_PRONE`: Current losing streak $\ge 3$ with recent `kda < 1.8`
    - `HYPER_CARRY`: Win rate $\ge 62\%$ with $\ge 5$ matches on role
    - `ONE_TRICK_PONY`: $\ge 60\%$ of total matches played on a single champion
    - `COLD_STREAK`: $\ge 4$ losses in last 5 matches

### 2.4 iTero-Style AI Draft Coach (`src/draft/draft_coach.py`)
- Class `DraftCoach`:
  - `analyze_team_composition(champions: List[str]) -> Dict[str, Any]`:
    - Damage Profile: `ad_ratio`, `ap_ratio`, `true_ratio` (warns if `max(ad, ap) > 0.82`)
    - Utility Radar: `cc_rating` (0-100), `engage_rating` (0-100), `poke_rating` (0-100), `waveclear_rating` (0-100)
    - Power Spike Curve: `early_game`, `mid_game`, `late_game` index
  - `compute_synergy_score(team_champions: List[str]) -> float`: Sum of pairwise synergy scores from database.
  - `compute_counter_score(blue_team: List[str], red_team: List[str]) -> float`: Lane and matchup delta advantage.
  - `simulate_win_probability(blue_team: List[str], red_team: List[str], iterations: int = 5000) -> Dict[str, float]`:
    - Fast Monte Carlo draft simulation combining base win-rates, synergy boosts, and counter penalties.
  - `recommend_picks(current_team: List[str], enemy_team: List[str], role: str, top_n: int = 3) -> List[Dict[str, Any]]`:
    - Evaluates available champions and returns sorted list with net expected win delta.

### 2.5 Native Desktop GUI (`src/ui/desktop_app.py`)
- Root window: 1100x720, dark Hextech theme, responsive layout.
- Tabs:
  1. `LIVE GAME`: Auto-detected match status, 5v5 team rosters, lane matchups, summoner tags, live gold/kill differential.
  2. `DRAFT COACH`: Interactive pick/ban draft board, team comp balance indicators, synergy alerts, counter advantages, and Monte Carlo win forecast gauge.
  3. `SUMMONER PROFILE`: Search bar, recent match history cards, behavioral tags, champion masteries.
- Status bar displaying LCU connection status: `CONNECTED [LIVE]` or `SIMULATED [OFFLINE MOCK]`.

### 2.6 Test Suite (`tests/test_hextech_oracle.py`)
- Minimum 12 rigorous unit and integration tests covering:
  - Database schema integrity, migrations, and CRUD operations.
  - LCU live connection and mock fallback parsing.
  - Tag assignment algorithm accuracy across edge-case match histories.
  - Draft engine team comp balance, counter calculation, and Monte Carlo simulation stability.
  - Headless UI launch validation.
