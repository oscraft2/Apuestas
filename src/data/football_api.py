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


def _get(endpoint: str, params: dict) -> Optional[dict]:
    # Bug #15: usar json.dumps para cache key estable y segura
    cache_key = f"football_{endpoint}_{json.dumps(sorted(params.items()))}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    headers = {"x-apisports-key": config.football_api_key}
    try:
        resp = requests.get(f"{BASE_URL}/{endpoint}", headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        cache.set(cache_key, data)
        return data
    except requests.exceptions.HTTPError as e:
        logger.error(f"API-Football HTTP error {endpoint}: {e}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"API-Football request error {endpoint}: {e}")
        return None


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
    data = _get("fixtures", {
        "league": league_id,
        "season": config.season,
        "from": today.isoformat(),
        "to": end.isoformat(),
    })
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
