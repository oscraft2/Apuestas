"""
Análisis centralizado — se ejecuta solo desde el scheduler (N veces al día).
No debe llamarse desde /hoy para no duplicar carga en APIs y CPU.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from src.engine import FootballAnalyzerV3
from src.analysis.cycle_store import persist_cycle_snapshot
from src.data.football_api import get_global_upcoming_fixtures, get_standings, get_team_stats, get_upcoming_fixtures, parse_team_stats
from src.data.odds_api import get_odds_for_league, get_upcoming_soccer_odds
from src.ml.trainer import XGBoostModel
from src.tracking.tracker import PredictionTracker
from config import DEFAULT_TARGET_LEAGUES, config, using_custom_target_leagues
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
        outcome = max(probs_1x2, key=lambda key: probs_1x2.get(key, 0))
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
        outcome = max(probs, key=lambda key: probs.get(key, 0))
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
    if r.get("official_pick"):
        official = dict(r.get("official_pick") or {})
        official["confidence"] = _market_confidence(r, official)
        official.setdefault("source", "statistical")
        return official
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


def _rows_for_tracker_logging(highlights: list, leaders: list) -> list[dict]:
    """
    Una fila por partido: prioriza el objeto enriquecido de líderes (official_pick)
    pero incluye todo el radar de destacados para que el resumen diario no-Prime
    vuelva a contar sugerencias completas, no solo Prime.
    """
    by_mid: dict = {}
    for h in highlights or []:
        mid = h.get("match_id")
        if mid:
            by_mid[mid] = h
    for leader in leaders or []:
        mid = leader.get("match_id")
        if mid:
            by_mid[mid] = leader
    return list(by_mid.values())


def _supplement_with_fixtures(all_results: list, league_ids: list) -> None:
    """
    Agrega fixtures de Football API para ligas que no tienen partidos en all_results.
    Permite que la tabla muestre todos los partidos aunque no haya cuotas activas.
    """
    if not config.football_api_key:
        return
    seen_ids = {str(r.get("match_id", "")) for r in all_results}
    leagues_with_data = {r.get("league_id") for r in all_results if r.get("league_id")}

    for league_id in league_ids:
        # Solo suplementar ligas sin datos de odds
        if league_id in leagues_with_data:
            continue
        try:
            fixtures = get_upcoming_fixtures(league_id, days_ahead=7)
            meta = league_meta(league_id)
            for fix in fixtures:
                f = fix.get("fixture", {})
                teams = fix.get("teams", {})
                league_info = fix.get("league", {})
                mid = str(f.get("id", ""))
                if not mid or mid in seen_ids:
                    continue
                seen_ids.add(mid)
                all_results.append({
                    "match_id":     mid,
                    "home":         teams.get("home", {}).get("name", "?"),
                    "away":         teams.get("away", {}).get("name", "?"),
                    "time":         f.get("date", ""),
                    "league":       league_info.get("name", meta["league_name"]),
                    "league_id":    league_id,
                    "league_display": meta["display_full"],
                    "country_name": meta["country_name"],
                    "country_code": meta["country_code"],
                    "flag":         meta["flag"],
                    "has_value":    False,
                    "value_bets":   [],
                    "fixture_only": True,
                })
        except Exception as e:
            logger.debug("Fixture supplement liga %s: %s", league_id, e)


def _inject_global_upcoming_odds(all_results: list) -> None:
    """Último recurso: poblar el radar con upcoming odds globales de fútbol."""
    seen_ids = {str(r.get("match_id", "")) for r in all_results}
    try:
        upcoming = get_upcoming_soccer_odds()
    except Exception as e:
        logger.warning("Fallback upcoming odds global falló: %s", e)
        return

    for match in upcoming:
        match_id = str(match.get("id") or "")
        if not match_id or match_id in seen_ids:
            continue
        seen_ids.add(match_id)
        all_results.append({
            "match_id": match_id,
            "home": match.get("home_team", "?"),
            "away": match.get("away_team", "?"),
            "time": match.get("commence_time", ""),
            "league": match.get("sport_title", "Cobertura Odds"),
            "league_id": match.get("league_id"),
            "has_value": False,
            "value_bets": [],
            "fixture_only": True,
        })


def _inject_global_football_fixtures(all_results: list) -> None:
    """Último recurso final: próximos fixtures globales de API-Football."""
    seen_ids = {str(r.get("match_id", "")) for r in all_results}
    try:
        fixtures = get_global_upcoming_fixtures()
    except Exception as e:
        logger.warning("Fallback global fixtures API-Football falló: %s", e)
        return

    for fix in fixtures:
        fixture = fix.get("fixture", {})
        teams = fix.get("teams", {})
        league_info = fix.get("league", {})
        match_id = str(fixture.get("id") or "")
        if not match_id or match_id in seen_ids:
            continue
        seen_ids.add(match_id)
        all_results.append({
            "match_id": match_id,
            "home": teams.get("home", {}).get("name", "?"),
            "away": teams.get("away", {}).get("name", "?"),
            "time": fixture.get("date", ""),
            "league": league_info.get("name", "Cobertura global"),
            "league_id": league_info.get("id"),
            "has_value": False,
            "value_bets": [],
            "fixture_only": True,
        })


async def analyze_league_full(league_id: int) -> list:
    analyzer = get_analyzer()
    standings = get_standings(league_id)
    if standings:
        analyzer.elo.load_from_standings(standings)
    odds_data = get_odds_for_league(league_id)
    fixture_mode = False
    if not odds_data:
        fixture_mode = True
        odds_data = []
        for fix in get_upcoming_fixtures(league_id, days_ahead=10):
            teams = fix.get("teams", {})
            fixture = fix.get("fixture", {})
            league = fix.get("league", {})
            home_team = teams.get("home", {})
            away_team = teams.get("away", {})
            odds_data.append({
                "id": fixture.get("id"),
                "home_team": home_team.get("name", "?"),
                "away_team": away_team.get("name", "?"),
                "commence_time": fixture.get("date", ""),
                "sport_title": league.get("name", LEAGUES_DISPLAY.get(league_id, str(league_id))),
                "bookmakers": [],
                "home_team_id": home_team.get("id"),
                "away_team_id": away_team.get("id"),
                "fixture_only": True,
            })
    results = []
    for match in odds_data:
        try:
            home_stats = None
            away_stats = None
            if fixture_mode:
                home_team_id = match.get("home_team_id")
                away_team_id = match.get("away_team_id")
                if home_team_id:
                    home_stats = parse_team_stats(get_team_stats(home_team_id, league_id) or {})
                if away_team_id:
                    away_stats = parse_team_stats(get_team_stats(away_team_id, league_id) or {})
            result = await analyzer.analyze(match, home_stats=home_stats, away_stats=away_stats, league_id=league_id)
            result["league_id"] = league_id
            if fixture_mode:
                result["fixture_only"] = True
                result["analysis_mode"] = "statistical"
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
    async def _collect_results(league_ids: list[int]) -> tuple[list, list]:
        batch_results: list = []
        batch_leagues_done: list = []
        for league_id in league_ids:
            try:
                batch = await analyze_league_full(league_id)
                batch_results.extend(batch)
                batch_leagues_done.append(LEAGUES_DISPLAY.get(league_id, str(league_id)))
            except Exception as e:
                logger.error("Central runner liga %s: %s", league_id, e)
        _supplement_with_fixtures(batch_results, league_ids)
        return batch_results, batch_leagues_done

    league_ids = list(config.target_leagues)
    all_results, leagues_done = await _collect_results(league_ids)

    if not all_results and using_custom_target_leagues():
        fallback_leagues = [lid for lid in DEFAULT_TARGET_LEAGUES if lid not in league_ids]
        if fallback_leagues:
            logger.warning(
                "Análisis vacío con TARGET_LEAGUES personalizado; reintentando con ligas por defecto"
            )
            fallback_results, fallback_done = await _collect_results(fallback_leagues)
            if fallback_results:
                all_results = fallback_results
                leagues_done = fallback_done

    if not all_results:
        logger.warning("Sin datos por ligas objetivo; usando fallback global de upcoming odds")
        _inject_global_upcoming_odds(all_results)

    if not all_results:
        logger.warning("Sin datos en Odds API; usando fallback global de fixtures API-Football")
        _inject_global_football_fixtures(all_results)

    highlights = pick_highlights(all_results)
    leaders = build_leader_picks(highlights or all_results)
    mixes = build_power_mix(leaders)
    analysis_date = datetime.now(timezone.utc).date().isoformat()
    for row in _rows_for_tracker_logging(highlights, leaders):
        official = row.get("official_pick") or _official_pick(row)
        if not official:
            continue
        _tracker.log_prediction({
            "match_id": row.get("match_id"),
            "home": row.get("home"),
            "away": row.get("away"),
            "league": row.get("league"),
            "league_id": row.get("league_id"),
            "time": row.get("time"),
            "date": analysis_date,
            "consensus_1x2": (row.get("consensus_1x2") or {}).get("probs", {}),
            "consensus_ou": (row.get("consensus_ou") or {}).get("probs", {}),
            "consensus_ou15": (row.get("consensus_ou15") or {}).get("probs", {}),
            "consensus_btts": (row.get("consensus_btts") or {}).get("probs", {}),
            "official_pick": dict(official),
            "value_bets": list(row.get("value_bets") or []),
        })
    _tracker.tag_cycle(analysis_date, highlights, leaders)
    persist_cycle_snapshot(
        analysis_date=analysis_date,
        results=all_results,
        highlights=highlights,
        leaders=leaders,
        mixes=mixes,
        leagues_done=leagues_done,
    )
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
