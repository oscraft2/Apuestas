"""
CAPA 4: Feature Engineering — forma, tendencia de goles, rachas, H2H
"""
from statistics import mean
from typing import Optional


class FeatureEngine:

    @staticmethod
    def form_points(results: list, n: int = 5) -> float:
        recent = results[-n:]
        if not recent:
            return 0.5
        pts = sum(3 if r == "W" else 1 if r == "D" else 0 for r in recent)
        return round(pts / (3 * len(recent)), 3)

    @staticmethod
    def goals_trend(goals: list, n: int = 5) -> float:
        g = goals[-n:]
        if len(g) < 2:
            return 0.0
        xm = (len(g) - 1) / 2
        ym = mean(g)
        num = sum((i - xm) * (y - ym) for i, y in enumerate(g))
        den = sum((i - xm) ** 2 for i in range(len(g)))
        return round(num / den, 3) if den > 0 else 0.0

    @staticmethod
    def streak(results: list) -> dict:
        if not results:
            return {"type": "N/A", "len": 0}
        cur = results[-1]
        length = 0
        for r in reversed(results):
            if r == cur:
                length += 1
            else:
                break
        names = {"W": "victoria", "D": "empate", "L": "derrota"}
        return {"type": names.get(cur, "?"), "len": length}

    @staticmethod
    def h2h_summary(h2h_matches: list, home_team: str) -> dict:
        if not h2h_matches:
            return {"home_wins": 0, "draws": 0, "away_wins": 0, "total": 0}
        home_w = draws = away_w = 0
        for match in h2h_matches:
            goals = match.get("goals", {})
            hg = goals.get("home", 0) or 0
            ag = goals.get("away", 0) or 0
            ht = match.get("teams", {}).get("home", {}).get("name", "")
            if hg > ag:
                if ht == home_team:
                    home_w += 1
                else:
                    away_w += 1
            elif hg < ag:
                if ht == home_team:
                    away_w += 1
                else:
                    home_w += 1
            else:
                draws += 1
        return {
            "home_wins": home_w,
            "draws": draws,
            "away_wins": away_w,
            "total": len(h2h_matches),
        }

    def build(self, home: dict, away: dict, h2h: Optional[list] = None) -> dict:
        hf = self.form_points(home.get("results", []))
        af = self.form_points(away.get("results", []))
        hs = self.streak(home.get("results", []))
        as_ = self.streak(away.get("results", []))

        hgf = home.get("goals_for", [])
        hga = home.get("goals_against", [])
        agf = away.get("goals_for", [])
        aga = away.get("goals_against", [])

        feats = {
            "home_form": hf,
            "away_form": af,
            "form_diff": round(hf - af, 3),
            "home_avg_gf": round(mean(hgf[-10:]), 2) if hgf else 1.3,
            "home_avg_ga": round(mean(hga[-10:]), 2) if hga else 1.0,
            "away_avg_gf": round(mean(agf[-10:]), 2) if agf else 1.1,
            "away_avg_ga": round(mean(aga[-10:]), 2) if aga else 1.2,
            "home_goals_trend": self.goals_trend(hgf),
            "away_goals_trend": self.goals_trend(agf),
            "home_streak": hs,
            "away_streak": as_,
        }

        if h2h:
            feats["h2h"] = self.h2h_summary(h2h, home.get("name", ""))

        # Prob heurística desde features
        fd = feats["form_diff"]
        gd = (feats["home_avg_gf"] - feats["away_avg_gf"]) - (
            feats["home_avg_ga"] - feats["away_avg_ga"]
        )
        score = 0.5 + fd * 0.3 + gd / 3 * 0.4
        score = max(0.2, min(0.7, score))
        feats["prob_1x2"] = {
            "home": round(score, 4),
            "draw": 0.25,
            "away": round(max(0.05, 1 - score - 0.25), 4),
        }

        return feats
