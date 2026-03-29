"""
CAPA 1: Análisis de mercado — 1X2 + Over/Under 2.5
"""
from statistics import mean
from config import config


class MarketAnalyzer:
    SHARP_BOOKS = {"pinnacle", "pinnacle_com", "matchbook", "betfair_ex_eu"}

    def analyze_h2h(self, bookmakers: list, home: str, away: str) -> dict:
        all_odds = {"home": [], "draw": [], "away": []}
        bm_odds = {}
        sharp_odds = None
        sharp_margin = float("inf")

        for bm in bookmakers:
            key = bm.get("key", "")
            name = bm.get("title", key)
            for market in bm.get("markets", []):
                if market["key"] != "h2h":
                    continue
                outcomes = market.get("outcomes", [])
                if len(outcomes) < 3:
                    continue
                odds = {}
                for o in outcomes:
                    if o["name"] == home:
                        odds["home"] = o["price"]
                    elif o["name"] == away:
                        odds["away"] = o["price"]
                    elif o["name"] == "Draw":
                        odds["draw"] = o["price"]

                if len(odds) == 3:
                    for k in odds:
                        all_odds[k].append(odds[k])
                    bm_odds[key] = {"name": name, "odds": odds}
                    margin = sum(1 / v for v in odds.values()) - 1
                    if key.lower() in self.SHARP_BOOKS and margin < sharp_margin:
                        sharp_odds = odds
                        sharp_margin = margin

        if not all_odds["home"] or len(bm_odds) < config.min_bookmakers:
            return {}

        avg = {k: mean(v) for k, v in all_odds.items()}
        best = {k: max(v) for k, v in all_odds.items()}
        implied = self._remove_vig(avg)
        sharp_prob = self._remove_vig(sharp_odds) if sharp_odds else self._remove_vig(best)

        spreads = {}
        for o in ["home", "draw", "away"]:
            vals = all_odds[o]
            spreads[o] = (max(vals) - min(vals)) / min(vals) if len(vals) >= 2 else 0

        labels = {"home": f"🏠 {home}", "draw": "🤝 Empate", "away": f"✈️ {away}"}
        value_bets = []
        for outcome in ["home", "draw", "away"]:
            best_odd = 0
            best_bm = ""
            for k, d in bm_odds.items():
                o = d["odds"].get(outcome, 0)
                if o > best_odd:
                    best_odd = o
                    best_bm = d["name"]

            if not (config.min_odds <= best_odd <= config.max_odds):
                continue
            prob = sharp_prob.get(outcome, 0)
            if prob <= 0:
                continue
            value = (prob * best_odd) - 1
            if value >= config.min_value_pct:
                value_bets.append({
                    "market": "1X2",
                    "outcome": outcome,
                    "label": labels[outcome],
                    "best_odds": round(best_odd, 2),
                    "bookmaker": best_bm,
                    "market_prob": round(implied.get(outcome, 0), 4),
                    "sharp_prob": round(prob, 4),
                    "fair_odds": round(1 / prob, 2) if prob > 0 else 0,
                    "value": round(value, 4),
                    "kelly": round(self._kelly(prob, best_odd), 4),
                })

        return {
            "avg_odds": avg,
            "best_odds": best,
            "implied_prob": implied,
            "sharp_prob": sharp_prob,
            "market_margin": round(sum(1 / v for v in avg.values()) - 1, 4),
            "num_bookmakers": len(bm_odds),
            "spreads": spreads,
            "value_bets_1x2": sorted(value_bets, key=lambda x: x["value"], reverse=True),
        }

    def analyze_totals(self, bookmakers: list) -> dict:
        over_odds, under_odds = [], []
        bm_totals = {}

        for bm in bookmakers:
            key = bm.get("key", "")
            name = bm.get("title", key)
            for market in bm.get("markets", []):
                if market["key"] != "totals":
                    continue
                over_o = under_o = None
                for o in market.get("outcomes", []):
                    if o.get("point", 2.5) != 2.5:
                        continue
                    if o["name"] == "Over":
                        over_o = o["price"]
                        over_odds.append(o["price"])
                    elif o["name"] == "Under":
                        under_o = o["price"]
                        under_odds.append(o["price"])
                if over_o and under_o:
                    bm_totals[key] = {"name": name, "over": over_o, "under": under_o}

        if not over_odds or len(bm_totals) < 3:
            return {}

        avg_over = mean(over_odds)
        avg_under = mean(under_odds)
        best_over = max(over_odds)
        best_under = max(under_odds)

        total = (1 / avg_over) + (1 / avg_under)
        over_prob = (1 / avg_over) / total
        under_prob = (1 / avg_under) / total

        total_s = (1 / best_over) + (1 / best_under)
        sharp_over = (1 / best_over) / total_s
        sharp_under = (1 / best_under) / total_s

        value_bets = []
        for side, prob, best, label in [
            ("over", sharp_over, best_over, "⬆️ Over 2.5"),
            ("under", sharp_under, best_under, "⬇️ Under 2.5"),
        ]:
            if not (config.min_odds <= best <= config.max_odds):
                continue
            value = (prob * best) - 1
            best_bm = next((d["name"] for d in bm_totals.values() if d[side] == best), "")
            if value >= config.min_value_pct:
                value_bets.append({
                    "market": "O/U 2.5",
                    "outcome": side,
                    "label": label,
                    "best_odds": round(best, 2),
                    "bookmaker": best_bm,
                    "market_prob": round(over_prob if side == "over" else under_prob, 4),
                    "sharp_prob": round(prob, 4),
                    "fair_odds": round(1 / prob, 2) if prob > 0 else 0,
                    "value": round(value, 4),
                    "kelly": round(self._kelly(prob, best), 4),
                })

        return {
            "point": 2.5,
            "avg_over": round(avg_over, 2),
            "avg_under": round(avg_under, 2),
            "over_prob": round(over_prob, 4),
            "under_prob": round(under_prob, 4),
            "num_bookmakers": len(bm_totals),
            "value_bets_ou": sorted(value_bets, key=lambda x: x["value"], reverse=True),
        }

    @staticmethod
    def _remove_vig(odds: dict) -> dict:
        if not odds:
            return {}
        raw = {k: 1 / v for k, v in odds.items() if v > 0}
        total = sum(raw.values())
        return {k: round(p / total, 4) for k, p in raw.items()} if total > 0 else {}

    @staticmethod
    def _kelly(prob: float, odds: float, fraction: float = 0.25) -> float:
        if prob <= 0 or prob >= 1 or odds <= 1:
            return 0
        b = odds - 1
        k = (prob * b - (1 - prob)) / b
        return max(0, k * fraction)
