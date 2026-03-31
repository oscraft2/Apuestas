from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def _cycles_dir() -> Path:
    from config import config

    base = Path(config.predictions_dir) / "cycles"
    base.mkdir(parents=True, exist_ok=True)
    return base


def persist_cycle_snapshot(*, analysis_date: str, results: list, highlights: list, leaders: list, mixes: list, leagues_done: list) -> str:
    path = _cycles_dir() / f"{analysis_date}.json"
    payload = {
        "analysis_date": analysis_date,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "results": results or [],
        "highlights": highlights or [],
        "leaders": leaders or [],
        "mixes": mixes or [],
        "leagues_done": leagues_done or [],
        "count": len(results or []),
        "highlight_count": len(highlights or []),
        "leader_count": len(leaders or []),
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return str(path)


def list_cycle_snapshots(limit: int = 30) -> list[dict]:
    items = []
    for path in sorted(_cycles_dir().glob("*.json"), reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        items.append({
            "analysis_date": payload.get("analysis_date") or path.stem,
            "saved_at": payload.get("saved_at"),
            "count": int(payload.get("count") or 0),
            "highlight_count": int(payload.get("highlight_count") or 0),
            "leader_count": int(payload.get("leader_count") or 0),
            "leagues_done": payload.get("leagues_done") or [],
        })
        if len(items) >= max(1, int(limit or 30)):
            break
    return items


def get_cycle_snapshot(analysis_date: str) -> dict | None:
    path = _cycles_dir() / f"{analysis_date}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
