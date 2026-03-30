from datetime import datetime, timezone
import threading


_analysis_lock = threading.Lock()
_analysis_status = {
    "running": False,
    "owner": "",
    "started_at": None,
}


def try_start(owner: str) -> bool:
    acquired = _analysis_lock.acquire(blocking=False)
    if not acquired:
        return False
    _analysis_status["running"] = True
    _analysis_status["owner"] = owner
    _analysis_status["started_at"] = datetime.now(timezone.utc).isoformat()
    return True


def finish() -> None:
    _analysis_status["running"] = False
    _analysis_status["owner"] = ""
    _analysis_status["started_at"] = None
    if _analysis_lock.locked():
        _analysis_lock.release()


def locked() -> bool:
    return _analysis_lock.locked()


def snapshot() -> dict:
    return dict(_analysis_status)
