"""
Feature #4 — Calibración de confianza por liga
Calcula qué tan bien calibrado está el modelo en cada liga usando
Brier Score y ECE (Expected Calibration Error).
Aplica penalizador automático en ligas con historial débil.
"""
import json
import logging
import math
from collections import defaultdict
from pathlib import Path
from config import config

logger = logging.getLogger(__name__)


class LeagueCalibration:
    """
    Lee el historial del tracker y calcula métricas de calibración por liga.
    El motor puede usar el penalty_factor para reducir el peso del modelo
    en ligas donde históricamente falla.
    """

    def __init__(self, predictions_file: str = None):
        self.filepath = Path(predictions_file or f"{config.predictions_dir}/predictions.jsonl")
        self._stats: dict = {}

    def compute(self) -> dict:
        """Calcula y retorna calibración por liga."""
        if not self.filepath.exists():
            return {}

        by_league: dict = defaultdict(lambda: {
            "bets": [],
            "brier": 0.0,
            "n": 0,
            "won": 0,
        })

        lines = [l for l in self.filepath.read_text().strip().split("\n") if l.strip()]
        for line in lines:
            pred = json.loads(line)
            if "result" not in pred:
                continue
            league = pred.get("league", "unknown")
            for vb in pred.get("value_bets", []):
                if "won" not in vb:
                    continue
                prob = vb.get("prob", 0)
                won = 1 if vb["won"] else 0
                by_league[league]["bets"].append((prob, won))
                by_league[league]["n"] += 1
                by_league[league]["won"] += won
                # Brier score acumulado
                by_league[league]["brier"] += (prob - won) ** 2

        result = {}
        for league, d in by_league.items():
            n = d["n"]
            if n == 0:
                continue
            brier = round(d["brier"] / n, 4)
            hit_rate = round(d["won"] / n, 3)
            avg_prob = round(sum(p for p, _ in d["bets"]) / n, 3)
            calibration_error = round(abs(avg_prob - hit_rate), 3)

            # Penalty factor: cuanto más alto el error de calibración, menor confianza
            # 0 error → factor 1.0 (sin penalización)
            # 0.1 error → factor 0.9
            # 0.2+ error → factor 0.8 (penalización máxima)
            penalty_factor = round(max(0.7, 1.0 - calibration_error * 2), 3)

            result[league] = {
                "n": n,
                "hit_rate": hit_rate,
                "avg_model_prob": avg_prob,
                "calibration_error": calibration_error,
                "brier_score": brier,
                "penalty_factor": penalty_factor,
                "grade": self._grade(brier, calibration_error),
            }

        self._stats = result
        return result

    @staticmethod
    def _grade(brier: float, cal_error: float) -> str:
        score = (1 - brier) * 0.6 + (1 - cal_error * 5) * 0.4
        if score >= 0.90:
            return "A"
        if score >= 0.80:
            return "B"
        if score >= 0.70:
            return "C"
        return "D"

    def get_penalty(self, league: str) -> float:
        """Retorna el factor de penalización para una liga (0.7–1.0)."""
        if not self._stats:
            self.compute()
        return self._stats.get(league, {}).get("penalty_factor", 1.0)

    def get_ece_bins(self, league: str, n_bins: int = 10) -> list:
        """Expected Calibration Error por bins para gráfico de calibración."""
        if not self.filepath.exists():
            return []
        lines = [l for l in self.filepath.read_text().strip().split("\n") if l.strip()]
        bins: dict[int, list] = defaultdict(list)
        for line in lines:
            pred = json.loads(line)
            if pred.get("league") != league or "result" not in pred:
                continue
            for vb in pred.get("value_bets", []):
                if "won" not in vb:
                    continue
                prob = vb.get("prob", 0)
                b = int(min(prob * n_bins, n_bins - 1))
                bins[b].append((prob, 1 if vb["won"] else 0))

        result = []
        for i in range(n_bins):
            data = bins.get(i, [])
            if not data:
                continue
            avg_p = sum(p for p, _ in data) / len(data)
            avg_o = sum(o for _, o in data) / len(data)
            result.append({
                "bin": round(i / n_bins + 0.05, 2),
                "predicted": round(avg_p, 3),
                "actual": round(avg_o, 3),
                "n": len(data),
            })
        return result

    def format_report(self) -> str:
        stats = self.compute()
        if not stats:
            return "📊 Sin datos suficientes para calibración por liga."

        lines = ["<b>🎯 Calibración del modelo por liga</b>", "─" * 34]
        for league, d in sorted(stats.items(), key=lambda x: x[1]["penalty_factor"], reverse=True):
            grade = d["grade"]
            grade_emoji = {"A": "🟢", "B": "🟡", "C": "🟠", "D": "🔴"}.get(grade, "⚪")
            lines.append(
                f"{grade_emoji} <b>{league[:20]}</b> [{grade}]\n"
                f"   n={d['n']} | HR {d['hit_rate']:.1%} | "
                f"Error cal.: {d['calibration_error']:.3f} | "
                f"Factor: ×{d['penalty_factor']}"
            )
        lines.append("\n<i>Factor &lt;1.0 = modelo penalizado en esa liga</i>")
        return "\n".join(lines)
