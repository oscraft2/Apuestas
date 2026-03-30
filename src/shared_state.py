"""
Estado compartido en memoria entre el bot y la API REST.
Permite que el scheduler del bot escriba los resultados
y la API los sirva al frontend sin releer archivos.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class LiveState:
    today_results: list = field(default_factory=list)   # análisis del día
    last_run: Optional[str] = None                       # ISO timestamp
    total_value_bets: int = 0
    leagues_analyzed: list = field(default_factory=list)


# Singleton accesible desde bot y API
live = LiveState()


def update(results: list, leagues: list = None):
    live.today_results = results
    live.last_run = datetime.now(timezone.utc).isoformat()
    live.total_value_bets = sum(1 for r in results if r.get("has_value"))
    live.leagues_analyzed = leagues or []
