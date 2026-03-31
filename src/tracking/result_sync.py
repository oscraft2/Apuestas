import logging
import re
import unicodedata
from datetime import datetime, timezone

from config import config
from src.data.football_api import get_fixtures_by_date
from src.league_labels import find_league_id_by_name
from src.tracking.tracker import PredictionTracker

logger = logging.getLogger(__name__)

FINAL_STATUSES = {"FT", "AET", "PEN"}


def _normalize_text(raw: str) -> str:
    base = unicodedata.normalize("NFKD", str(raw or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", base.lower())


def _kickoff_distance_seconds(prediction: dict, fixture: dict) -> float:
    pred_time = prediction.get("time", "")
    fixture_time = (((fixture or {}).get("fixture") or {}).get("date") or "")
    if not pred_time or not fixture_time:
        return 10**9
    try:
        pred_dt = datetime.fromisoformat(pred_time.replace("Z", "+00:00"))
        fixture_dt = datetime.fromisoformat(fixture_time.replace("Z", "+00:00"))
        return abs((pred_dt - fixture_dt).total_seconds())
    except ValueError:
        return 10**9


def _extract_final_score(fixture: dict) -> tuple[int, int] | None:
    score = fixture.get("score", {}) or {}
    fulltime = score.get("fulltime", {}) or {}
    home = fulltime.get("home")
    away = fulltime.get("away")
    if home is None or away is None:
        goals = fixture.get("goals", {}) or {}
        home = goals.get("home")
        away = goals.get("away")
    if home is None or away is None:
        return None
    return int(home), int(away)


def _match_prediction_fixture(prediction: dict, fixtures: list[dict]) -> dict | None:
    pred_home = _normalize_text(prediction.get("home"))
    pred_away = _normalize_text(prediction.get("away"))
    candidates = []

    for fixture in fixtures or []:
        teams = fixture.get("teams", {}) or {}
        home_name = _normalize_text((teams.get("home") or {}).get("name"))
        away_name = _normalize_text((teams.get("away") or {}).get("name"))
        if pred_home == home_name and pred_away == away_name:
            candidates.append(fixture)

    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    return min(candidates, key=lambda fixture: _kickoff_distance_seconds(prediction, fixture))


def sync_pending_results(tracker: PredictionTracker | None = None, max_days_back: int = 4) -> dict:
    if not config.football_api_key:
        return {"ok": False, "reason": "FOOTBALL_API_KEY no configurada", "checked": 0, "settled": 0}

    tracker = tracker or PredictionTracker()
    pending = tracker.get_pending_predictions(max_days_back=max_days_back)
    if not pending:
        return {"ok": True, "checked": 0, "settled": 0, "groups": 0}

    grouped: dict[tuple[int, str], list[dict]] = {}
    for prediction in pending:
        league_id = prediction.get("league_id")
        if not isinstance(league_id, int):
            league_id = find_league_id_by_name(prediction.get("league"))
        date_str = (prediction.get("time") or "")[:10] or prediction.get("date")
        if not league_id or not date_str:
            continue
        grouped.setdefault((league_id, date_str), []).append(prediction)

    checked = 0
    settled = 0
    for (league_id, date_str), predictions in grouped.items():
        fixtures = get_fixtures_by_date(league_id, date_str)
        for prediction in predictions:
            checked += 1
            fixture = _match_prediction_fixture(prediction, fixtures)
            if not fixture:
                continue
            status = ((((fixture or {}).get("fixture") or {}).get("status") or {}).get("short") or "").upper()
            if status not in FINAL_STATUSES:
                continue
            final_score = _extract_final_score(fixture)
            if not final_score:
                continue
            tracker.log_result(prediction.get("match_id", ""), final_score[0], final_score[1])
            settled += 1

    logger.info("ResultSync: %s pendientes revisadas, %s liquidadas", checked, settled)
    return {"ok": True, "checked": checked, "settled": settled, "groups": len(grouped)}
