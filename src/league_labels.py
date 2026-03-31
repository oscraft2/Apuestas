"""Etiquetas y metadata de ligas (API-Football) compartidas entre UI, API y bot."""

import unicodedata

LEAGUE_META = {
    265: {
        "league_name": "Primera División Chile",
        "display_name": "Primera Chile",
        "country_name": "Chile",
        "country_code": "CL",
        "flag": "🇨🇱",
        "region": "latam",
    },
    71: {
        "league_name": "Brasileirão Serie A",
        "display_name": "Brasileirão",
        "country_name": "Brasil",
        "country_code": "BR",
        "flag": "🇧🇷",
        "region": "latam",
    },
    262: {
        "league_name": "Liga MX",
        "display_name": "Liga MX",
        "country_name": "México",
        "country_code": "MX",
        "flag": "🇲🇽",
        "region": "latam",
    },
    253: {
        "league_name": "MLS",
        "display_name": "MLS",
        "country_name": "Estados Unidos",
        "country_code": "US",
        "flag": "🇺🇸",
        "region": "north-america",
    },
    128: {
        "league_name": "Liga Profesional Argentina",
        "display_name": "Liga Argentina",
        "country_name": "Argentina",
        "country_code": "AR",
        "flag": "🇦🇷",
        "region": "latam",
    },
    239: {
        "league_name": "Primera A Colombia",
        "display_name": "Primera Colombia",
        "country_name": "Colombia",
        "country_code": "CO",
        "flag": "🇨🇴",
        "region": "latam",
    },
    281: {
        "league_name": "Liga 1 Perú",
        "display_name": "Liga 1",
        "country_name": "Perú",
        "country_code": "PE",
        "flag": "🇵🇪",
        "region": "latam",
    },
    242: {
        "league_name": "Liga Pro Ecuador",
        "display_name": "Liga Pro",
        "country_name": "Ecuador",
        "country_code": "EC",
        "flag": "🇪🇨",
        "region": "latam",
    },
    39: {
        "league_name": "Premier League",
        "display_name": "Premier League",
        "country_name": "Inglaterra",
        "country_code": "GB-ENG",
        "flag": "🏴",
        "region": "europa",
    },
    140: {
        "league_name": "La Liga",
        "display_name": "La Liga",
        "country_name": "España",
        "country_code": "ES",
        "flag": "🇪🇸",
        "region": "europa",
    },
    135: {
        "league_name": "Serie A",
        "display_name": "Serie A",
        "country_name": "Italia",
        "country_code": "IT",
        "flag": "🇮🇹",
        "region": "europa",
    },
    78: {
        "league_name": "Bundesliga",
        "display_name": "Bundesliga",
        "country_name": "Alemania",
        "country_code": "DE",
        "flag": "🇩🇪",
        "region": "europa",
    },
    61: {
        "league_name": "Ligue 1",
        "display_name": "Ligue 1",
        "country_name": "Francia",
        "country_code": "FR",
        "flag": "🇫🇷",
        "region": "europa",
    },
    2: {
        "league_name": "Champions League",
        "display_name": "Champions League",
        "country_name": "Europa",
        "country_code": "EU",
        "flag": "🏆",
        "region": "continental",
    },
    3: {
        "league_name": "Europa League",
        "display_name": "Europa League",
        "country_name": "Europa",
        "country_code": "EU",
        "flag": "🏆",
        "region": "continental",
    },
    848: {
        "league_name": "UEFA Conference League",
        "display_name": "Conference League",
        "country_name": "Europa",
        "country_code": "EU",
        "flag": "🏆",
        "region": "continental",
    },
    13: {
        "league_name": "Copa Libertadores",
        "display_name": "Libertadores",
        "country_name": "CONMEBOL",
        "country_code": "SAM",
        "flag": "🌎",
        "region": "continental",
    },
    11: {
        "league_name": "Copa Sudamericana",
        "display_name": "Sudamericana",
        "country_name": "CONMEBOL",
        "country_code": "SAM",
        "flag": "🌎",
        "region": "continental",
    },
    94: {
        "league_name": "Primeira Liga",
        "display_name": "Primeira Liga",
        "country_name": "Portugal",
        "country_code": "PT",
        "flag": "🇵🇹",
        "region": "europa",
    },
    88: {
        "league_name": "Eredivisie",
        "display_name": "Eredivisie",
        "country_name": "Países Bajos",
        "country_code": "NL",
        "flag": "🇳🇱",
        "region": "europa",
    },
    203: {
        "league_name": "Super Lig",
        "display_name": "Süper Lig",
        "country_name": "Turquía",
        "country_code": "TR",
        "flag": "🇹🇷",
        "region": "europa",
    },
    307: {
        "league_name": "Saudi Pro League",
        "display_name": "Saudi Pro League",
        "country_name": "Arabia Saudita",
        "country_code": "SA",
        "flag": "🇸🇦",
        "region": "middle-east",
    },
}

