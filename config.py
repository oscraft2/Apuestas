import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class Config:
    # API Keys
    telegram_token: str = os.getenv("TELEGRAM_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    odds_api_key: str = os.getenv("ODDS_API_KEY", "")
    football_api_key: str = os.getenv("FOOTBALL_API_KEY", "")
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")

    # Mercados objetivo
    target_markets: List[str] = field(default_factory=lambda: ["h2h", "totals"])

    # Ligas monitoreadas (IDs de API-Football)
    target_leagues: List[int] = field(default_factory=lambda: [
        39,   # Premier League
        140,  # La Liga
        135,  # Serie A
        78,   # Bundesliga
        61,   # Ligue 1
        2,    # Champions League
        3,    # Europa League
    ])

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

    # Scheduler: reportes automáticos (hora UTC)
    report_hours_utc: List[int] = field(default_factory=lambda: [8, 17])

    # ELO
    elo_base: float = 1500.0
    elo_spread: float = 300.0
    elo_k_factor: float = 32.0

    # Localía
    home_advantage_factor: float = 1.15

    # The Odds API
    odds_regions: str = "eu,uk"
    odds_sport: str = "soccer"

    # DeepSeek
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_max_adjustment: float = 0.05   # ±5% máximo

    # Temporada actual
    season: int = 2024


config = Config()
