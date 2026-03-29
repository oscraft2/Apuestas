"""
CAPA 6: Consenso ponderado + detección de value bets
Pesos: Mercado 35% | Poisson 25% | ELO 15% | Features 15% | DeepSeek 10%
"""
import math
from config import config


class ConsensusEngine:
    WEIGHTS = {
        "market":   0.35,
        "poisson":  0.25,
        "elo":      0.15,
        "features": 0.15,
        "deepseek": 0.10,
    }

    def combine_1x2(self, models: dict, ai_adj: dict = None) -> dict:
        active = {k: v for k, v in models.items() if v}
        if not active:
            return {}

        w = {k: self.WEIGHTS.get(k, 0.10) for k in active}
        tw = sum(w.values())
        w = {k: v / tw for k, v in w.items()}

        prob = {"home": 0.0, "draw": 0.0, "away": 0.0}
        for name, probs in active.items():
            for o in prob:
                prob[o] += probs.get(o, 0) * w[name]

        # Ajuste IA (máx ±5%)
        if ai_adj:
            for o in prob:
                adj = max(-config.deepseek_max_adjustment,
                          min(config.deepseek_max_adjustment, ai_adj.get(o, 0)))
                prob[o] += adj * self.WEIGHTS.get("deepseek", 0.10)

        total = sum(prob.values())
        if total > 0:
            prob = {k: round(v / total, 4) for k, v in prob.items()}

        agreement = self._agreement(active)
        fair = {k: round(1 / v, 2) if v > 0 else 99.0 for k, v in prob.items()}
        confidence = round(1 - self._entropy(prob) / math.log(3), 3)

        return {
            "probs": prob,
            "fair_odds": fair,
            "agreement": agreement,
            "confidence": confidence,
            "models_used": list(active.keys()),
        }

    def combine_ou(self, models: dict, ai_adj: dict = None) -> dict:
        active = {k: v for k, v in models.items() if v}
        if not active:
            return {}

        w = {k: self.WEIGHTS.get(k, 0.10) for k in active}
        tw = sum(w.values())
        w = {k: v / tw for k, v in w.items()}

        prob = {"over": 0.0, "under": 0.0}
        for name, probs in active.items():
            for o in prob:
                prob[o] += probs.get(o, 0) * w[name]

        if ai_adj:
            for o in prob:
                adj = max(-config.deepseek_max_adjustment,
                          min(config.deepseek_max_adjustment, ai_adj.get(o, 0)))
                prob[o] += adj * self.WEIGHTS.get("deepseek", 0.10)

        total = sum(prob.values())
        if total > 0:
            prob = {k: round(v / total, 4) for k, v in prob.items()}

        fair = {k: round(1 / v, 2) if v > 0 else 99.0 for k, v in prob.items()}
        return {"probs": prob, "fair_odds": fair}

    def detect_value(self, consensus_prob: dict, best_odds: dict, market_label: str) -> list:
        values = []
        for outcome, prob in consensus_prob.items():
            odds = best_odds.get(outcome, 0)
            if prob <= 0 or odds <= 1:
                continue
            if not (config.min_odds <= odds <= config.max_odds):
                continue
            ev = (prob * odds) - 1
            if ev >= config.min_value_pct:
                b = odds - 1
                kelly = max(0.0, ((prob * b) - (1 - prob)) / b * 0.25)
                values.append({
                    "market": market_label,
                    "outcome": outcome,
                    "prob": round(prob, 4),
                    "odds": round(odds, 2),
                    "fair_odds": round(1 / prob, 2),
                    "value": round(ev, 4),
                    "kelly": round(kelly, 4),
                })
        return sorted(values, key=lambda x: x["value"], reverse=True)

    @staticmethod
    def _agreement(models: dict) -> float:
        if len(models) < 2:
            return 1.0
        favs = [max(p, key=p.get) for p in models.values()]
        top = max(set(favs), key=favs.count)
        return round(favs.count(top) / len(favs), 2)

    @staticmethod
    def _entropy(probs: dict) -> float:
        return -sum(p * math.log(p) if p > 0 else 0 for p in probs.values())
