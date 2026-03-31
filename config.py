import os
import logging
from dataclasses import dataclass, field
from typing import List

logger = logging.getLogger(__name__)


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

    # ── Mercados objetivo ─────────────────────────────────────────────────────
    target_markets: List[str] = field(default_factory=lambda: ["h2h", "totals"])

    # ── Ligas monitoreadas (IDs de API-Football) ──────────────────────────────
    target_leagues: List[int] = field(default_factory=lambda: [
        39,   # Premier League
        140,  # La Liga
        135,  # Serie A
        78,   # Bundesliga
        61,   # Ligue 1
        2,    # Champions League
        3,    # Europa League
    ])

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
    min_bookmakers:         int   = 5
    min_confidence:         float = 0.60
    min_model_agreement:    float = 0.66
    min_odds:               float = 1.30
    max_odds:               float = 8.00

    # ── Cache ─────────────────────────────────────────────────────────────────
    cache_ttl_hours:  int = 6
    cache_dir:        str = "data/cache"
    predictions_dir:  str = "data/predictions"

    # ── Scheduler ─────────────────────────────────────────────────────────────
    report_hours_utc: List[int] = field(default_factory=lambda: [8, 17])

    # ── ELO ──────────────────────────────────────────────────────────────────
    elo_base:   float = 1500.0
    elo_spread: float = 300.0
    elo_k_factor: float = 32.0

    # ── Localía ──────────────────────────────────────────────────────────────
    home_advantage_factor: float = 1.15

    # ── The Odds API ──────────────────────────────────────────────────────────
    odds_regions: str = "eu,uk"
    odds_sport:   str = "soccer"

    # ── DeepSeek ─────────────────────────────────────────────────────────────
    deepseek_model:          str   = "deepseek-chat"
    deepseek_base_url:       str   = "https://api.deepseek.com/v1"
    deepseek_max_adjustment: float = 0.05

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