LEAGUE_MARKET_BIAS = {
    265: {"O/U 2.5:under": 1.08, "BTTS:no": 1.05, "O/U 1.5:over": 1.02},
    71: {"O/U 2.5:over": 1.03, "O/U 1.5:over": 1.05, "BTTS:yes": 1.03},
    262: {"O/U 2.5:over": 1.07, "O/U 1.5:over": 1.08, "BTTS:yes": 1.06},
    253: {"O/U 2.5:over": 1.09, "O/U 1.5:over": 1.10, "BTTS:yes": 1.08},
    128: {"O/U 2.5:under": 1.08, "BTTS:no": 1.06, "O/U 1.5:over": 1.01},
    239: {"O/U 2.5:under": 1.05, "BTTS:no": 1.03, "O/U 1.5:over": 1.01},
    281: {"O/U 2.5:over": 1.05, "O/U 1.5:over": 1.07, "BTTS:yes": 1.04},
    242: {"O/U 2.5:over": 1.05, "O/U 1.5:over": 1.07, "BTTS:yes": 1.04},
    39: {"O/U 2.5:over": 1.03, "O/U 1.5:over": 1.04, "BTTS:yes": 1.02},
    140: {"O/U 2.5:over": 1.04, "O/U 1.5:over": 1.05, "BTTS:yes": 1.03},
    135: {"O/U 2.5:under": 1.04, "BTTS:no": 1.02, "O/U 1.5:over": 1.01},
    78: {"O/U 2.5:over": 1.05, "O/U 1.5:over": 1.06, "BTTS:yes": 1.03},
    61: {"O/U 2.5:over": 1.04, "O/U 1.5:over": 1.05, "BTTS:yes": 1.02},
    2: {"O/U 2.5:over": 1.03, "O/U 1.5:over": 1.04, "BTTS:yes": 1.03},
    3: {"O/U 2.5:over": 1.03, "O/U 1.5:over": 1.04, "BTTS:yes": 1.03},
    848: {"O/U 2.5:over": 1.03, "O/U 1.5:over": 1.04, "BTTS:yes": 1.03},
    13: {"O/U 2.5:over": 1.04, "O/U 1.5:over": 1.05, "BTTS:yes": 1.04},
    11: {"O/U 2.5:over": 1.04, "O/U 1.5:over": 1.05, "BTTS:yes": 1.04},
    94: {"O/U 2.5:under": 1.04, "BTTS:no": 1.03, "O/U 1.5:over": 1.02},
    88: {"O/U 2.5:over": 1.11, "O/U 1.5:over": 1.10, "BTTS:yes": 1.08},
    203: {"O/U 2.5:over": 1.06, "O/U 1.5:over": 1.07, "BTTS:yes": 1.04},
    307: {"O/U 2.5:over": 1.09, "O/U 1.5:over": 1.10, "BTTS:yes": 1.07},
}

LEAGUE_NAMES = {
    league_id: meta["league_name"]
    for league_id, meta in LEAGUE_META.items()
}

LEAGUES_DISPLAY = {
    league_id: f"{meta['flag']} {meta['display_name']}"
    for league_id, meta in LEAGUE_META.items()
}


def league_meta(league_id: int) -> dict:
    meta = LEAGUE_META.get(league_id, {})
    plain = meta.get("league_name", f"Liga {league_id}")
    display = meta.get("display_name", plain)
    flag = meta.get("flag", "⚽")
    return {
        "id": league_id,
        "league_name": plain,
        "display_name": display,
        "display_full": f"{flag} {display}",
        "country_name": meta.get("country_name", "Cobertura general"),
        "country_code": meta.get("country_code", "INT"),
        "flag": flag,
        "region": meta.get("region", "general"),
        "market_bias": LEAGUE_MARKET_BIAS.get(league_id, {}),
    }


def league_display_name(league_id: int) -> str:
    """Nombre legible con bandera; si el ID no está mapeado, muestra un fallback."""
    return league_meta(league_id)["display_full"]


def league_country_name(league_id: int) -> str:
    return league_meta(league_id)["country_name"]


def league_flag(league_id: int) -> str:
    return league_meta(league_id)["flag"]


def _normalize_name(raw: str) -> str:
    base = unicodedata.normalize("NFKD", str(raw or "")).encode("ascii", "ignore").decode("ascii")
    return "".join(ch for ch in base.lower() if ch.isalnum())


def find_league_id_by_name(raw: str) -> int | None:
    needle = _normalize_name(raw)
    if not needle:
        return None
    for league_id, meta in LEAGUE_META.items():
        candidates = [
            meta.get("league_name", ""),
            meta.get("display_name", ""),
            f"{meta.get('flag', '')} {meta.get('display_name', '')}",
            meta.get("country_name", ""),
        ]
        if any(_normalize_name(candidate) == needle for candidate in candidates if candidate):
            return league_id
    for league_id, meta in LEAGUE_META.items():
        candidates = [
            meta.get("league_name", ""),
            meta.get("display_name", ""),
            meta.get("country_name", ""),
        ]
        if any(needle in _normalize_name(candidate) for candidate in candidates if candidate):
            return league_id
    return None
