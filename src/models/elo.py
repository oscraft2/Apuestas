"""
CAPA 3: Sistema ELO dinámico — pre-cargado desde standings
"""
import math
import json
import os
from collections import defaultdict
from config import config


class EloSystem:
    BASE = 1500.0
    K = 40.0
    HOME_ADV = 65.0

    def __init__(self, ratings_file: str = None):
        self.ratings: dict = defaultdict(lambda: self.BASE)
        self.ratings_file = ratings_file or os.path.join(config.cache_dir, "elo_ratings.json")
        self._load_persisted()

    def _load_persisted(self):
        if os.path.exists(self.ratings_file):
            with open(self.ratings_file, "r") as f:
                saved = json.load(f)
                for k, v in saved.items():
                    self.ratings[k] = v

    def save(self):
        os.makedirs(os.path.dirname(self.ratings_file), exist_ok=True)
        with open(self.ratings_file, "w") as f:
            json.dump(dict(self.ratings), f, indent=2)

    def load_from_standings(self, standings: list):
        """Pre-carga ratings desde tabla de posiciones de la liga.
        Posición 1 → 1800, último lugar → 1500.
        """
        n = len(standings)
        for i, team in enumerate(standings):
            name = team.get("team", {}).get("name", "")
            if name:
                self.ratings[name] = self.BASE + int(
                    config.elo_spread * (1 - i / max(n - 1, 1))
                )
        self.save()

    def predict(self, home: str, away: str) -> dict:
        hr = self.ratings[home] + self.HOME_ADV
        ar = self.ratings[away]
        e = 1 / (1 + 10 ** ((ar - hr) / 400))

        diff = abs(hr - ar)
        draw_factor = max(0.15, 0.30 - diff / 2000)

        hw = e * (1 - draw_factor)
        aw = (1 - e) * (1 - draw_factor)
        dr = 1 - hw - aw

        return {
            "home": round(hw, 4),
            "draw": round(dr, 4),
            "away": round(aw, 4),
            "home_elo": round(self.ratings[home]),
            "away_elo": round(self.ratings[away]),
        }

    def update(self, home: str, away: str, home_goals: int, away_goals: int):
        """Actualiza ratings después de un partido real."""
        actual = 1.0 if home_goals > away_goals else 0.0 if home_goals < away_goals else 0.5
        margin = abs(home_goals - away_goals)
        mult = math.log(margin + 1) / math.log(2) if margin > 1 else 1.0

        hr = self.ratings[home] + self.HOME_ADV
        ar = self.ratings[away]
        exp = 1 / (1 + 10 ** ((ar - hr) / 400))

        delta = self.K * mult * (actual - exp)
        self.ratings[home] += delta
        self.ratings[away] -= delta
        self.save()
