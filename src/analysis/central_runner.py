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
from src.tracking.tracker import PredictionTracker
from config import config
from src.league_labels import LEAGUES_DISPLAY, league_meta

logger = logging.getLogger(__name__)

_analyzer: FootballAnalyzerV3 | None = None
_xgb = XGBoostModel()
_tracker = PredictionTracker()


def get_analyzer() -> FootballAnalyzerV3:
    global _analyzer
    if _analyzer is None:
        _analyzer = FootballAnalyzerV3()
    return _analyzer


def _market_confidence(r: dict, pick: dict | None = None) -> float:
    market = (pick or {}).get("market")
    if market == "1X2":
        return float((r.get("consensus_1x2") or {}).get("confidence") or 0)
    if market == "O/U 2.5":
        return float((r.get("consensus_ou") or {}).get("confidence") or 0)
    if market == "O/U 1.5":
        return float((r.get("consensus_ou15") or {}).get("confidence") or 0)
    if market == "BTTS":
        return float((r.get("consensus_btts") or {}).get("confidence") or 0)
    return float((r.get("consensus_1x2") or {}).get("confidence") or 0)


def _pick_market_bias(r: dict, pick: dict | None = None) -> float:
    if not pick:
        return 1.0
    bias_map = league_meta(r.get("league_id") or -1).get("market_bias", {})
    key = f"{pick.get('market')}:{pick.get('outcome')}"
    return float(bias_map.get(key) or 1.0)


def _fallback_pick(r: dict) -> dict | None:
    options = []
    market_data = r.get("market") or {}
    h2h_market = market_data.get("h2h") or {}
    ou25_market = market_data.get("ou25") or market_data.get("ou") or {}
    ou15_market = market_data.get("ou15") or {}
    btts_market = market_data.get("btts") or {}
    c1 = r.get("consensus_1x2") or {}
    probs_1x2 = c1.get("probs") or {}
    if probs_1x2:
        outcome = max(probs_1x2, key=probs_1x2.get)
        options.append({
            "market": "1X2",
            "outcome": outcome,
            "label": {"home": "Gana local", "draw": "Empate", "away": "Gana visita"}.get(outcome, outcome),
            "prob": float(probs_1x2.get(outcome) or 0),
            "odds": (h2h_market.get("best_odds") or {}).get(outcome) or (c1.get("fair_odds") or {}).get(outcome),
            "value": 0.0,
            "kelly": 0.0,
            "source": "consensus",
        })

    for consensus_key, market_label, labels in [
        ("consensus_ou", "O/U 2.5", {"over": "Over 2.5", "under": "Under 2.5"}),
        ("consensus_ou15", "O/U 1.5", {"over": "Over 1.5", "under": "Under 1.5"}),
        ("consensus_btts", "BTTS", {"yes": "Ambos marcan", "no": "No marcan ambos"}),
    ]:
        consensus = r.get(consensus_key) or {}
        probs = consensus.get("probs") or {}
        if not probs:
            continue
        outcome = max(probs, key=probs.get)
        best_odds = (consensus.get("fair_odds") or {}).get(outcome)
        if market_label == "O/U 2.5":
            best_odds = ou25_market.get("best_over") if outcome == "over" else ou25_market.get("best_under")
        elif market_label == "O/U 1.5":
            best_odds = ou15_market.get("best_over") if outcome == "over" else ou15_market.get("best_under")
        elif market_label == "BTTS":
            best_odds = btts_market.get("best_yes") if outcome == "yes" else btts_market.get("best_no")
        options.append({
            "market": market_label,
            "outcome": outcome,
            "label": labels.get(outcome, outcome),
            "prob": float(probs.get(outcome) or 0),
            "odds": best_odds or (consensus.get("fair_odds") or {}).get(outcome),
            "value": 0.0,
            "kelly": 0.0,
            "source": "consensus",
        })

    if not options:
        return None
    return max(options, key=lambda item: float(item.get("prob") or 0))


def _official_pick(r: dict) -> dict | None:
    picks = r.get("value_bets") or []
    if not picks:
        fallback = _fallback_pick(r)
        if not fallback:
            return None
        fallback["confidence"] = _market_confidence(r, fallback)
        return fallback
    official = dict(picks[0])
    official["confidence"] = _market_confidence(r, official)
    official["source"] = "value"
    return official


def interest_score(r: dict) -> float:
    """Puntuación editorial para ordenar partidos llamativos (valor + consenso + fit de liga)."""
    official_pick = _official_pick(r)
    mv = float(r.get("max_value") or 0)
    conf = _market_confidence(r, official_pick)
    c1 = r.get("consensus_1x2") or {}
    agree = max(
        float(c1.get("agreement") or 0),
        float((r.get("consensus_ou") or {}).get("agreement") or 0),
        float((r.get("consensus_ou15") or {}).get("agreement") or 0),
        float((r.get("consensus_btts") or {}).get("agreement") or 0),
    )
    nvb = len(r.get("value_bets") or [])
    bonus = 0.15 if r.get("has_value") else 0.0
    hero = 0.12 if r.get("league_id") == config.hero_league_id else 0.0
    fit = (_pick_market_bias(r, official_pick) - 1.0) * 1.5
    return mv * 12.0 + conf * 2.6 + agree * 0.4 + min(nvb, 4) * 0.03 + bonus + hero + fit


