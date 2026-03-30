"""
Feature #5 — Mercados extendidos
BTTS (ambos marcan), Doble oportunidad (1X/X2/12), goles exactos,
resultado en descanso. Todas las probabilidades salen del modelo Poisson.
"""
from src.models.poisson import PoissonModel
from config import config

_poisson = PoissonModel()


class ExtendedMarkets:

    def analyze_btts(self, bookmakers: list, poisson_result: dict) -> dict:
        """Ambos anotan (Both Teams To Score)."""
        bm_yes, bm_no = [], []
        bm_map = {}

        for bm in bookmakers:
            key = bm.get("key", "")
            name = bm.get("title", key)
            for mkt in bm.get("markets", []):
                if mkt.get("key") not in ("btts", "both_teams_score"):
                    continue
                yes_o = no_o = None
                for o in mkt.get("outcomes", []):
                    n = o["name"].lower()
                    if n in ("yes", "si", "sí"):
                        yes_o = o["price"]
                        bm_yes.append(yes_o)
                    elif n in ("no",):
                        no_o = o["price"]
                        bm_no.append(no_o)
                if yes_o and no_o:
                    bm_map[key] = {"name": name, "yes": yes_o, "no": no_o}

        model_yes = poisson_result.get("btts", {}).get("yes", 0)
        model_no = poisson_result.get("btts", {}).get("no", 0)

        value_bets = []
        if bm_map:
            best_yes = max(bm_yes) if bm_yes else 0
            best_no = max(bm_no) if bm_no else 0
            for side, best, prob in [("yes", best_yes, model_yes), ("no", best_no, model_no)]:
                if not (config.min_odds <= best <= config.max_odds):
                    continue
                ev = (prob * best) - 1
                if ev >= config.min_value_pct:
                    b = best - 1
                    kelly = max(0.0, ((prob * b) - (1 - prob)) / b * 0.25) if b > 0 else 0
                    label = "✅ Sí marcan" if side == "yes" else "❌ No marcan ambos"
                    value_bets.append({
                        "market": "BTTS",
                        "outcome": side,
                        "label": label,
                        "odds": round(best, 2),
                        "prob": round(prob, 4),
                        "fair_odds": round(1 / prob, 2) if prob > 0 else 99,
                        "value": round(ev, 4),
                        "kelly": round(kelly, 4),
                    })

        return {
            "model_yes": round(model_yes, 4),
            "model_no": round(model_no, 4),
            "num_bookmakers": len(bm_map),
            "value_bets_btts": sorted(value_bets, key=lambda x: x["value"], reverse=True),
        }

    def analyze_double_chance(self, bookmakers: list, poisson_result: dict, home: str, away: str) -> dict:
        """Doble oportunidad: 1X (local o empate), X2 (empate o visita), 12 (cualquier ganador)."""
        p = poisson_result.get("probs_1x2", {})
        ph = p.get("home", 0)
        pd = p.get("draw", 0)
        pa = p.get("away", 0)

        model_probs = {
            "1X": round(ph + pd, 4),
            "X2": round(pd + pa, 4),
            "12": round(ph + pa, 4),
        }

        best_odds_dc: dict[str, tuple] = {}
        for bm in bookmakers:
            key = bm.get("key", "")
            name = bm.get("title", key)
            for mkt in bm.get("markets", []):
                if mkt.get("key") != "double_chance":
                    continue
                for o in mkt.get("outcomes", []):
                    n = o["name"]
                    mapping = {home: "1X", "Draw No Bet Home": "1X",
                               away: "X2", "Draw No Bet Away": "X2",
                               f"{home}/{away}": "12"}
                    dc_key = None
                    if "Draw" not in n and home in n:
                        dc_key = "1X"
                    elif "Draw" not in n and away in n:
                        dc_key = "X2"
                    elif home in n and away in n:
                        dc_key = "12"
                    if dc_key and o["price"] > best_odds_dc.get(dc_key, (0, ""))[0]:
                        best_odds_dc[dc_key] = (o["price"], name)

        value_bets = []
        labels = {"1X": f"🏠/🤝 {home[:10]} o Empate", "X2": f"🤝/✈️ Empate o {away[:10]}", "12": "🏠/✈️ Sin empate"}
        for dc, prob in model_probs.items():
            if dc not in best_odds_dc:
                continue
            odds, bm_name = best_odds_dc[dc]
            if not (config.min_odds <= odds <= config.max_odds):
                continue
            ev = (prob * odds) - 1
            if ev >= config.min_value_pct:
                b = odds - 1
                kelly = max(0.0, ((prob * b) - (1 - prob)) / b * 0.25) if b > 0 else 0
                value_bets.append({
                    "market": "Doble oportunidad",
                    "outcome": dc,
                    "label": labels[dc],
                    "odds": round(odds, 2),
                    "bookmaker": bm_name,
                    "prob": round(prob, 4),
                    "fair_odds": round(1 / prob, 2) if prob > 0 else 99,
                    "value": round(ev, 4),
                    "kelly": round(kelly, 4),
                })

        return {
            "model_probs": model_probs,
            "value_bets_dc": sorted(value_bets, key=lambda x: x["value"], reverse=True),
        }

    def analyze_exact_goals(self, poisson_result: dict) -> list:
        """Top 3 marcadores más probables desde la distribución Poisson."""
        xg_h = poisson_result.get("xg_home", 1.3)
        xg_a = poisson_result.get("xg_away", 1.1)
        matrix = {}
        for i in range(8):
            for j in range(8):
                p = _poisson.pmf(xg_h, i) * _poisson.pmf(xg_a, j)
                matrix[(i, j)] = round(p, 4)
        top = sorted(matrix.items(), key=lambda x: x[1], reverse=True)[:5]
        return [{"score": f"{s[0]}-{s[1]}", "prob": p} for s, p in top]

    def analyze_halftime(self, poisson_result: dict) -> dict:
        """Probabilidad de resultado al descanso (mitad de xG)."""
        xg_h = poisson_result.get("xg_home", 1.3) / 2
        xg_a = poisson_result.get("xg_away", 1.1) / 2
        result = _poisson.predict(xg_h, xg_a, max_goals=5)
        return {
            "probs_ht": result["probs_1x2"],
            "top_ht_score": result["top_score"],
            "top_ht_prob": result["top_score_prob"],
        }
