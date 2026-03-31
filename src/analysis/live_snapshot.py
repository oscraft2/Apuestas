"""
Persistencia del último análisis central en disco.

- Las medidas históricas (aciertos, ROI) siguen viniendo del tracker (predictions.jsonl).
- Este snapshot evita que la caché en RAM se pierda del todo al reiniciar el proceso
  y permite recuperar el tablero si el volumen `data/` persiste (p. ej. Railway con disco).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

VERSION = 1
FILENAME = "last_live_analysis.json"


def _snapshot_path() -> Path:
    from config import config

    base = Path(config.cache_dir)
    base.mkdir(parents=True, exist_ok=True)
    return base / FILENAME


def persist_live_snapshot() -> None:
    """Serializa `shared_state.live` tras cada actualización de análisis."""
    from config import config

    if not getattr(config, "persist_live_snapshot", True):
        return
    from src.shared_state import live

    path = _snapshot_path()
    payload = {
        "version": VERSION,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "analysis_run_at": live.last_run,
        "runs_today": int(getattr(live, "runs_today", 0) or 0),
        "results": live.today_results,
        "highlights": live.highlight_results,
        "leaders": live.leader_results,
        "mixes": live.leader_mixes,
        "leagues_done": live.leagues_analyzed,
    }
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except OSError as e:
        logger.warning("No se pudo guardar snapshot de análisis: %s", e)


def restore_live_snapshot() -> bool:
    """
    Restaura `live` desde disco. Devuelve True si hubo datos válidos.
    Debe llamarse al arrancar la API antes del warmup.
    """
    from config import config

    if not getattr(config, "persist_live_snapshot", True):
        return False
    from src.shared_state import live

    path = _snapshot_path()
    if not path.exists():
        return False
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Snapshot ilegible: %s", e)
        return False
    if int(raw.get("version") or 0) != VERSION:
        logger.warning("Snapshot con versión no soportada, ignorando")
        return False

    live.today_results = raw.get("results") or []
    live.highlight_results = raw.get("highlights") or []
    live.leader_results = raw.get("leaders") or []
    live.leader_mixes = raw.get("mixes") or []
    live.leagues_analyzed = raw.get("leagues_done") or []
    live.last_run = raw.get("analysis_run_at") or raw.get("saved_at")
    live.total_value_bets = sum(1 for r in live.today_results if r.get("has_value"))
    live.runs_today = int(raw.get("runs_today") or 1)

    logger.info(
        "Snapshot de análisis restaurado: %s partidos · %s destacados · %s Prime · última pasada %s",
        len(live.today_results),
        len(live.highlight_results),
        len(live.leader_results),
        (live.last_run or "")[:19],
    )
    return bool(live.today_results or live.highlight_results or live.leader_results)
