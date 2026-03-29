"""
CAPA 2: Modelo de Poisson con xG reales desde API-Football
"""
import math


class PoissonModel:
    HOME_ADVANTAGE = 0.25

    @staticmethod
    def pmf(lam: float, k: int) -> float:
        if lam <= 0 or k < 0:
            return 0.0
        return (lam ** k) * math.exp(-lam) / math.factorial(k)

    def predict(self, xg_home: float, xg_away: float, max_goals: int = 7) -> dict:
        matrix = {}
        hw = dr = aw = 0.0
        ou25 = {"over": 0.0, "under": 0.0}
        btts = {"yes": 0.0, "no": 0.0}

        for i in range(max_goals + 1):
            for j in range(max_goals + 1):
                p = self.pmf(xg_home, i) * self.pmf(xg_away, j)
                matrix[(i, j)] = p
                if i > j:
                    hw += p
                elif i == j:
                    dr += p
                else:
                    aw += p
                if i + j > 2.5:
                    ou25["over"] += p
                else:
                    ou25["under"] += p
                if i > 0 and j > 0:
                    btts["yes"] += p
                else:
                    btts["no"] += p

        top_score = max(matrix, key=matrix.get)

        return {
            "xg_home": round(xg_home, 2),
            "xg_away": round(xg_away, 2),
            "probs_1x2": {
                "home": round(hw, 4),
                "draw": round(dr, 4),
                "away": round(aw, 4),
            },
            "probs_ou25": {
                "over": round(ou25["over"], 4),
                "under": round(ou25["under"], 4),
            },
            "btts": {
                "yes": round(btts["yes"], 4),
                "no": round(btts["no"], 4),
            },
            "top_score": f"{top_score[0]}-{top_score[1]}",
            "top_score_prob": round(matrix[top_score], 4),
        }

    def from_stats(
        self,
        home_gf: float,
        home_ga: float,
        away_gf: float,
        away_ga: float,
        league_avg: float = 2.7,
    ) -> dict:
        """Calcula xG desde estadísticas reales (goles por partido de la temporada)."""
        half = league_avg / 2
        att_h = home_gf / half if half > 0 else 1.0
        def_h = home_ga / half if half > 0 else 1.0
        att_a = away_gf / half if half > 0 else 1.0
        def_a = away_ga / half if half > 0 else 1.0

        xg_h = max(0.4, min(4.0, att_h * def_a * half + self.HOME_ADVANTAGE))
        xg_a = max(0.3, min(3.5, att_a * def_h * half))

        return self.predict(xg_h, xg_a)