def leader_score(r: dict) -> float:
    official_pick = _official_pick(r)
    if not official_pick:
        return -1.0
    conf = _market_confidence(r, official_pick)
    agree = max(
        float((r.get("consensus_1x2") or {}).get("agreement") or 0),
        float((r.get("consensus_ou") or {}).get("agreement") or 0),
        float((r.get("consensus_ou15") or {}).get("agreement") or 0),
        float((r.get("consensus_btts") or {}).get("agreement") or 0),
    )
    value = float(official_pick.get("value") or 0)
    kelly = float(official_pick.get("kelly") or 0)
    fit = _pick_market_bias(r, official_pick)
    hero = 0.18 if r.get("league_id") == config.hero_league_id else 0.0
    multi = 0.05 if len(r.get("value_bets") or []) > 1 else 0.0
    return value * 14.0 + conf * 3.2 + agree * 0.6 + kelly * 6.0 + (fit - 1.0) * 4.0 + hero + multi


def pick_highlights(results: list, top_n: int | None = None) -> list:
    if not results:
        return []
    n = top_n if top_n is not None else getattr(config, "highlight_top_n", 15)
    ranked = []
    for item in results:
        enriched = dict(item)
        enriched["interest_score"] = round(interest_score(item), 4)
        ranked.append(enriched)
    ranked.sort(key=lambda item: item.get("interest_score", 0), reverse=True)
    return ranked[:n]


def build_leader_picks(results: list, top_n: int | None = None) -> list:
    if not results:
        return []
    n = top_n if top_n is not None else getattr(config, "leader_top_n", 5)
    candidates = []
    for item in results:
        official = _official_pick(item)
        enriched = dict(item)
        enriched["official_pick"] = official
        enriched["interest_score"] = round(enriched.get("interest_score", interest_score(item)), 4)
        enriched["leader_score"] = round(leader_score(item), 4)
        if official:
            candidates.append(enriched)
    candidates.sort(key=lambda item: item.get("leader_score", 0), reverse=True)
    leaders = []
    for idx, item in enumerate(candidates[:n], start=1):
        leader = dict(item)
        leader["leader_rank"] = idx
        leader["leader_name"] = f"ValueX Prime #{idx}"
        leaders.append(leader)
    return leaders


def build_power_mix(leaders: list, max_legs: int | None = None) -> list:
    if not leaders:
        return []
    legs_limit = max_legs if max_legs is not None else getattr(config, "leader_mix_legs", 3)
    eligible = []
    seen_matches = set()
    for leader in leaders:
        official = leader.get("official_pick") or _official_pick(leader)
        if not official:
            continue
        match_id = leader.get("match_id")
        if match_id in seen_matches:
            continue
        seen_matches.add(match_id)
        eligible.append((leader, official))
    if len(eligible) < 2:
        return []

    mixes = []
    for leg_count in range(2, min(len(eligible), legs_limit) + 1):
        legs = eligible[:leg_count]
        combined_odds = 1.0
        combined_prob = 1.0
        combined_value = 0.0
        mix_legs = []
        for leader, official in legs:
            odds = float(official.get("odds") or official.get("best_odds") or 1)
            prob = float(official.get("prob") or 0)
            value = float(official.get("value") or 0)
            combined_odds *= odds
            combined_prob *= prob
            combined_value += value
            mix_legs.append({
                "match_id": leader.get("match_id"),
                "home": leader.get("home"),
                "away": leader.get("away"),
                "market": official.get("market"),
                "selection": official.get("label") or official.get("outcome"),
                "odds": round(odds, 2),
                "probability": round(prob, 4),
                "value": round(value, 4),
                "leader_rank": leader.get("leader_rank"),
            })

        mixes.append({
            "name": f"ValueX PowerMix {leg_count}",
            "label": "PowerMix",
            "legs_count": leg_count,
            "legs": mix_legs,
            "combined_odds": round(combined_odds, 2),
            "combined_probability": round(combined_prob, 4),
            "combined_value": round((combined_prob * combined_odds) - 1, 4),
            "sum_value": round(combined_value, 4),
            "risk_label": "alta" if leg_count >= 3 else "media",
        })
    return mixes


async def analyze_league_full(league_id: int) -> list:
    analyzer = get_analyzer()
    standings = get_standings(league_id)
    if standings:
        analyzer.elo.load_from_standings(standings)
    odds_data = get_odds_for_league(league_id)
    results = []
    for match in odds_data:
        try:
            result = await analyzer.analyze(match, league_id=league_id)
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
    leaders = build_leader_picks(highlights or all_results)
    mixes = build_power_mix(leaders)
    analysis_date = datetime.now(timezone.utc).date().isoformat()
    for leader in leaders:
        _tracker.log_prediction({
            "match_id": leader.get("match_id"),
            "home": leader.get("home"),
            "away": leader.get("away"),
            "league": leader.get("league"),
            "league_id": leader.get("league_id"),
            "time": leader.get("time"),
            "date": analysis_date,
            "consensus_1x2": (leader.get("consensus_1x2") or {}).get("probs", {}),
            "consensus_ou": (leader.get("consensus_ou") or {}).get("probs", {}),
            "consensus_ou15": (leader.get("consensus_ou15") or {}).get("probs", {}),
            "consensus_btts": (leader.get("consensus_btts") or {}).get("probs", {}),
            "official_pick": dict(leader.get("official_pick") or {}),
            "value_bets": list(leader.get("value_bets") or []),
        })
    _tracker.tag_cycle(analysis_date, highlights, leaders)
    return {
        "results": all_results,
        "highlights": highlights,
        "leaders": leaders,
        "mixes": mixes,
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
