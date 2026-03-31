"""
Estado compartido en memoria entre el bot y la API REST.
El análisis pesado solo lo rellena el scheduler central (N veces/día).
Tras cada update se puede persistir en disco (live_snapshot) para recuperar tras reinicios.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class LiveState:
    today_results: list = field(default_factory=list)   # todos los partidos del último análisis
    highlight_results: list = field(default_factory=list)  # top "llamativos" (ranking interest_score)
    leader_results: list = field(default_factory=list)  # picks oficiales del día (ValueX Prime)
    leader_mixes: list = field(default_factory=list)    # combinadas derivadas de líderes (PowerMix)
    last_run: Optional[str] = None                       # ISO timestamp
    total_value_bets: int = 0
    leagues_analyzed: list = field(default_factory=list)
    runs_today: int = 0                                  # número de corridas hoy (UTC)
    last_publish_utc: Optional[str] = None               # último post automático/manual a Telegram
    last_publish_kind: str = ""                          # scheduled | startup | admin_summary | admin_custom
    last_publish_parts: int = 0
    last_publish_target: str = ""


# Singleton accesible desde bot y API
live = LiveState()


def is_cache_ready_today() -> bool:
    """True si ya hay un análisis de hoy (UTC) con resultados en memoria."""
    today = datetime.now(timezone.utc).date().isoformat()
    return bool(
        live.last_run
        and live.last_run[:10] == today
        and live.today_results
    )


def update(results: list, leagues: list = None, highlights: list = None, leaders: list = None, mixes: list = None):
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    prev_date = live.last_run[:10] if live.last_run else None
    if prev_date == today:
        live.runs_today = getattr(live, "runs_today", 0) + 1
    else:
        live.runs_today = 1

    live.today_results = results
    live.highlight_results = highlights if highlights is not None else []
    live.leader_results = leaders if leaders is not None else []
    live.leader_mixes = mixes if mixes is not None else []
    live.last_run = now.isoformat()
    live.total_value_bets = sum(1 for r in results if r.get("has_value"))
    live.leagues_analyzed = leagues or []

    try:
        from src.analysis.live_snapshot import persist_live_snapshot

        persist_live_snapshot()
    except Exception as exc:
        logger.debug("Persist snapshot omitido: %s", exc)


def record_publish(kind: str, parts: int, target: str = "telegram"):
    live.last_publish_utc = datetime.now(timezone.utc).isoformat()
    live.last_publish_kind = kind
    live.last_publish_parts = int(parts or 0)
    live.last_publish_target = target