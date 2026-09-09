"""
Porofesor-style Summoner Profiler and Behavioral Tag Engine for Hextech Oracle.
Evaluates 20-match stat aggregations and assigns playstyle diagnostic badges.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SummonerProfiler:
    """
    Analyzes historical and live summoner match data to generate performance
    metrics and Porofesor-style behavioral tags.
    """

    # Supported behavioral tags
    TAG_VISION_PRODIGY = "VISION_PRODIGY"
    TAG_AGGRESSIVE_LANER = "AGGRESSIVE_LANER"
    TAG_FARM_MACHINE = "FARM_MACHINE"
    TAG_TILT_PRONE = "TILT_PRONE"
    TAG_HYPER_CARRY = "HYPER_CARRY"
    TAG_ONE_TRICK_PONY = "ONE_TRICK_PONY"
    TAG_COLD_STREAK = "COLD_STREAK"

    @classmethod
    def analyze_performance(cls, matches: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Computes win rate, avg KDA, avg CS/min, avg Vision/min, and role/champ distributions.
        """
        if not matches:
            return {
                "total_matches": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "win_rate_pct": 0.0,
                "avg_kills": 0.0,
                "avg_deaths": 0.0,
                "avg_assists": 0.0,
                "kda": 0.0,
                "avg_cs": 0.0,
                "avg_cs_per_min": 0.0,
                "avg_vision_score": 0.0,
                "avg_vision_per_min": 0.0,
                "champion_stats": {},
                "role_stats": {},
            }

        total_matches = len(matches)
        wins = 0
        total_kills = 0
        total_deaths = 0
        total_assists = 0
        total_cs = 0
        total_vision = 0
        total_duration_minutes = 0.0

        champ_counts: Counter[str] = Counter()
        champ_wins: Counter[str] = Counter()
        role_counts: Counter[str] = Counter()
        role_wins: Counter[str] = Counter()

        for m in matches:
            is_win = 1 if m.get("win") in (1, True, "1", "True") else 0
            if is_win:
                wins += 1

            kills = int(m.get("kills", 0))
            deaths = int(m.get("deaths", 0))
            assists = int(m.get("assists", 0))
            cs = int(m.get("cs", 0))
            vision = int(m.get("vision_score", 0))
            duration = max(60, int(m.get("duration", 1800)))

            total_kills += kills
            total_deaths += deaths
            total_assists += assists
            total_cs += cs
            total_vision += vision
            total_duration_minutes += duration / 60.0

            champ = m.get("champion", "Unknown")
            champ_counts[champ] += 1
            if is_win:
                champ_wins[champ] += 1

            role = m.get("role")
            if role:
                role_counts[role] += 1
                if is_win:
                    role_wins[role] += 1

        losses = total_matches - wins
        win_rate = round(wins / total_matches, 4) if total_matches > 0 else 0.0
        avg_kills = round(total_kills / total_matches, 2)
        avg_deaths = round(total_deaths / total_matches, 2)
        avg_assists = round(total_assists / total_matches, 2)
        kda = (
            round((total_kills + total_assists) / max(1, total_deaths), 2)
            if total_matches > 0
            else 0.0
        )
        avg_cs = round(total_cs / total_matches, 1)
        avg_cs_per_min = (
            round(total_cs / max(0.1, total_duration_minutes), 2)
            if total_duration_minutes > 0
            else 0.0
        )
        avg_vision = round(total_vision / total_matches, 1)
        avg_vision_per_min = (
            round(total_vision / max(0.1, total_duration_minutes), 2)
            if total_duration_minutes > 0
            else 0.0
        )

        champ_stats = {
            c: {
                "matches": count,
                "wins": champ_wins[c],
                "win_rate": round(champ_wins[c] / count, 3),
            }
            for c, count in champ_counts.items()
        }

        role_stats = {
            r: {
                "matches": count,
                "wins": role_wins[r],
                "win_rate": round(role_wins[r] / count, 3),
            }
            for r, count in role_counts.items()
        }

        return {
            "total_matches": total_matches,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "win_rate_pct": round(win_rate * 100.0, 1),
            "avg_kills": avg_kills,
            "avg_deaths": avg_deaths,
            "avg_assists": avg_assists,
            "kda": kda,
            "avg_cs": avg_cs,
            "avg_cs_per_min": avg_cs_per_min,
            "avg_vision_score": avg_vision,
            "avg_vision_per_min": avg_vision_per_min,
            "champion_stats": champ_stats,
            "role_stats": role_stats,
        }

    @classmethod
    def generate_tags(
        cls,
        matches: List[Dict[str, Any]],
        live_stats: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """
        Evaluates matches and optional live in-game stats against rule triggers
        to assign diagnostic badges.
        """
        tags: List[str] = []

        # Check live stats first for instant tag triggers if available
        if live_stats:
            live_duration_min = max(0.5, float(live_stats.get("game_time", 1800)) / 60.0)
            live_vision = float(live_stats.get("vision_score", 0))
            if (live_vision / live_duration_min) >= 1.4:
                tags.append(cls.TAG_VISION_PRODIGY)

            live_cs = float(live_stats.get("cs", 0))
            if (live_cs / live_duration_min) >= 7.5:
                if cls.TAG_FARM_MACHINE not in tags:
                    tags.append(cls.TAG_FARM_MACHINE)

        if not matches:
            return tags

        stats = cls.analyze_performance(matches)
        total_matches = stats["total_matches"]

        # 1. VISION_PRODIGY: vision_score / (duration / 60) >= 1.4
        if stats["avg_vision_per_min"] >= 1.4 and cls.TAG_VISION_PRODIGY not in tags:
            tags.append(cls.TAG_VISION_PRODIGY)

        # 2. AGGRESSIVE_LANER: avg_kills >= 6 and kda >= 2.5
        if stats["avg_kills"] >= 6.0 and stats["kda"] >= 2.5:
            tags.append(cls.TAG_AGGRESSIVE_LANER)

        # 3. FARM_MACHINE: cs_per_min >= 7.5
        if stats["avg_cs_per_min"] >= 7.5 and cls.TAG_FARM_MACHINE not in tags:
            tags.append(cls.TAG_FARM_MACHINE)

        # 4. TILT_PRONE: Current losing streak >= 3 with recent kda < 1.8
        current_loss_streak = 0
        streak_kills = 0
        streak_deaths = 0
        streak_assists = 0

        for m in matches:
            is_win = 1 if m.get("win") in (1, True, "1", "True") else 0
            if is_win == 0:
                current_loss_streak += 1
                streak_kills += int(m.get("kills", 0))
                streak_deaths += int(m.get("deaths", 0))
                streak_assists += int(m.get("assists", 0))
            else:
                break

        if current_loss_streak >= 3:
            streak_kda = (streak_kills + streak_assists) / max(1, streak_deaths)
            if streak_kda < 1.8:
                tags.append(cls.TAG_TILT_PRONE)

        # 5. HYPER_CARRY: Win rate >= 62% with >= 5 matches on role (or overall)
        has_hyper_carry = False
        if stats["role_stats"]:
            for r_info in stats["role_stats"].values():
                if r_info["matches"] >= 5 and r_info["win_rate"] >= 0.62:
                    has_hyper_carry = True
                    break
        if not has_hyper_carry and total_matches >= 5 and stats["win_rate"] >= 0.62:
            has_hyper_carry = True

        if has_hyper_carry:
            tags.append(cls.TAG_HYPER_CARRY)

        # 6. ONE_TRICK_PONY: >= 60% of total matches played on a single champion
        if total_matches >= 3 and stats["champion_stats"]:
            max_champ_matches = max(c["matches"] for c in stats["champion_stats"].values())
            if (max_champ_matches / total_matches) >= 0.60:
                tags.append(cls.TAG_ONE_TRICK_PONY)

        # 7. COLD_STREAK: >= 4 losses in last 5 matches
        recent_5 = matches[:5]
        if len(recent_5) >= 4:
            recent_losses = sum(
                1 for m in recent_5 if not (m.get("win") in (1, True, "1", "True"))
            )
            if recent_losses >= 4:
                tags.append(cls.TAG_COLD_STREAK)

        return tags
