"""
Client for API-Football (api-football.com)
Free tier: 100 requests/day
"""
import json
import logging
import requests
from typing import Optional
from config import config
from src.data.cache_manager import CacheManager

logger = logging.getLogger(__name__)
BASE_URL = "https://v3.football.api-sports.io"
cache = CacheManager(config.cache_dir, config.cache_ttl_hours)


def _has_usable_payload(data: object) -> bool:
    if isinstance(data, dict):
        response = data.get("response")
        if isinstance(response, list):
            return len(response) > 0
        return bool(data)
    if isinstance(data, list):
        return len(data) > 0
    return False


def _get(endpoint: str, params: dict) -> Optional[dict]:
    # Bug #15: usar json.dumps para cache key estable y segura
    cache_key = f"football_{endpoint}_{json.dumps(sorted(params.items()))}"
    cached = cache.get(cache_key)
    if cached is not None and _has_usable_payload(cached):
        return cached

    headers = {"x-apisports-key": config.football_api_key}
    try:
        resp = requests.get(f"{BASE_URL}/{endpoint}", headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if _has_usable_payload(data):
            cache.set(cache_key, data)
        return data
    except requests.exceptions.HTTPError as e:
        logger.error(f"API-Football HTTP error {endpoint}: {e}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"API-Football request error {endpoint}: {e}")
        return None


def probe_endpoint(endpoint: str, params: dict) -> dict:
    """Probe directo sin caché para diagnóstico operativo."""
    if not config.football_api_key:
        return {"ok": False, "status_code": None, "count": 0, "error": "no_key"}
    headers = {"x-apisports-key": config.football_api_key}
    try:
        resp = requests.get(f"{BASE_URL}/{endpoint}", headers=headers, params=params or {}, timeout=15)
        status_code = resp.status_code
        try:
            data = resp.json()
        except ValueError:
            data = None
        if isinstance(data, dict) and isinstance(data.get("response"), list):
            count = len(data.get("response") or [])
        elif isinstance(data, list):
            count = len(data)
        else:
            count = 0
        return {
            "ok": resp.ok,
            "status_code": status_code,
            "count": count,
            "error": None if resp.ok else (str(data)[:300] if data else f"http_{status_code}"),
        }
    except requests.exceptions.RequestException as e:
        return {"ok": False, "status_code": None, "count": 0, "error": type(e).__name__}


def get_current_season_for_league(league_id: int) -> int:
    """Resuelve la temporada actual real de una liga usando /leagues?current=true."""
    data = _get("leagues", {"id": league_id, "current": "true"})
    response = data.get("response", []) if data else []
    for item in response:
        seasons = item.get("seasons", []) or []
        for season in seasons:
            if season.get("current"):
                year = season.get("year")
                if isinstance(year, int):
                    return year
    return int(config.season)


def probe_upcoming_fixtures_for_league(league_id: int, next_count: int = 10) -> dict:
    """Probe directo con temporada dinámica para ver si una liga tiene próximos partidos."""
    from datetime import date, timedelta

    season = get_current_season_for_league(league_id)
    today = date.today()
    end = today + timedelta(days=max(5, next_count))
    probe = probe_endpoint(
        "fixtures",
        {
            "league": league_id,
            "season": season,
            "from": today.isoformat(),
            "to": end.isoformat(),
        },
    )
    probe["season"] = season
    probe["window"] = {"from": today.isoformat(), "to": end.isoformat()}
    return probe


def get_fixtures_today(league_id: int) -> list:
    """Partidos de hoy para una liga dada."""
    from datetime import date
    today = date.today().isoformat()
    data = _get("fixtures", {"league": league_id, "season": config.season, "date": today})
    return data.get("response", []) if data else []


def get_fixtures_by_date(league_id: int, date_str: str) -> list:
    """Partidos de una fecha concreta para una liga dada."""
    data = _get("fixtures", {"league": league_id, "season": config.season, "date": date_str})
    return data.get("response", []) if data else []


def get_upcoming_fixtures(league_id: int, days_ahead: int = 7) -> list:
    """Próximos partidos de una liga en los siguientes N días (para suplementar la tabla)."""
    from datetime import date, timedelta
    if not config.football_api_key:
        return []
    today = date.today()
    end = today + timedelta(days=days_ahead)
    base_params = {
        "league": league_id,
        "from": today.isoformat(),
        "to": end.isoformat(),
    }

    season = get_current_season_for_league(league_id)

    # Primer intento con temporada actual real de la liga.
    data = _get("fixtures", {**base_params, "season": season})
    out = data.get("response", []) if data else []
    if out:
        return out

    # Fallback por desalineación de temporada (ligas que cambian año calendario).
    for fallback_season in (config.season, season + 1, max(2000, season - 1), max(2000, config.season - 1)):
        if fallback_season == season:
            continue
        data = _get("fixtures", {**base_params, "season": fallback_season})
        out = data.get("response", []) if data else []
        if out:
            logger.info("Fixtures fallback OK liga %s con season=%s", league_id, fallback_season)
            return out

    # Último recurso: pedir próximos fixtures por liga sin depender tanto de la temporada.
    next_count = max(5, min(days_ahead * 3, 20))
    for extra_params in (
        {"league": league_id, "season": season, "next": next_count},
        {"league": league_id, "season": config.season, "next": next_count},
        {"league": league_id, "next": next_count},
    ):
        data = _get("fixtures", extra_params)
        out = data.get("response", []) if data else []
        if out:
            logger.info("Fixtures fallback NEXT OK liga %s con params=%s", league_id, extra_params)
            return out
    return []


def get_global_upcoming_fixtures(limit: int = 30) -> list:
    """Próximos partidos globales de fútbol como último recurso para poblar la agenda."""
    if not config.football_api_key:
        return []
    safe_limit = max(10, min(int(limit or 30), 100))
    data = _get("fixtures", {"next": safe_limit})
    return data.get("response", []) if data else []


def get_standings(league_id: int) -> list:
    """Clasificación actual de la liga."""
    data = _get("standings", {"league": league_id, "season": config.season})
    if not data or not data.get("response"):
        return []
    standings = data["response"][0].get("league", {}).get("standings", [])
    return standings[0] if standings else []


def get_team_stats(team_id: int, league_id: int) -> Optional[dict]:
    """Estadísticas del equipo en la liga (goles, forma)."""
    data = _get("teams/statistics", {
        "team": team_id,
        "league": league_id,
        "season": config.season,
    })
    return data.get("response") if data else None


def get_last_matches(team_id: int, n: int = 10) -> list:
    """Últimos N partidos de un equipo."""
    data = _get("fixtures", {
        "team": team_id,
        "last": n,
        "season": config.season,
    })
    return data.get("response", []) if data else []


def get_h2h(team1_id: int, team2_id: int, last: int = 5) -> list:
    """Head-to-head entre dos equipos."""
    data = _get("fixtures/headtohead", {
        "h2h": f"{team1_id}-{team2_id}",
        "last": last,
    })
    return data.get("response", []) if data else []


def get_injuries(fixture_id: int) -> list:
    """Lesiones e indisponibles para un partido."""
    data = _get("injuries", {"fixture": fixture_id})
    return data.get("response", []) if data else []


def parse_team_stats(raw: dict) -> dict:
    """Convierte respuesta de API-Football en dict usable por el engine."""
    if not raw:
        return {}
    goals = raw.get("goals", {})
    gf_total = goals.get("for", {}).get("total", {}).get("total", 0) or 0
    ga_total = goals.get("against", {}).get("total", {}).get("total", 0) or 0
    matches_played = raw.get("fixtures", {}).get("played", {}).get("total", 1) or 1
    form_str = raw.get("form", "") or ""

    return {
        "avg_gf": round(gf_total / matches_played, 2),
        "avg_ga": round(ga_total / matches_played, 2),
        "results": list(form_str[-10:]),  # últimas 10 jornadas como ['W','D','L',...]
        "goals_for": [],
        "goals_against": [],
        "name": raw.get("team", {}).get("name", ""),
    }
