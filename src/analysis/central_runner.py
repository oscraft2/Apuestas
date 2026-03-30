"""
Análisis centralizado — se ejecuta solo desde el scheduler (N veces al día).
No debe llamarse desde /hoy para no duplicar carga en APIs y CPU.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from src.engine import FootballAnalyzerV3
from src.data.football_api import get_standings
from src.data.odds_api import get_odds_for_league
from src.ml.trainer import XGBoostModel
from config import config
from src.league_labels import LEAGUES_DISPLAY

logger = logging.getLogger(__name__)

_analyzer: FootballAnalyzerV3 | None = None
_xgb = XGBoostModel()


def get_analyzer() -> FootballAnalyzerV3:
    global _analyzer
    if _analyzer is None:
        _analyzer = FootballAnalyzerV3()
    return _analyzer


def interest_score(r: dict) -> float:
    """Puntuación para ordenar partidos 'llamativos' (valor + consenso)."""
    mv = float(r.get("max_value") or 0)
    c1 = r.get("consensus_1x2") or {}
    conf = float(c1.get("confidence") or 0)
    agree = float(c1.get("agreement") or 0)
    nvb = len(r.get("value_bets") or [])
    bonus = 0.15 if r.get("has_value") else 0.0
    hero = 0.12 if r.get("league_id") == config.hero_league_id else 0.0
    return mv * 12.0 + conf * 2.5 + agree * 0.4 + min(nvb, 4) * 0.03 + bonus + hero


def pick_highlights(results: list, top_n: int | None = None) -> list:
    if not results:
        return []
    n = top_n if top_n is not None else getattr(config, "highlight_top_n", 15)
    ranked = sorted(results, key=interest_score, reverse=True)
    return ranked[:n]


async def analyze_league_full(league_id: int) -> list:
    analyzer = get_analyzer()
    standings = get_standings(league_id)
    if standings:
        analyzer.elo.load_from_standings(standings)
    odds_data = get_odds_for_league(league_id)
    results = []
    for match in odds_data:
        try:
            result = await analyzer.analyze(match)
            result["league_id"] = league_id
            if _xgb.is_available and result.get("has_value"):
                xgb_prob = _xgb.predict_proba(result)
                if xgb_prob is not None:
                    result["xgb_win_prob"] = xgb_prob
            results.append(result)
        except Exception as e:
            logger.warning("Error analizando %s: %s", match.get("home_team", "?"), e)
    results.sort(key=lambda x: x.get("max_value", 0), reverse=True)
    return results


async def run_full_analysis() -> dict:
    """
    Recorre todas las ligas configuradas, actualiza ELO por liga y devuelve
    resultados completos + lista de destacados (más llamativos).
    """
    all_results: list = []
    leagues_done: list = []
    league_ids = list(config.target_leagues)

    for league_id in league_ids:
        try:
            batch = await analyze_league_full(league_id)
            all_results.extend(batch)
            leagues_done.append(LEAGUES_DISPLAY.get(league_id, str(league_id)))
        except Exception as e:
            logger.error("Central runner liga %s: %s", league_id, e)

    highlights = pick_highlights(all_results)
    return {
        "results": all_results,
        "highlights": highlights,
        "leagues_done": leagues_done,
    }


def next_run_utc() -> datetime | None:
    """Próxima ejecución programada según report_hours_utc."""
    hours = sorted(set(getattr(config, "report_hours_utc", [8, 15, 22])))
    if not hours:
        return None
    now = datetime.now(timezone.utc)
    candidates: list[datetime] = []
    for offset in range(0, 4):
        base = now.date() + timedelta(days=offset)
        for h in hours:
            t = datetime(base.year, base.month, base.day, h, 0, 0, tzinfo=timezone.utc)
            if t > now:
                candidates.append(t)
    return min(candidates) if candidates else None


def format_schedule_hint() -> str:
    hrs = ", ".join(f"{h:02d}:00" for h in sorted(set(config.report_hours_utc)))
    nxt = next_run_utc()
    if nxt:
        return (
            f"Horarios UTC: {hrs}\n"
            f"Próximo análisis automático: ~{nxt.strftime('%d/%m %H:%M')} UTC"
        )
    return f"Horarios UTC: {hrs}"
