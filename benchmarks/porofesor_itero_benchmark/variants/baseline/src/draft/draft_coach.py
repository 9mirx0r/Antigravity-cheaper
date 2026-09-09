"""Hextech Oracle - iTero-Style Draft Coach & Monte Carlo Engine."""

import logging
import random
from typing import Any, Dict, List, Optional

from src.storage.db import Database

logger = logging.getLogger(__name__)


class DraftCoach:
    """Draft intelligence engine providing team composition analysis and Monte Carlo simulations."""

    def __init__(self, db: Optional[Database] = None):
        """Initialize DraftCoach with a Database instance."""
        if db is None:
            self.db = Database()
        else:
            self.db = db

    def analyze_team_composition(self, champions: List[str]) -> Dict[str, Any]:
        """Analyze team composition damage profiles, utility radar, and power spikes.

        Args:
            champions: List of champion names or IDs in the team.

        Returns:
            Dictionary containing damage_profile, utility_radar, and power_spike.
        """
        champ_objs = []
        for c in champions:
            champ = self.db.get_champion(c)
            if champ:
                champ_objs.append(champ)

        if not champ_objs:
            return {
                "damage_profile": {
                    "ad_ratio": 0.5,
                    "ap_ratio": 0.5,
                    "true_ratio": 0.0,
                    "warning": None,
                },
                "utility_radar": {
                    "cc_rating": 50.0,
                    "engage_rating": 50.0,
                    "poke_rating": 50.0,
                    "waveclear_rating": 50.0,
                    "scaling_rating": 50.0,
                },
                "power_spike": {
                    "early_game": 50.0,
                    "mid_game": 50.0,
                    "late_game": 50.0,
                },
            }

        # 1. Damage Profile Breakdown
        ad_points = 0.0
        ap_points = 0.0
        true_points = 0.0

        for c in champ_objs:
            dtype = (c.get("damage_type") or "AD").upper()
            if dtype == "AD":
                ad_points += 1.0
            elif dtype == "AP":
                ap_points += 1.0
            elif dtype == "HYBRID":
                ad_points += 0.5
                ap_points += 0.5
            elif dtype == "TRUE":
                true_points += 1.0
            else:
                ad_points += 0.5
                ap_points += 0.5

        total_dmg = max(0.1, ad_points + ap_points + true_points)
        ad_ratio = round(ad_points / total_dmg, 3)
        ap_ratio = round(ap_points / total_dmg, 3)
        true_ratio = round(true_points / total_dmg, 3)

        warning = None
        if ad_ratio > 0.82:
            warning = "CRITICAL: AD OVERLOAD (>82% AD). Extreme vulnerability to Thornmail/Armor stacking."
        elif ap_ratio > 0.82:
            warning = "CRITICAL: AP OVERLOAD (>82% AP). Extreme vulnerability to Force of Nature/MR stacking."

        # 2. Utility Radar (0-100)
        n = len(champ_objs)
        cc_rating = round(sum(c.get("cc", 50) for c in champ_objs) / n, 1)
        engage_rating = round(sum(c.get("engage", 50) for c in champ_objs) / n, 1)
        poke_rating = round(sum(c.get("poke", 50) for c in champ_objs) / n, 1)
        waveclear_rating = round(sum(c.get("waveclear", 50) for c in champ_objs) / n, 1)
        scaling_rating = round(sum(c.get("scaling", 50) for c in champ_objs) / n, 1)

        # 3. Power Spike Curve
        early_game = round(0.4 * engage_rating + 0.4 * poke_rating + 0.2 * (100.0 - scaling_rating), 1)
        mid_game = round(0.35 * cc_rating + 0.35 * waveclear_rating + 0.30 * engage_rating, 1)
        late_game = round(float(scaling_rating), 1)

        return {
            "damage_profile": {
                "ad_ratio": ad_ratio,
                "ap_ratio": ap_ratio,
                "true_ratio": true_ratio,
                "warning": warning,
            },
            "utility_radar": {
                "cc_rating": cc_rating,
                "engage_rating": engage_rating,
                "poke_rating": poke_rating,
                "waveclear_rating": waveclear_rating,
                "scaling_rating": scaling_rating,
            },
            "power_spike": {
                "early_game": early_game,
                "mid_game": mid_game,
                "late_game": late_game,
            },
        }

    def compute_synergy_score(self, team_champions: List[str]) -> float:
        """Compute sum of pairwise synergy bonuses across team roster."""
        total_synergy = 0.0
        n = len(team_champions)
        for i in range(n):
            for j in range(i + 1, n):
                score = self.db.get_synergy(team_champions[i], team_champions[j])
                total_synergy += score
        return round(total_synergy, 4)

    def compute_counter_score(self, blue_team: List[str], red_team: List[str]) -> float:
        """Compute net counter delta advantage for blue team against red team."""
        total_delta = 0.0
        for b in blue_team:
            for r in red_team:
                delta = self.db.get_counter_delta(b, r)
                total_delta += delta
        return round(total_delta, 4)

    def simulate_win_probability(
        self,
        blue_team: List[str],
        red_team: List[str],
        iterations: int = 10000,
        seed: Optional[int] = 42,
    ) -> Dict[str, Any]:
        """Perform Monte Carlo draft simulation combining base win-rates, synergies, and counters.

        Args:
            blue_team: List of Blue team champions.
            red_team: List of Red team champions.
            iterations: Number of simulated match runs (default: 10,000).
            seed: Deterministic RNG seed for repeatable testing.

        Returns:
            Dictionary with blue_win_rate, red_win_rate, iterations, and synergy/counter deltas.
        """
        blue_champs = [self.db.get_champion(c) for c in blue_team if self.db.get_champion(c)]
        red_champs = [self.db.get_champion(c) for c in red_team if self.db.get_champion(c)]

        blue_base_wr = (sum(c["win_rate"] for c in blue_champs) / len(blue_champs)) if blue_champs else 0.50
        red_base_wr = (sum(c["win_rate"] for c in red_champs) / len(red_champs)) if red_champs else 0.50

        blue_synergy = self.compute_synergy_score(blue_team)
        red_synergy = self.compute_synergy_score(red_team)

        counter_delta = self.compute_counter_score(blue_team, red_team)

        # Team composition imbalance penalty
        blue_comp = self.analyze_team_composition(blue_team)
        red_comp = self.analyze_team_composition(red_team)
        blue_penalty = -0.04 if blue_comp["damage_profile"]["warning"] else 0.0
        red_penalty = -0.04 if red_comp["damage_profile"]["warning"] else 0.0

        # Mean expected strength advantage for Blue
        expected_delta = (
            (blue_base_wr - red_base_wr)
            + ((blue_synergy - red_synergy) * 0.4)
            + (counter_delta * 0.5)
            + (blue_penalty - red_penalty)
        )

        rng = random.Random(seed) if seed is not None else random.Random()
        std_dev = 0.18

        blue_wins = 0
        for _ in range(iterations):
            sampled_performance = rng.gauss(expected_delta, std_dev)
            if sampled_performance > 0.0:
                blue_wins += 1

        blue_win_rate = round(blue_wins / iterations, 4)
        red_win_rate = round(1.0 - blue_win_rate, 4)

        return {
            "blue_win_rate": blue_win_rate,
            "red_win_rate": red_win_rate,
            "iterations": iterations,
            "blue_synergy": blue_synergy,
            "red_synergy": red_synergy,
            "counter_delta": counter_delta,
            "expected_delta": round(expected_delta, 4),
        }

    def recommend_picks(
        self,
        current_team: List[str],
        enemy_team: List[str],
        role: Optional[str] = None,
        top_n: int = 3,
    ) -> List[Dict[str, Any]]:
        """Recommend optimal champions to draft based on synergy, counters, and meta strength.

        Args:
            current_team: Current allied champion roster.
            enemy_team: Enemy champion roster.
            role: Desired role filter ('TOP', 'JUNGLE', 'MID', 'ADC', 'SUPPORT').
            top_n: Number of recommendations to return.

        Returns:
            List of recommended champions sorted by net expected win delta.
        """
        all_champions = self.db.get_all_champions()
        taken_names = {c.lower() for c in (current_team + enemy_team)}
        candidates = []

        for cand in all_champions:
            c_id = cand["id"].lower()
            c_name = cand["name"].lower()
            if c_id in taken_names or c_name in taken_names:
                continue

            if role:
                roles_list = [r.strip().upper() for r in (cand.get("roles") or "").split(",")]
                if role.upper() not in roles_list:
                    continue

            # Synergy with current teammates
            syn_bonus = sum(self.db.get_synergy(cand["name"], mate) for mate in current_team)
            # Counter advantage vs enemies
            cnt_bonus = sum(self.db.get_counter_delta(cand["name"], enemy) for enemy in enemy_team)
            # Baseline win rate delta relative to 50%
            wr_delta = cand.get("win_rate", 0.50) - 0.50

            net_win_delta = round(wr_delta + (syn_bonus * 0.45) + (cnt_bonus * 0.55), 4)

            reasons = []
            if syn_bonus > 0.05:
                reasons.append(f"Pairwise synergy bonus (+{syn_bonus * 100:.1f}%)")
            if cnt_bonus > 0.05:
                reasons.append(f"Matchup counter advantage (+{cnt_bonus * 100:.1f}%)")
            if wr_delta > 0.005:
                reasons.append(f"High tier win rate ({cand['win_rate'] * 100:.1f}%)")
            if not reasons:
                reasons.append(f"Balanced {cand.get('damage_type', 'AD')} pick")

            candidates.append({
                "champion": cand["name"],
                "champion_id": cand["id"],
                "roles": cand.get("roles", ""),
                "damage_type": cand.get("damage_type", "AD"),
                "win_rate": cand.get("win_rate", 0.50),
                "synergy_bonus": round(syn_bonus, 3),
                "counter_bonus": round(cnt_bonus, 3),
                "net_win_delta": net_win_delta,
                "reasoning": "; ".join(reasons),
            })

        candidates.sort(key=lambda x: x["net_win_delta"], reverse=True)
        return candidates[:top_n]
