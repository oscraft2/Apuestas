"""
Client for The Odds API (the-odds-api.com)
Free tier: 500 requests/month — llamar bajo demanda
"""
import json
import logging
import requests
from typing import Optional
from config import config
from src.data.cache_manager import CacheManager

logger = logging.getLogger(__name__)
BASE_URL = "https://api.the-odds-api.com/v4"
cache = CacheManager(config.cache_dir, ttl_hours=2)


def _has_usable_payload(data: object) -> bool:
    if isinstance(data, list):
        return len(data) > 0
    if isinstance(data, dict):
        response = data.get("response")
        if isinstance(response, list):
            return len(response) > 0
        return bool(data)
    return False


def _get(endpoint: str, params: dict) -> Optional[list | dict]:
    # Bug #16: usar json.dumps para cache key estable
    cache_key = f"odds_{endpoint}_{json.dumps(sorted(params.items()))}"
    cached = cache.get(cache_key)
    if cached is not None and _has_usable_payload(cached):
        return cached

    params["apiKey"] = config.odds_api_key
    try:
        resp = requests.get(f"{BASE_URL}/{endpoint}", params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if _has_usable_payload(data):
            cache.set(cache_key, data)
        return data
    except requests.exceptions.HTTPError as e:
        logger.error(f"Odds API HTTP error {endpoint}: {e}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Odds API request error {endpoint}: {e}")
        return None


def probe_endpoint(endpoint: str, params: dict) -> dict:
    """Probe directo sin caché para diagnóstico operativo."""
    if not config.odds_api_key:
        return {"ok": False, "status_code": None, "count": 0, "error": "no_key"}
    req_params = dict(params or {})
    req_params["apiKey"] = config.odds_api_key
    try:
        resp = requests.get(f"{BASE_URL}/{endpoint}", params=req_params, timeout=15)
        status_code = resp.status_code
        try:
            data = resp.json()
        except ValueError:
            data = None
        if isinstance(data, list):
            count = len(data)
        elif isinstance(data, dict) and isinstance(data.get("response"), list):
            count = len(data.get("response") or [])
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


def get_odds(sport_key: str = "soccer_epl", markets: str = "h2h,totals,btts") -> list:
    """
    Cuotas de 1X2 (h2h), totales y BTTS para un deporte/liga.
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


# Mapeo de league_id (API-Football) → sport_key (The Odds API v4).
# Si añades un ID en TARGET_LEAGUES, debe existir aquí o no habrá cuotas.
# Lista oficial: GET https://api.the-odds-api.com/v4/sports?apiKey=…
# IDs FIFA/UEFA/CONMEBOL: confirma en dashboard.api-football.com/soccer/ids si una competición cambia de ID.
LEAGUE_TO_SPORT_KEY = {
    # Top 5 Europa
    39:  "soccer_epl",
    140: "soccer_spain_la_liga",
    135: "soccer_italy_serie_a",
    78:  "soccer_germany_bundesliga",
    61:  "soccer_france_ligue_one",
    # Copas UEFA (The Odds API — ver /v4/sports si una clave cambia de temporada)
    2:   "soccer_uefa_champs_league",
    3:   "soccer_uefa_europa_league",
    848: "soccer_uefa_europa_conference_league",
    # Selecciones internacionales (API-Football league id → sport_key Odds API)
    1:    "soccer_fifa_world_cup",
    4:    "soccer_uefa_european_championship",
    5:    "soccer_fifa_world_cup_qualification_uefa",
    9:    "soccer_conmebol_copa_america",
    10:   "soccer_international_friendly",
    16:   "soccer_fifa_world_cup_qualification_south_america",
    1073: "soccer_uefa_nations_league",
    # CONMEBOL clubes
    13:  "soccer_conmebol_copa_libertadores",
    11:  "soccer_conmebol_copa_sudamericana",
    # Américas
    265: "soccer_chile_primera_division",
    71:  "soccer_brazil_campeonato",
    262: "soccer_mexico_ligamx",
    253: "soccer_usa_mls",
    128: "soccer_argentina_primera_division",
    239: "soccer_colombia_primera_a",
    281: "soccer_peru_liga_1",
    242: "soccer_ecuador_liga_pro",
    # Europa y otras
    88:  "soccer_netherlands_eredivisie",
    94:  "soccer_portugal_primeira_liga",
    203: "soccer_turkey_super_league",
    307: "soccer_saudi_pro_league",
}

SPORT_KEY_TO_LEAGUE = {sport_key: league_id for league_id, sport_key in LEAGUE_TO_SPORT_KEY.items()}


def get_odds_for_league(league_id: int) -> list:
    sport_key = LEAGUE_TO_SPORT_KEY.get(league_id)
    if not sport_key:
        return []
    requested_markets = list(config.target_markets or ["h2h", "totals"])
    markets = ",".join(requested_markets)
    data = get_odds(sport_key, markets=markets)
    if data:
        return data

    # Fallback: algunas ligas no soportan BTTS/totals en todos los bookies/planes.
    safe_markets = [m for m in requested_markets if m in {"h2h", "totals"}]
    if safe_markets:
        fallback = get_odds(sport_key, markets=",".join(safe_markets))
        if fallback:
            logger.info(
                "Odds fallback OK liga %s (%s): %s",
                league_id,
                sport_key,
                ",".join(safe_markets),
            )
            return fallback

    h2h_only = get_odds(sport_key, markets="h2h")
    if h2h_only:
        logger.info("Odds fallback H2H OK liga %s (%s)", league_id, sport_key)
    return h2h_only


def get_upcoming_soccer_odds(limit: int = 24) -> list:
    """Fallback global: próximos partidos de fútbol con cuotas, sin depender del mapeo liga->sport_key."""
    requested_markets = list(config.target_markets or ["h2h", "totals"])
    data = _get("sports/upcoming/odds", {
        "regions": config.odds_regions,
        "markets": ",".join(requested_markets),
        "oddsFormat": "decimal",
    })
    if not isinstance(data, list):
        return []

    soccer = []
    seen_ids = set()
    for match in data:
        sport_key = str(match.get("sport_key") or "")
        if not sport_key.startswith("soccer_"):
            continue
        if not match.get("home_team") or not match.get("away_team"):
            continue
        match_id = str(match.get("id") or "")
        if not match_id or match_id in seen_ids:
            continue
        seen_ids.add(match_id)
        enriched = dict(match)
        league_id = SPORT_KEY_TO_LEAGUE.get(sport_key)
        if league_id is not None:
            enriched["league_id"] = league_id
        soccer.append(enriched)

    soccer.sort(key=lambda item: str(item.get("commence_time") or ""))
    return soccer[:limit]
