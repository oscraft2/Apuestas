import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path


class BenchmarkStore:
    def __init__(self, path: str):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def _load(self) -> list[dict]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save(self, items: list[dict]) -> None:
        self.path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_picks(self) -> list[dict]:
        with self.lock:
            items = self._load()
        return sorted(items, key=lambda item: item.get("kickoff_utc") or item.get("created_at") or "", reverse=True)

    def add_pick(self, payload: dict) -> dict:
        item = {
            "id": uuid.uuid4().hex[:12],
            "source": str(payload.get("source", "")).strip(),
            "league_id": payload.get("league_id"),
            "league": str(payload.get("league", "")).strip(),
            "home": str(payload.get("home", "")).strip(),
            "away": str(payload.get("away", "")).strip(),
            "market": str(payload.get("market", "")).strip(),
            "selection": str(payload.get("selection", "")).strip(),
            "odds": float(payload.get("odds", 0)),
            "kickoff_utc": str(payload.get("kickoff_utc", "")).strip(),
            "note": str(payload.get("note", "")).strip(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with self.lock:
            items = self._load()
            items.append(item)
            self._save(items)
        return item

    def delete_pick(self, pick_id: str) -> bool:
        with self.lock:
            items = self._load()
            filtered = [item for item in items if item.get("id") != pick_id]
            if len(filtered) == len(items):
                return False
            self._save(filtered)
        return True
