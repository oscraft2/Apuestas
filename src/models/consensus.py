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
        # Filtrar modelos vacíos o None explícitamente (bug #17)
        active = {k: v for k, v in models.items() if v and isinstance(v, dict) and len(v) >= 3}
        if not active:
            return {}

        w = {k: self.WEIGHTS.get(k, 0.10) for k in active}
        tw = sum(w.values())
        w = {k: v / tw for k, v in w.items()}

        prob = {"home": 0.0, "draw": 0.0, "away": 0.0}
        for name, probs in active.items():
            for o in prob:
                prob[o] += probs.get(o, 0) * w[name]

        # Ajuste IA: se aplica directamente (fix bug #4 — no multiplicar por peso)
        if ai_adj and isinstance(ai_adj, dict):
            for o in prob:
                adj = max(-config.deepseek_max_adjustment,
                          min(config.deepseek_max_adjustment, ai_adj.get(o, 0)))
                prob[o] += adj

        total = sum(prob.values())
        if total > 0:
            prob = {k: round(v / total, 4) for k, v in prob.items()}
        else:
            # Bug #34: fallback a distribución uniforme en lugar de dict vacío
            prob = {"home": 0.3333, "draw": 0.3333, "away": 0.3334}

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

    def combine_binary(self, models: dict, outcomes: tuple[str, str], ai_adj: dict = None) -> dict:
        active = {k: v for k, v in models.items() if v and isinstance(v, dict) and len(v) >= 2}
        if not active:
            return {}

        w = {k: self.WEIGHTS.get(k, 0.10) for k in active}
        tw = sum(w.values())
        w = {k: v / tw for k, v in w.items()}

        prob = {outcome: 0.0 for outcome in outcomes}
        for name, probs in active.items():
            for outcome in prob:
                prob[outcome] += probs.get(outcome, 0) * w[name]

        if ai_adj and isinstance(ai_adj, dict):
            for outcome in prob:
                adj = max(
                    -config.deepseek_max_adjustment,
                    min(config.deepseek_max_adjustment, ai_adj.get(outcome, 0)),
                )
                prob[outcome] += adj

        total = sum(prob.values())
        if total > 0:
            prob = {k: round(v / total, 4) for k, v in prob.items()}
        else:
            base = round(1 / len(outcomes), 4)
            prob = {outcome: base for outcome in outcomes}
            last = outcomes[-1]
            prob[last] = round(1 - sum(prob[o] for o in outcomes[:-1]), 4)

        fair = {k: round(1 / v, 2) if v > 0 else 99.0 for k, v in prob.items()}
        confidence = round(1 - self._entropy(prob) / math.log(len(outcomes)), 3) if len(outcomes) > 1 else 1.0
        agreement = self._agreement(active)
        return {
            "probs": prob,
            "fair_odds": fair,
            "agreement": agreement,
            "confidence": confidence,
            "models_used": list(active.keys()),
        }

    def combine_ou(self, models: dict, ai_adj: dict = None) -> dict:
        return self.combine_binary(models, ("over", "under"), ai_adj=ai_adj)

    def combine_btts(self, models: dict) -> dict:
        return self.combine_binary(models, ("yes", "no"))

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
                    "label": self._label_for_market(market_label, outcome),
                    "prob": round(prob, 4),
                    "odds": round(odds, 2),
                    "fair_odds": round(1 / prob, 2),
                    "value": round(ev, 4),
                    "kelly": round(kelly, 4),
                })
        return sorted(values, key=lambda x: x["value"], reverse=True)

    @staticmethod
    def _label_for_market(market_label: str, outcome: str) -> str:
        if market_label == "1X2":
            return {"home": "Gana local", "draw": "Empate", "away": "Gana visita"}.get(outcome, outcome)
        if market_label.startswith("O/U "):
            line = market_label.split(" ", 1)[1]
            return {
                "over": f"Over {line}",
                "under": f"Under {line}",
            }.get(outcome, outcome)
        if market_label == "BTTS":
            return {"yes": "Ambos marcan", "no": "No marcan ambos"}.get(outcome, outcome)
        if market_label == "Doble oportunidad":
            return outcome
        return outcome

    @staticmethod
    def _agreement(models: dict) -> float:
        if len(models) < 2:
            return 1.0
        # Bug #17: filtrar dicts vacíos antes de max()
        valid = [p for p in models.values() if p]
        if not valid:
            return 0.0
        favs = [max(p, key=p.get) for p in valid]
        top = max(set(favs), key=favs.count)
        return round(favs.count(top) / len(favs), 2)

    @staticmethod
    def _entropy(probs: dict) -> float:
        return -sum(p * math.log(p) if p > 0 else 0 for p in probs.values())
