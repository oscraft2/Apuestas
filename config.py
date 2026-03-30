import os
from dataclasses import dataclass, field
from typing import List


def _normalize_secret(raw: str) -> str:
    """Quita espacios/saltos de línea y comillas envolventes (copiar/pegar desde Railway)."""
    s = (raw or "").replace("\u200b", "").replace("\ufeff", "").strip()
    quote_pairs = [('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’")]
    changed = True
    while changed and len(s) >= 2:
        changed = False
        for left, right in quote_pairs:
            if s.startswith(left) and s.endswith(right):
                s = s[len(left):len(s) - len(right)].strip()
                changed = True
                break
    return s


# IDs por defecto: foco Américas (Chile primero). Sobrescribibles con TARGET_LEAGUES en .env
_DEFAULT_LEAGUE_IDS = [
    265,  # 🇨🇱 Chile — Primera División (protagonista por defecto)
    71,   # 🇧🇷 Brasil — Brasileirão Série A
    262,  # 🇲🇽 México — Liga MX
    253,  # 🇺🇸 MLS
    128,  # 🇦🇷 Argentina — Liga Profesional
    239,  # 🇨🇴 Colombia — Primera A
    88,   # 🇳🇱 Eredivisie
    94,   # 🇵🇹 Primeira Liga
    203,  # 🇹🇷 Süper Lig
    307,  # 🇸🇦 Saudi Pro League
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


def _parse_bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "si", "sí"}


def _parse_int_env(name: str, default: int, min_value: int | None = None, max_value: int | None = None) -> int:
    raw = os.getenv(name, "").strip()
    try:
        value = int(raw)
    except ValueError:
        value = default
    if min_value is not None:
        value = max(min_value, value)
    if max_value is not None:
        value = min(max_value, value)
    return value


def _parse_csv_env(name: str, default: str = "") -> List[str]:
    raw = os.getenv(name, default).strip()
    return [part.strip() for part in raw.split(",") if part.strip()]


def _default_admin_cookie_secure() -> bool:
    return bool(
        os.getenv("RAILWAY_PROJECT_ID")
        or os.getenv("RAILWAY_ENVIRONMENT_ID")
        or os.getenv("RAILWAY_ENVIRONMENT_NAME")
    )


@dataclass
class Config:
    # API Keys
    telegram_token: str = os.getenv("TELEGRAM_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    odds_api_key: str = os.getenv("ODDS_API_KEY", "")
    football_api_key: str = os.getenv("FOOTBALL_API_KEY", "")
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")

    # Panel admin web — contraseña maestra y secreto de sesión
    admin_token: str = field(default_factory=lambda: _normalize_secret(os.getenv("ADMIN_TOKEN", "")))
    admin_session_secret: str = field(default_factory=lambda: _normalize_secret(os.getenv("ADMIN_SESSION_SECRET", os.getenv("ADMIN_TOKEN", ""))))
    admin_session_hours: int = field(default_factory=lambda: _parse_int_env("ADMIN_SESSION_HOURS", 12, 1, 168))
    admin_cookie_secure: bool = field(default_factory=lambda: _parse_bool_env("ADMIN_COOKIE_SECURE", _default_admin_cookie_secure()))
    admin_cookie_name: str = "valuex_admin_session"
    frontend_origins: List[str] = field(default_factory=lambda: _parse_csv_env("FRONTEND_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"))

    # Mercados objetivo
    target_markets: List[str] = field(default_factory=lambda: ["h2h", "totals", "btts"])

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
    benchmark_data_path: str = "data/benchmark/manual_picks.json"

    # Scheduler: análisis central (hora UTC). REPORT_HOURS_UTC=8,15,22
    report_hours_utc: List[int] = field(default_factory=lambda: _parse_report_hours())

    # Cuántos partidos "más llamativos" destacar en resúmenes / Telegram
    highlight_top_n: int = 15
    leader_top_n: int = field(default_factory=lambda: _parse_int_env("LEADER_TOP_N", 5, 1, 10))
    leader_mix_legs: int = field(default_factory=lambda: _parse_int_env("LEADER_MIX_LEGS", 3, 2, 4))

    # Telegram / canal
    telegram_publish_top_matches: int = field(default_factory=lambda: _parse_int_env("TELEGRAM_PUBLISH_TOP_MATCHES", 3, 0, 10))
    telegram_publish_match_details: bool = field(default_factory=lambda: _parse_bool_env("TELEGRAM_PUBLISH_MATCH_DETAILS", True))
    auto_warmup_on_start: bool = field(default_factory=lambda: _parse_bool_env("AUTO_WARMUP_ON_START", True))
    auto_publish_startup_report: bool = field(default_factory=lambda: _parse_bool_env("AUTO_PUBLISH_STARTUP_REPORT", False))
    startup_analysis_delay_sec: int = field(default_factory=lambda: _parse_int_env("STARTUP_ANALYSIS_DELAY_SEC", 20, 0, 600))
    line_move_poll_interval_sec: int = field(default_factory=lambda: _parse_int_env("LINE_MOVE_POLL_INTERVAL_SEC", 1800, 60, 86400))
    result_sync_interval_sec: int = field(default_factory=lambda: _parse_int_env("RESULT_SYNC_INTERVAL_SEC", 3600, 300, 86400))

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
