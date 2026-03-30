"""
Estado compartido en memoria entre el bot y la API REST.
El análisis pesado solo lo rellena el scheduler central (N veces/día).
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class LiveState:
    today_results: list = field(default_factory=list)   # todos los partidos del último análisis
    highlight_results: list = field(default_factory=list)  # top "llamativos" (ranking interest_score)
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


def update(results: list, leagues: list = None, highlights: list = None):
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    prev_date = live.last_run[:10] if live.last_run else None
    if prev_date == today:
        live.runs_today = getattr(live, "runs_today", 0) + 1
    else:
        live.runs_today = 1

    live.today_results = results
    live.highlight_results = highlights if highlights is not None else []
    live.last_run = now.isoformat()
    live.total_value_bets = sum(1 for r in results if r.get("has_value"))
    live.leagues_analyzed = leagues or []


def record_publish(kind: str, parts: int, target: str = "telegram"):
    live.last_publish_utc = datetime.now(timezone.utc).isoformat()
    live.last_publish_kind = kind
    live.last_publish_parts = int(parts or 0)
    live.last_publish_target = target