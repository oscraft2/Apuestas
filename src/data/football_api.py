"""
Client for API-Football (api-football.com)
Free tier: 100 requests/day
"""
import requests
from typing import Optional
from config import config
from src.data.cache_manager import CacheManager

BASE_URL = "https://v3.football.api-sports.io"
cache = CacheManager(config.cache_dir, config.cache_ttl_hours)


def _get(endpoint: str, params: dict) -> Optional[dict]:
    cache_key = f"football_{endpoint}_{sorted(params.items())}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    headers = {
        "x-apisports-key": config.football_api_key,
    }
    resp = requests.get(f"{BASE_URL}/{endpoint}", headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    cache.set(cache_key, data)
    return data


def get_fixtures_today(league_id: int) -> list:
    """Partidos de hoy para una liga dada."""
    from datetime import date
    today = date.today().isoformat()
    data = _get("fixtures", {"league": league_id, "season": config.season, "date": today})
    return data.get("response", []) if data else []


def get_standings(league_id: int) -> list:
    """Clasificación actual de la liga."""
    data = _get("standings", {"league": league_id, "season": config.season})
    if not data or not data.get("response"):
        return []
    standings = data["response"][0].get("league", {}).get("standings", [])
    return standings[0] if standings else []


def get_team_stats(team_id: int, league_id: int) -> Optional[dict]:
    """Estadísticas del equipo en la liga (goles, xG, forma)."""
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
