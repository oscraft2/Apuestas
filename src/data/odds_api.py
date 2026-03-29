"""
Client for The Odds API (the-odds-api.com)
Free tier: 500 requests/month — llamar bajo demanda, no cachear muy poco tiempo.
"""
import requests
from typing import Optional
from config import config
from src.data.cache_manager import CacheManager

BASE_URL = "https://api.the-odds-api.com/v4"
# Cache de 2h para cuotas (más fresco que datos de equipo)
cache = CacheManager(config.cache_dir, ttl_hours=2)


def _get(endpoint: str, params: dict) -> Optional[dict]:
    cache_key = f"odds_{endpoint}_{sorted(params.items())}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    params["apiKey"] = config.odds_api_key
    resp = requests.get(f"{BASE_URL}/{endpoint}", params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    cache.set(cache_key, data)
    return data


def get_odds(sport_key: str = "soccer_epl", markets: str = "h2h,totals") -> list:
    """
    Cuotas de 1X2 (h2h) y Over/Under (totals) para un deporte/liga.
    sport_key ejemplos: soccer_epl, soccer_spain_la_liga, soccer_italy_serie_a
    """
    data = _get(f"sports/{sport_key}/odds", {
        "regions": config.odds_regions,
        "markets": markets,
        "oddsFormat": "decimal",
    })
    return data if isinstance(data, list) else []


def get_sports() -> list:
    """Lista de deportes/ligas disponibles."""
    data = _get("sports", {"all": "true"})
    return data if isinstance(data, list) else []


# Mapeo de league_id (API-Football) → sport_key (The Odds API)
LEAGUE_TO_SPORT_KEY = {
    39:  "soccer_epl",
    140: "soccer_spain_la_liga",
    135: "soccer_italy_serie_a",
    78:  "soccer_germany_bundesliga",
    61:  "soccer_france_ligue_one",
    2:   "soccer_uefa_champs_league",
    3:   "soccer_uefa_europa_league",
}


def get_odds_for_league(league_id: int) -> list:
    sport_key = LEAGUE_TO_SPORT_KEY.get(league_id)
    if not sport_key:
        return []
    return get_odds(sport_key)
