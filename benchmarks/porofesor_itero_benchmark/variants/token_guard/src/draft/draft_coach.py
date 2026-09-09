"""
iTero-style AI Draft Intelligence Coach for Hextech Oracle.
Evaluates team comp radar, damage ratios, pairwise synergies, counter deltas,
and executes fast Monte Carlo win-rate draft simulations.
"""

from __future__ import annotations

import itertools
import logging
import math
import random
from typing import Any, Dict, List, Optional

from src.storage.db import HextechDatabase

logger = logging.getLogger(__name__)


class DraftCoach:
    """
    Algorithmic draft coach calculating team balance metrics, synergy boosts,
    counter scoring matrices, and Monte Carlo predictive win probabilities.
    """

    def __init__(self, db: HextechDatabase) -> None:
        self.db = db
        self._champ_cache: Dict[str, Dict[str, Any]] = {}
        self._load_cache()

    def _load_cache(self) -> None:
        """Cache all champions for fast iterative simulation lookups."""
        champs = self.db.get_all_champions()
        for c in champs:
            self._champ_cache[c["name"].lower()] = c
            self._champ_cache[c["id"].lower()] = c

    def get_champion(self, name_or_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve champion data from cache or database."""
        key = name_or_id.strip().lower()
        if key in self._champ_cache:
            return self._champ_cache[key]
        champ = self.db.get_champion_stats(name_or_id)
        if champ:
            self._champ_cache[champ["name"].lower()] = champ
            self._champ_cache[champ["id"].lower()] = champ
        return champ

    def analyze_team_composition(self, champions: List[str]) -> Dict[str, Any]:
        """
        Analyzes damage breakdown, utility radar (CC, engage, poke, waveclear, scaling),
        and power spike curve across early, mid, and late game phases.
        """
        champ_objs: List[Dict[str, Any]] = []
        for name in champions:
            c = self.get_champion(name)
            if c:
                champ_objs.append(c)

        if not champ_objs:
            return {
                "champions_count": 0,
                "damage_profile": {
                    "ad_ratio": 0.333,
                    "ap_ratio": 0.333,
                    "true_ratio": 0.334,
                },
                "utility_radar": {
                    "cc_rating": 50.0,
                    "engage_rating": 50.0,
                    "poke_rating": 50.0,
                    "waveclear_rating": 50.0,
                    "scaling_rating": 50.0,
                },
                "power_spikes": {
                    "early_game": 50.0,
                    "mid_game": 50.0,
                    "late_game": 50.0,
                },
                "warnings": [],
            }

        total_ad = 0.0
        total_ap = 0.0
        total_true = 0.0

        total_cc = 0.0
        total_engage = 0.0
        total_poke = 0.0
        total_waveclear = 0.0
        total_scaling = 0.0

        for c in champ_objs:
            dtype = c.get("damage_type", "AD").upper()
            if dtype == "AD":
                total_ad += 1.0
            elif dtype == "AP":
                total_ap += 1.0
            elif dtype == "TRUE":
                total_true += 1.0
            elif dtype == "HYBRID":
                total_ad += 0.5
                total_ap += 0.5
            else:
                total_ad += 1.0

            total_cc += c.get("cc", 50)
            total_engage += c.get("engage", 50)
            total_poke += c.get("poke", 50)
            total_waveclear += c.get("waveclear", 50)
            total_scaling += c.get("scaling", 50)

        n = len(champ_objs)
        damage_sum = total_ad + total_ap + total_true
        ad_ratio = round(total_ad / damage_sum, 3) if damage_sum > 0 else 0.333
        ap_ratio = round(total_ap / damage_sum, 3) if damage_sum > 0 else 0.333
        true_ratio = round(max(0.0, 1.0 - (ad_ratio + ap_ratio)), 3)

        warnings: List[str] = []
        if ad_ratio > 0.82:
            warnings.append(
                f"HEAVY_PHYSICAL_DAMAGE: Comp is {int(ad_ratio * 100)}% AD. Vulnerable to Armor stacking."
            )
        if ap_ratio > 0.82:
            warnings.append(
                f"HEAVY_MAGIC_DAMAGE: Comp is {int(ap_ratio * 100)}% AP. Vulnerable to Magic Resist."
            )

        cc_rating = round(total_cc / n, 1)
        engage_rating = round(total_engage / n, 1)
        poke_rating = round(total_poke / n, 1)
        waveclear_rating = round(total_waveclear / n, 1)
        scaling_rating = round(total_scaling / n, 1)

        if cc_rating < 40.0:
            warnings.append("LOW_CROWD_CONTROL: Comp lacks hard lockdown.")
        if waveclear_rating < 40.0:
            warnings.append("WEAK_WAVECLEAR: Vulnerable to aggressive sieges.")

        # Power spike curves (0-100)
        early_game = round(
            min(100.0, max(0.0, (100.0 - scaling_rating) * 0.7 + engage_rating * 0.3)), 1
        )
        mid_game = round(
            min(100.0, max(0.0, poke_rating * 0.35 + waveclear_rating * 0.35 + cc_rating * 0.3)), 1
        )
        late_game = round(scaling_rating, 1)

        return {
            "champions_count": n,
            "damage_profile": {
                "ad_ratio": ad_ratio,
                "ap_ratio": ap_ratio,
                "true_ratio": true_ratio,
            },
            "utility_radar": {
                "cc_rating": cc_rating,
                "engage_rating": engage_rating,
                "poke_rating": poke_rating,
                "waveclear_rating": waveclear_rating,
                "scaling_rating": scaling_rating,
            },
            "power_spikes": {
                "early_game": early_game,
                "mid_game": mid_game,
                "late_game": late_game,
            },
            "warnings": warnings,
        }

    def compute_synergy_score(self, team_champions: List[str]) -> float:
        """
        Calculates the cumulative pairwise synergy score across all pairs in the team.
        """
        if len(team_champions) < 2:
            return 0.0

        total_synergy = 0.0
        for c1, c2 in itertools.combinations(team_champions, 2):
            total_synergy += self.db.get_synergy(c1, c2)

        return round(total_synergy, 4)

    def compute_counter_score(self, blue_team: List[str], red_team: List[str]) -> float:
        """
        Calculates matchup counter delta advantage.
        Returns positive value if Blue counters Red, negative if Red counters Blue.
        """
        if not blue_team or not red_team:
            return 0.0

        total_delta = 0.0
        for b_champ in blue_team:
            for r_champ in red_team:
                delta = self.db.get_counter_delta(b_champ, r_champ)
                total_delta += delta

        return round(total_delta, 4)

    def simulate_win_probability(
        self,
        blue_team: List[str],
        red_team: List[str],
        iterations: int = 5000,
    ) -> Dict[str, float]:
        """
        Executes fast Monte Carlo simulation combining baseline champion win-rates,
        pairwise synergy multipliers, and counter matchup differentials.
        """
        # Calculate baseline team win rates
        blue_champs = [self.get_champion(c) for c in blue_team]
        red_champs = [self.get_champion(c) for c in red_team]

        blue_base_wr = (
            sum(c["win_rate"] for c in blue_champs if c) / max(1, len([c for c in blue_champs if c]))
            if blue_champs
            else 0.50
        )
        red_base_wr = (
            sum(c["win_rate"] for c in red_champs if c) / max(1, len([c for c in red_champs if c]))
            if red_champs
            else 0.50
        )

        synergy_blue = self.compute_synergy_score(blue_team)
        synergy_red = self.compute_synergy_score(red_team)
        counter_delta = self.compute_counter_score(blue_team, red_team)

        # Net advantage combining baseline, synergy, and counter matrices
        net_advantage = (
            (blue_base_wr - red_base_wr)
            + (synergy_blue - synergy_red) * 0.65
            + counter_delta * 0.50
        )

        # Logistic transformation to expected win probability
        # Scaling factor 5.0 calibrates standard +/- 5-15% win probability shifts
        p_blue = 1.0 / (1.0 + math.exp(-5.0 * net_advantage))
        p_blue = max(0.05, min(0.95, p_blue))

        # Monte Carlo trial simulation
        blue_wins = 0
        for _ in range(iterations):
            if random.random() < p_blue:
                blue_wins += 1

        blue_win_rate = round(blue_wins / iterations, 4)
        red_win_rate = round(1.0 - blue_win_rate, 4)

        return {
            "blue_win_rate": blue_win_rate,
            "red_win_rate": red_win_rate,
        }

    def recommend_picks(
        self,
        current_team: List[str],
        enemy_team: List[str],
        role: Optional[str] = None,
        top_n: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Evaluates available champion pool to find optimal picks maximizing synergy
        with current team and countering enemy draft.
        """
        all_champs = self.db.get_all_champions()
        picked = {c.lower() for c in current_team + enemy_team}

        candidates: List[Dict[str, Any]] = []

        for champ in all_champs:
            name = champ["name"]
            if name.lower() in picked or champ["id"].lower() in picked:
                continue

            # Check role filter
            if role and role.strip():
                champ_roles = [r.strip().upper() for r in champ.get("roles", "").split(",")]
                if role.strip().upper() not in champ_roles:
                    continue

            # Synergy bonus with existing allies
            synergy_gain = 0.0
            synergy_details = []
            for ally in current_team:
                syn = self.db.get_synergy(name, ally)
                if syn > 0:
                    synergy_gain += syn
                    synergy_details.append(f"{ally} (+{syn})")

            # Counter advantage against existing enemies
            counter_gain = 0.0
            counter_details = []
            for enemy in enemy_team:
                delta = self.db.get_counter_delta(name, enemy)
                if delta > 0:
                    counter_gain += delta
                    counter_details.append(f"Counters {enemy} (+{delta})")
                elif delta < 0:
                    counter_gain += delta
                    counter_details.append(f"Countered by {enemy} ({delta})")

            # Win rate baseline
            wr_delta = champ.get("win_rate", 0.50) - 0.50

            # Composite AI Score
            score = (wr_delta * 1.2) + (synergy_gain * 1.5) + (counter_gain * 1.3)

            candidates.append(
                {
                    "champion": name,
                    "score": round(score, 4),
                    "win_rate": champ.get("win_rate", 0.50),
                    "roles": champ.get("roles", ""),
                    "damage_type": champ.get("damage_type", "AD"),
                    "synergy_gain": round(synergy_gain, 4),
                    "counter_gain": round(counter_gain, 4),
                    "synergies": synergy_details,
                    "counters": counter_details,
                }
            )

        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[:top_n]
