import os
from dataclasses import dataclass, field
from typing import List


def _normalize_secret(raw: str) -> str:
    """Quita espacios/saltos de línea y comillas envolventes (copiar/pegar desde Railway)."""
    s = (raw or "").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        s = s[1:-1].strip()
    return s


# IDs por defecto: foco Américas (Chile primero). Sobrescribibles con TARGET_LEAGUES en .env
_DEFAULT_LEAGUE_IDS = [
    265,  # 🇨🇱 Chile — Primera División (protagonista por defecto)
    71,   # 🇧🇷 Brasil — Brasileirão Série A
    262,  # 🇲🇽 México — Liga MX
    253,  # 🇺🇸 MLS
    128,  # 🇦🇷 Argentina — Liga Profesional
    239,  # 🇨🇴 Colombia — Primera A
]


def _parse_target_leagues() -> List[int]:
    """
    TARGET_LEAGUES=39,140,135 — lista separada por comas.
    Si está vacío o es inválida, se usan las ligas por defecto.
    """
    raw = os.getenv("TARGET_LEAGUES", "").strip()
    if not raw:
        return list(_DEFAULT_LEAGUE_IDS)
    out: List[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            continue
    return out if out else list(_DEFAULT_LEAGUE_IDS)


def _parse_report_hours() -> List[int]:
    """REPORT_HOURS_UTC=8,15,22 — horas UTC del análisis central."""
    raw = os.getenv("REPORT_HOURS_UTC", "").strip()
    if not raw:
        return [8, 15, 22]
    out: List[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            h = int(part)
            if 0 <= h <= 23:
                out.append(h)
        except ValueError:
            continue
    return sorted(set(out)) if out else [8, 15, 22]


def _parse_hero_league_id() -> int:
    """Liga protagonista: prioridad en ranking de destacados (ID API-Football)."""
    raw = os.getenv("HERO_LEAGUE_ID", "265").strip()
    try:
        return int(raw)
    except ValueError:
        return 265


@dataclass
class Config:
    # API Keys
    telegram_token: str = os.getenv("TELEGRAM_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    odds_api_key: str = os.getenv("ODDS_API_KEY", "")
    football_api_key: str = os.getenv("FOOTBALL_API_KEY", "")
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")

    # Panel admin web — sin espacios ni comillas extra (se normalizan al cargar)
    admin_token: str = field(default_factory=lambda: _normalize_secret(os.getenv("ADMIN_TOKEN", "")))

    # Mercados objetivo
    target_markets: List[str] = field(default_factory=lambda: ["h2h", "totals"])

    # Ligas monitoreadas (IDs API-Football) — ver TARGET_LEAGUES en .env
    target_leagues: List[int] = field(default_factory=_parse_target_leagues)

    # Prioridad en “partidos llamativos” (boost suave). Por defecto Chile (265).
    hero_league_id: int = field(default_factory=_parse_hero_league_id)

    # Pesos del consenso
    consensus_weights: dict = field(default_factory=lambda: {
        "market":   0.35,
        "poisson":  0.25,
        "elo":      0.15,
        "features": 0.15,
        "deepseek": 0.10,
    })

    # Filtros de calidad
    min_value_pct: float = 0.03          # Valor mínimo > 3%
    min_bookmakers: int = 5              # Al menos 5 bookmakers
    min_confidence: float = 0.60         # Confianza > 60%
    min_model_agreement: float = 0.66    # 2 de 3 modelos coinciden
    min_odds: float = 1.30
    max_odds: float = 8.00

    # Cache
    cache_ttl_hours: int = 6
    cache_dir: str = "data/cache"
    predictions_dir: str = "data/predictions"

    # Scheduler: análisis central (hora UTC). REPORT_HOURS_UTC=8,15,22
    report_hours_utc: List[int] = field(default_factory=lambda: _parse_report_hours())

    # Cuántos partidos "más llamativos" destacar en resúmenes / Telegram
    highlight_top_n: int = 15

    # ELO
    elo_base: float = 1500.0
    elo_spread: float = 300.0
    elo_k_factor: float = 32.0

    # Localía
    home_advantage_factor: float = 1.15

    # The Odds API — para ligas americanas conviene incluir us (bookmakers USA)
    odds_regions: str = os.getenv("ODDS_REGIONS", "us,eu,uk")
    odds_sport: str = "soccer"

    # DeepSeek
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_max_adjustment: float = 0.05   # ±5% máximo

    # Temporada actual — se auto-detecta: jul-dic = año actual, ene-jun = año anterior
    season: int = field(default_factory=lambda: __import__('datetime').datetime.now().year
                        if __import__('datetime').datetime.now().month >= 7
                        else __import__('datetime').datetime.now().year - 1)


config = Config()
