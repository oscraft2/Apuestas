import os
import logging
from dataclasses import dataclass, field
from typing import List

logger = logging.getLogger(__name__)


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


# IDs por defecto (API-Football). Sobrescribibles con TARGET_LEAGUES en .env
# Orden: grandes ligas EU + copas UEFA + selecciones (FIFA/UEFA/CONMEBOL) + CONMEBOL clubes + LATAM + otros.
_DEFAULT_LEAGUE_IDS = [
    # Top 5 Europa
    39, 140, 135, 78, 61,
    # Copas UEFA (clubes)
    2, 3, 848,
    # Selecciones — partidos entre países (Mundial, Euro, eliminatorias, Copa América, amistosos, Nations League)
    1, 4, 5, 9, 10, 16, 1073,
    # CONMEBOL (copas de clubes)
    13, 11,
    # LATAM (ligas fuertes)
    265, 71, 262, 253, 128, 239, 281, 242,
    # Otros mercados relevantes
    88, 94, 203, 307,
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
    # ── Telegram ──────────────────────────────────────────────────────────────
    telegram_token:   str = os.getenv("TELEGRAM_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # ── APIs externas ─────────────────────────────────────────────────────────
    odds_api_key:      str = os.getenv("ODDS_API_KEY", "")
    football_api_key:  str = os.getenv("FOOTBALL_API_KEY", "")
    deepseek_api_key:  str = os.getenv("DEEPSEEK_API_KEY", "")

    # ── Base de datos ─────────────────────────────────────────────────────────
    database_url: str = os.getenv("DATABASE_URL", "")   # Railway inyecta esto

    # ── Stripe (pagos premium) ────────────────────────────────────────────────
    stripe_secret_key:      str = os.getenv("STRIPE_SECRET_KEY", "")
    stripe_webhook_secret:  str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    stripe_price_id:        str = os.getenv("STRIPE_PRICE_ID", "")      # price_xxx

    # ── Admin ─────────────────────────────────────────────────────────────────
    # ID de Telegram del administrador (puede usar /admin)
    admin_user_id: int = int(os.getenv("ADMIN_USER_ID", "0"))
    # Clave para proteger endpoints POST de la API
    api_secret_key: str = os.getenv("API_SECRET_KEY", "")
    # Token para panel admin web (distinto del user_id de Telegram)
    admin_token: str = os.getenv("ADMIN_TOKEN", "")
    # Secreto para firmar cookies de sesión admin
    admin_session_secret: str = os.getenv("ADMIN_SESSION_SECRET", "changeme-secret-32chars")
    # Nombre de la cookie de sesión admin
    admin_cookie_name: str = "vxp_admin"
    # Marcar cookie como Secure en producción (HTTPS)
    admin_cookie_secure: bool = os.getenv("ADMIN_COOKIE_SECURE", "true").lower() == "true"
    # Duración de sesión admin en horas
    admin_session_hours: int = int(os.getenv("ADMIN_SESSION_HOURS", "8"))
    # Arrancar análisis automático al iniciar
    auto_warmup_on_start: bool = os.getenv("AUTO_WARMUP_ON_START", "true").lower() == "true"

    # ── Mercados objetivo (The Odds API: h2h, totals, btts) ───────────────────
    target_markets: List[str] = field(default_factory=lambda: ["h2h", "totals", "btts"])

    # ── Ligas monitoreadas (IDs de API-Football) ──────────────────────────────
    target_leagues: List[int] = field(default_factory=_parse_target_leagues)

    # ── Pesos del consenso ────────────────────────────────────────────────────
    consensus_weights: dict = field(default_factory=lambda: {
        "market":   0.35,
        "poisson":  0.25,
        "elo":      0.15,
        "features": 0.15,
        "deepseek": 0.10,
    })

    # ── Filtros de calidad ────────────────────────────────────────────────────
    min_value_pct:          float = 0.03
    min_bookmakers:         int   = 4
    min_confidence:         float = 0.60
    min_model_agreement:    float = 0.66
    min_odds:               float = 1.30
    max_odds:               float = 8.00

    # ── Cache ─────────────────────────────────────────────────────────────────
    cache_ttl_hours:  int = 6
    cache_dir:        str = "data/cache"
    predictions_dir:  str = "data/predictions"

    # ── Scheduler ─────────────────────────────────────────────────────────────
    report_hours_utc: List[int] = field(default_factory=_parse_report_hours)
    # Segundos tras arranque para primer análisis automático
    startup_analysis_delay_sec:   int = 30
    # Intervalo de sincronización de resultados (segundos)
    result_sync_interval_sec:     int = 3600
    # Intervalo de polling de movimientos de cuota (segundos)
    line_move_poll_interval_sec:  int = 1800
    # Si la API lanza análisis central en su propio loop (sin bot)
    api_schedule_central:         bool = True
    # Orígenes permitidos para CORS (separados por coma en FRONTEND_ORIGINS)
    frontend_origins: List[str] = field(default_factory=lambda: ["*"])

    # ── ELO ──────────────────────────────────────────────────────────────────
    elo_base:   float = 1500.0
    elo_spread: float = 300.0
    elo_k_factor: float = 32.0

    # ── Localía ──────────────────────────────────────────────────────────────
    home_advantage_factor: float = 1.15

    # ── The Odds API ──────────────────────────────────────────────────────────
    odds_regions: str = os.getenv("ODDS_REGIONS", "us,eu,uk")
    odds_sport:   str = "soccer"

    # ── DeepSeek ─────────────────────────────────────────────────────────────
    deepseek_model:          str   = "deepseek-chat"
    deepseek_base_url:       str   = "https://api.deepseek.com/v1"
    deepseek_max_adjustment: float = 0.05

    # ── Prime / Leaders ───────────────────────────────────────────────────────
    leader_top_n:      int   = 5      # Máximo de picks Prime por análisis
    highlight_top_n:   int   = 15     # Máximo de highlights por análisis
    leader_mix_legs:   int   = 3      # Piernas máx en PowerMix
    hero_league_id:    int   = int(os.getenv("HERO_LEAGUE_ID", "265"))  # Liga estrella (bonus score)
    # Markets habilitados para official_pick (1X2, O/U 2.5, O/U 1.5, BTTS)
    pick_markets: List[str] = field(default_factory=lambda: ["1X2", "O/U 2.5", "O/U 1.5", "BTTS"])

    # ── Temporada (auto-detectada) ────────────────────────────────────────────
    season: int = field(default_factory=lambda: __import__('datetime').datetime.now().year
                        if __import__('datetime').datetime.now().month >= 7
                        else __import__('datetime').datetime.now().year - 1)


config = Config()


def validate_env() -> bool:
    """
    Valida que las variables de entorno críticas estén configuradas.
    Retorna True si todo OK. Loguea warnings para las opcionales ausentes.
    """
    required = {
        "TELEGRAM_TOKEN":  config.telegram_token,
        "ODDS_API_KEY":    config.odds_api_key,
        "DEEPSEEK_API_KEY": config.deepseek_api_key,
    }
    optional = {
        "FOOTBALL_API_KEY":     config.football_api_key,
        "DATABASE_URL":         config.database_url,
        "STRIPE_SECRET_KEY":    config.stripe_secret_key,
        "STRIPE_WEBHOOK_SECRET": config.stripe_webhook_secret,
        "STRIPE_PRICE_ID":      config.stripe_price_id,
        "ADMIN_USER_ID":        str(config.admin_user_id) if config.admin_user_id else "",
        "API_SECRET_KEY":       config.api_secret_key,
        "TELEGRAM_CHAT_ID":     config.telegram_chat_id,
    }

    ok = True
    for name, val in required.items():
        if not val:
            logger.error("❌ Variable requerida no configurada: %s", name)
            ok = False

    for name, val in optional.items():
        if not val:
            logger.warning("⚠️  Variable opcional ausente: %s", name)

    if ok:
        logger.info("✅ Variables de entorno validadas correctamente")
    return ok
