"""Hextech Oracle - Porofesor-Style Summoner Profiler & Tag Engine."""

from collections import Counter
from typing import Any, Dict, List, Optional


class SummonerProfiler:
    """Computes statistical aggregations and assigns behavioral tags."""

    @staticmethod
    def analyze_performance(matches: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate statistical performance across a set of matches."""
        if not matches:
            return {
                "total_matches": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "avg_kills": 0.0,
                "avg_deaths": 0.0,
                "avg_assists": 0.0,
                "avg_kda": 0.0,
                "avg_cs": 0.0,
                "avg_cs_per_min": 0.0,
                "avg_vision_score": 0.0,
                "avg_vision_per_min": 0.0,
                "champion_distribution": {},
                "role_distribution": {},
            }

        total_matches = len(matches)
        wins = sum(1 for m in matches if m.get("win"))
        losses = total_matches - wins
        win_rate = round(wins / total_matches, 3)

        total_kills = sum(m.get("kills", 0) for m in matches)
        total_deaths = sum(m.get("deaths", 0) for m in matches)
        total_assists = sum(m.get("assists", 0) for m in matches)
        total_cs = sum(m.get("cs", 0) for m in matches)
        total_vision = sum(m.get("vision_score", 0) for m in matches)
        total_duration = sum(m.get("duration", 1800) for m in matches)  # seconds

        avg_kills = round(total_kills / total_matches, 2)
        avg_deaths = round(total_deaths / total_matches, 2)
        avg_assists = round(total_assists / total_matches, 2)
        avg_kda = round((total_kills + total_assists) / max(1, total_deaths), 2)
        avg_cs = round(total_cs / total_matches, 1)
        avg_vision_score = round(total_vision / total_matches, 1)

        total_minutes = max(1.0, total_duration / 60.0)
        avg_cs_per_min = round(total_cs / total_minutes, 2)
        avg_vision_per_min = round(total_vision / total_minutes, 2)

        champ_counts = dict(Counter(m.get("champion", "Unknown") for m in matches))
        role_counts = dict(Counter(m.get("role", "MID") for m in matches if m.get("role")))

        return {
            "total_matches": total_matches,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "avg_kills": avg_kills,
            "avg_deaths": avg_deaths,
            "avg_assists": avg_assists,
            "avg_kda": avg_kda,
            "avg_cs": avg_cs,
            "avg_cs_per_min": avg_cs_per_min,
            "avg_vision_score": avg_vision_score,
            "avg_vision_per_min": avg_vision_per_min,
            "champion_distribution": champ_counts,
            "role_distribution": role_counts,
        }

    @classmethod
    def generate_tags(
        cls,
        matches: List[Dict[str, Any]],
        live_stats: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """Generate Porofesor-style behavioral tags from matches and/or live game statistics.

        Tags:
            - VISION_PRODIGY: vision_score / (duration / 60) >= 1.4
            - AGGRESSIVE_LANER: avg_kills >= 6 and kda >= 2.5
            - FARM_MACHINE: cs_per_min >= 7.5
            - TILT_PRONE: Current losing streak >= 3 with recent kda < 1.8
            - HYPER_CARRY: Win rate >= 62% with >= 5 matches on role
            - ONE_TRICK_PONY: >= 60% of total matches played on a single champion
            - COLD_STREAK: >= 4 losses in last 5 matches
        """
        tags: List[str] = []

        # Evaluate performance aggregations if matches are present
        perf = cls.analyze_performance(matches) if matches else None

        # 1. VISION_PRODIGY: vision_score / (duration / 60) >= 1.4
        vision_rate = 0.0
        if live_stats and live_stats.get("game_time", 0) > 60:
            gt_min = live_stats["game_time"] / 60.0
            vision_rate = live_stats.get("vision_score", 0) / gt_min
        elif perf and perf["avg_vision_per_min"] > 0:
            vision_rate = perf["avg_vision_per_min"]

        if vision_rate >= 1.4:
            tags.append("VISION_PRODIGY")

        # 2. FARM_MACHINE: cs_per_min >= 7.5
        cs_rate = 0.0
        if live_stats and live_stats.get("game_time", 0) > 60:
            gt_min = live_stats["game_time"] / 60.0
            cs_rate = live_stats.get("cs", 0) / gt_min
        elif perf and perf["avg_cs_per_min"] > 0:
            cs_rate = perf["avg_cs_per_min"]

        if cs_rate >= 7.5:
            tags.append("FARM_MACHINE")

        # 3. AGGRESSIVE_LANER: avg_kills >= 6 and kda >= 2.5
        agg_matched = False
        if perf and perf["total_matches"] > 0:
            if perf["avg_kills"] >= 6.0 and perf["avg_kda"] >= 2.5:
                agg_matched = True
        elif live_stats:
            lk = live_stats.get("kills", 0)
            ld = live_stats.get("deaths", 0)
            la = live_stats.get("assists", 0)
            lkda = (lk + la) / max(1, ld)
            if lk >= 6 and lkda >= 2.5:
                agg_matched = True

        if agg_matched:
            tags.append("AGGRESSIVE_LANER")

        # Match history based tags
        if matches:
            # 4. COLD_STREAK: >= 4 losses in last 5 matches
            last_5 = matches[:5]
            if len(last_5) >= 4:
                recent_losses = sum(1 for m in last_5 if not m.get("win"))
                if recent_losses >= 4:
                    tags.append("COLD_STREAK")

            # 5. TILT_PRONE: Current losing streak >= 3 with recent kda < 1.8
            losing_streak = 0
            streak_k = 0
            streak_d = 0
            streak_a = 0
            for m in matches:
                if not m.get("win"):
                    losing_streak += 1
                    streak_k += m.get("kills", 0)
                    streak_d += m.get("deaths", 0)
                    streak_a += m.get("assists", 0)
                else:
                    break

            if losing_streak >= 3:
                streak_kda = (streak_k + streak_a) / max(1, streak_d)
                if streak_kda < 1.8:
                    tags.append("TILT_PRONE")

            # 6. HYPER_CARRY: Win rate >= 62% with >= 5 matches on role
            total_m = len(matches)
            if total_m >= 5:
                # Check overall or by role
                role_counts = Counter(m.get("role", "MID") for m in matches if m.get("role"))
                role_qualified = False
                for role, count in role_counts.items():
                    if count >= 5:
                        role_wins = sum(1 for m in matches if m.get("role") == role and m.get("win"))
                        if (role_wins / count) >= 0.62:
                            role_qualified = True
                            break
                if role_qualified or ((perf["win_rate"] if perf else 0) >= 0.62):
                    tags.append("HYPER_CARRY")

            # 7. ONE_TRICK_PONY: >= 60% of total matches played on a single champion
            if total_m >= 3:
                champ_counts = Counter(m.get("champion") for m in matches)
                _, top_count = champ_counts.most_common(1)[0]
                if (top_count / total_m) >= 0.60:
                    tags.append("ONE_TRICK_PONY")

        return tags
