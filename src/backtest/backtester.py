"""
Feature #1 — Backtesting automático
Simula el modelo sobre datos históricos y calcula ROI real,
calibración, hit rate por mercado y por liga.
"""
import json
import logging
import math
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class BacktestBet:
    date: str
    league: str
    home: str
    away: str
    market: str
    outcome: str
    model_prob: float
    odds: float
    value: float
    kelly_fraction: float
    result: Optional[str] = None   # "won" | "lost" | "void"
    pnl: float = 0.0


@dataclass
class BacktestResult:
    total_bets: int = 0
    won: int = 0
    lost: int = 0
    void: int = 0
    pnl_flat: float = 0.0          # 1u fija por apuesta
    pnl_kelly: float = 0.0         # Kelly fraccionado (0.25)
    roi_flat: float = 0.0
    roi_kelly: float = 0.0
    hit_rate: float = 0.0
    avg_value: float = 0.0
    avg_odds: float = 0.0
    max_drawdown: float = 0.0
    sharpe: float = 0.0
    by_market: dict = field(default_factory=dict)
    by_league: dict = field(default_factory=dict)
    monthly: dict = field(default_factory=dict)
    bets: list = field(default_factory=list)


class Backtester:
    """
    Carga predicciones históricas del tracker (JSONL) junto con resultados
    reales y evalúa el modelo.

    Uso:
        bt = Backtester("data/predictions/predictions.jsonl")
        result = bt.run()
        print(result.roi_flat, result.hit_rate)
    """

    def __init__(self, predictions_file: str):
        self.path = Path(predictions_file)

    def run(self, min_value: float = 0.0, min_odds: float = 1.0, max_odds: float = 99.0) -> BacktestResult:
        if not self.path.exists():
            logger.warning("No hay predicciones guardadas para backtesting.")
            return BacktestResult()

        bets: list[BacktestBet] = []
        lines = [l for l in self.path.read_text().strip().split("\n") if l.strip()]

        for line in lines:
            pred = json.loads(line)
            if "result" not in pred:
                continue  # pendiente, omitir

            for vb in pred.get("value_bets", []):
                if vb.get("value", 0) < min_value:
                    continue
                odds = vb.get("odds", vb.get("best_odds", 1))
                if not (min_odds <= odds <= max_odds):
                    continue
                won = vb.get("won")
                if won is None:
                    continue
                result_str = "won" if won else "lost"
                pnl = vb.get("pnl", (odds - 1) if won else -1.0)

                bets.append(BacktestBet(
                    date=pred.get("date", ""),
                    league=pred.get("league", "?"),
                    home=pred.get("home", ""),
                    away=pred.get("away", ""),
                    market=vb.get("market", "?"),
                    outcome=vb.get("outcome", "?"),
                    model_prob=vb.get("prob", 0),
                    odds=odds,
                    value=vb.get("value", 0),
                    kelly_fraction=vb.get("kelly", 0),
                    result=result_str,
                    pnl=pnl,
                ))

        if not bets:
            return BacktestResult()

        return self._compute(bets)

    def _compute(self, bets: list[BacktestBet]) -> BacktestResult:
        res = BacktestResult()
        res.total_bets = len(bets)
        res.bets = [asdict(b) for b in bets]

        flat_curve = [0.0]
        kelly_curve = [0.0]
        flat_running = 0.0
        kelly_running = 0.0
        flat_peak = 0.0
        kelly_peak = 0.0
        flat_dd = 0.0
        kelly_dd = 0.0
        flat_returns = []

        for b in bets:
            if b.result == "won":
                res.won += 1
            elif b.result == "lost":
                res.lost += 1
            else:
                res.void += 1
                continue

            # Flat staking (1 unidad)
            flat_running += b.pnl
            flat_curve.append(flat_running)
            flat_returns.append(b.pnl)
            flat_peak = max(flat_peak, flat_running)
            flat_dd = max(flat_dd, flat_peak - flat_running)

            # Kelly staking
            kelly_stake = max(0.01, min(0.25, b.kelly_fraction))
            kelly_pnl = b.pnl * kelly_stake
            kelly_running += kelly_pnl
            kelly_curve.append(kelly_running)
            kelly_peak = max(kelly_peak, kelly_running)
            kelly_dd = max(kelly_dd, kelly_peak - kelly_running)

        settled = res.won + res.lost
        if settled == 0:
            return res

        res.pnl_flat = round(flat_running, 2)
        res.pnl_kelly = round(kelly_running, 4)
        res.roi_flat = round(flat_running / settled * 100, 2)
        res.roi_kelly = round(kelly_running / settled * 100, 2)
        res.hit_rate = round(res.won / settled, 3)
        res.avg_value = round(sum(b.value for b in bets) / len(bets), 4)
        res.avg_odds = round(sum(b.odds for b in bets) / len(bets), 2)
        res.max_drawdown = round(flat_dd, 2)

        # Sharpe ratio (anualizado si hay suficientes datos)
        if len(flat_returns) >= 5:
            avg_r = flat_running / settled
            std_r = math.sqrt(sum((r - avg_r) ** 2 for r in flat_returns) / len(flat_returns))
            res.sharpe = round(avg_r / std_r * math.sqrt(365) if std_r > 0 else 0, 2)

        # Por mercado
        for b in bets:
            if b.result == "void":
                continue
            m = b.market
            res.by_market.setdefault(m, {"won": 0, "lost": 0, "pnl": 0.0, "bets": 0})
            res.by_market[m]["bets"] += 1
            res.by_market[m]["pnl"] = round(res.by_market[m]["pnl"] + b.pnl, 2)
            if b.result == "won":
                res.by_market[m]["won"] += 1
            else:
                res.by_market[m]["lost"] += 1

        for m, d in res.by_market.items():
            s = d["won"] + d["lost"]
            d["hit_rate"] = round(d["won"] / s, 3) if s > 0 else 0
            d["roi"] = round(d["pnl"] / s * 100, 1) if s > 0 else 0

        # Por liga
        for b in bets:
            if b.result == "void":
                continue
            lg = b.league
            res.by_league.setdefault(lg, {"won": 0, "lost": 0, "pnl": 0.0, "bets": 0})
            res.by_league[lg]["bets"] += 1
            res.by_league[lg]["pnl"] = round(res.by_league[lg]["pnl"] + b.pnl, 2)
            if b.result == "won":
                res.by_league[lg]["won"] += 1
            else:
                res.by_league[lg]["lost"] += 1

        for lg, d in res.by_league.items():
            s = d["won"] + d["lost"]
            d["hit_rate"] = round(d["won"] / s, 3) if s > 0 else 0
            d["roi"] = round(d["pnl"] / s * 100, 1) if s > 0 else 0

        # Por mes
        for b in bets:
            if b.result == "void" or not b.date:
                continue
            month = b.date[:7]
            res.monthly.setdefault(month, {"pnl": 0.0, "bets": 0, "won": 0})
            res.monthly[month]["bets"] += 1
            res.monthly[month]["pnl"] = round(res.monthly[month]["pnl"] + b.pnl, 2)
            if b.result == "won":
                res.monthly[month]["won"] += 1

        return res

    def format_summary(self, res: BacktestResult) -> str:
        if res.total_bets == 0:
            return "📊 Sin datos históricos suficientes para backtesting."

        pnl_emoji = "📈" if res.pnl_flat >= 0 else "📉"
        lines = [
            "<b>📊 Backtesting — Resumen histórico</b>",
            f"{'─' * 34}",
            f"Apuestas analizadas: <b>{res.total_bets}</b> ({res.won}✅ {res.lost}❌)",
            f"Hit rate: <b>{res.hit_rate:.1%}</b>  |  Cuota media: {res.avg_odds:.2f}",
            f"Valor medio: +{res.avg_value:.1%}",
            f"",
            f"{pnl_emoji} <b>Flat (1u):</b> {res.pnl_flat:+.2f}u | ROI: {res.roi_flat:+.1f}%",
            f"📐 <b>Kelly (×0.25):</b> {res.pnl_kelly:+.4f}u | ROI: {res.roi_kelly:+.1f}%",
            f"📉 Max drawdown: {res.max_drawdown:.2f}u  |  Sharpe: {res.sharpe:.2f}",
        ]

        if res.by_market:
            lines.append("\n<b>Por mercado:</b>")
            for m, d in sorted(res.by_market.items(), key=lambda x: x[1]["roi"], reverse=True):
                lines.append(f"  {m}: {d['bets']} apuestas | HR {d['hit_rate']:.0%} | ROI {d['roi']:+.1f}%")

        if res.by_league:
            lines.append("\n<b>Por liga (top 5):</b>")
            top = sorted(res.by_league.items(), key=lambda x: x[1]["roi"], reverse=True)[:5]
            for lg, d in top:
                lines.append(f"  {lg[:20]}: {d['bets']} ap. | ROI {d['roi']:+.1f}%")

        lines.append("\n⚠️ <i>Resultados pasados no garantizan rendimiento futuro.</i>")
        return "\n".join(lines)
