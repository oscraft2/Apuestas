"""
API REST (FastAPI) — Football Value Bot V3
Endpoints bajo /api/... + sirve el dashboard React como SPA.
"""
import logging
import asyncio
import hmac
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
from pydantic import BaseModel, Field

from fastapi import Body, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse

import src.shared_state as state
from src.api.admin_session import create_admin_session, verify_admin_session
from src.analysis.runtime import finish as finish_analysis_run
from src.analysis.runtime import locked as analysis_run_locked
from src.analysis.runtime import snapshot as analysis_run_snapshot
from src.analysis.runtime import try_start as try_start_analysis_run
from src.benchmark.store import BenchmarkStore
from src.tracking.tracker import PredictionTracker
from src.backtest.backtester import Backtester
from src.analytics.calibration import LeagueCalibration
from src.bankroll.manager import BankrollManager
from src.users.manager import UserManager
from config import config

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Football Value Bot V3 API",
    description="API REST para el dashboard ValueXPro",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

tracker = PredictionTracker()
backtester = Backtester(f"{config.predictions_dir}/predictions.jsonl")
calibration = LeagueCalibration()
bankroll_mgr = BankrollManager()
user_mgr = UserManager()
benchmark_store = BenchmarkStore(config.benchmark_data_path)

# ── Cache de análisis en vivo (1 hora) ────────────────────────────────────────
_live_lock = asyncio.Lock()

# Un solo análisis pesado a la vez entre API admin y scheduler Telegram (`both`)
_admin_job_state = {
    "status": "idle",            # idle | queued | running | success | error
    "started_at": None,
    "finished_at": None,
    "error": None,
    "last_result_count": 0,
}


def _admin_session_max_age() -> int:
    return max(3600, int(config.admin_session_hours) * 3600)


def _admin_cookie_kwargs() -> dict:
    return {
        "key": config.admin_cookie_name,
        "httponly": True,
        "samesite": "lax",
        "secure": bool(config.admin_cookie_secure),
        "path": "/api/admin",
        "max_age": _admin_session_max_age(),
    }


def _normalize_text(raw: str) -> str:
    base = unicodedata.normalize("NFKD", str(raw or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", base.lower())


def _recommendation_from_1x2(item: dict) -> dict | None:
    c1 = item.get("consensus_1x2") or {}
    probs = c1.get("probs") or {}
    if not probs:
        return None
    outcome = max(probs, key=probs.get)
    label_map = {
        "home": f"Gana {item.get('home', 'local')}",
        "draw": "Empate",
        "away": f"Gana {item.get('away', 'visita')}",
    }
    return {
        "market": "1X2",
        "selection": label_map.get(outcome, outcome),
        "outcome": outcome,
        "probability": float(probs.get(outcome, 0)),
        "odds": (c1.get("fair_odds") or {}).get(outcome),
        "source": "consensus",
    }


def _recommendation_from_totals(item: dict) -> dict | None:
    cou = item.get("consensus_ou") or {}
    probs = cou.get("probs") or {}
    if not probs:
        return None
    outcome = max(probs, key=probs.get)
    label_map = {
        "over": "Over 2.5",
        "under": "Under 2.5",
    }
    return {
        "market": "Totales 2.5",
        "selection": label_map.get(outcome, outcome),
        "outcome": outcome,
        "probability": float(probs.get(outcome, 0)),
        "odds": (cou.get("fair_odds") or {}).get(outcome),
        "source": "consensus",
    }


def _derive_primary_pick(item: dict) -> dict:
    top = (item.get("value_bets") or [None])[0]
    confidence = float((item.get("consensus_1x2") or {}).get("confidence") or 0)
    if top:
        return {
            "market": top.get("market"),
            "selection": top.get("label") or top.get("outcome"),
            "outcome": top.get("outcome"),
            "probability": top.get("prob"),
            "odds": top.get("odds", top.get("best_odds")),
            "value": top.get("value"),
            "kelly": top.get("kelly"),
            "confidence": confidence,
            "source": "value",
        }

    picks = [candidate for candidate in (_recommendation_from_1x2(item), _recommendation_from_totals(item)) if candidate]
    if not picks:
        return {
            "market": "Radar",
            "selection": "Sin recomendación principal",
            "source": "none",
            "confidence": confidence,
        }

    picks.sort(key=lambda candidate: float(candidate.get("probability") or 0), reverse=True)
    best = picks[0]
    best["confidence"] = confidence
    return best


def _derive_stake_plan(item: dict) -> dict:
    primary = _derive_primary_pick(item)
    confidence = float(primary.get("confidence") or 0)
    probability = float(primary.get("probability") or 0)
    value = float(primary.get("value") or 0)
    kelly = float(primary.get("kelly") or 0)

    if primary.get("source") == "none":
        return {
            "label": "Sin operacion",
            "units": "0u",
            "bankroll_pct": "0.0%",
            "confidence_band": "sin_dato",
            "reason": "Aun no hay lectura suficiente para sugerir una entrada",
        }

    if primary.get("source") != "value":
        if confidence >= 0.70 or probability >= 0.52:
            return {
                "label": "Consenso fuerte",
                "units": "0.75u",
                "bankroll_pct": "1.0%",
                "confidence_band": "alta",
                "reason": "El modelo ve una lectura firme aunque la cuota aun no marque un edge extremo",
            }
        if confidence >= 0.60 or probability >= 0.46:
            return {
                "label": "Seguimiento activo",
                "units": "0.50u",
                "bankroll_pct": "0.75%",
                "confidence_band": "media",
                "reason": "Hay senal utilizable del consenso, con stake controlado",
            }
        return {
            "label": "Lectura prudente",
            "units": "0.25u",
            "bankroll_pct": "0.50%",
            "confidence_band": "prudente",
            "reason": "Sin edge claro, pero con una inclinacion suficiente para seguimiento tactico",
        }

    if confidence >= 0.74 and (value >= 0.08 or kelly >= 0.06):
        return {
            "label": "Alta convicción",
            "units": "1.50u",
            "bankroll_pct": f"{max(kelly * 100, 1.75):.1f}%",
            "confidence_band": "alta",
            "reason": "Edge alto y consenso robusto",
        }
    if confidence >= 0.68 and (value >= 0.05 or kelly >= 0.035):
        return {
            "label": "Convicción media",
            "units": "1.00u",
            "bankroll_pct": f"{max(kelly * 100, 1.25):.1f}%",
            "confidence_band": "media",
            "reason": "Señal utilizable con control",
        }
    if confidence >= 0.60 or value >= 0.03 or kelly >= 0.02:
        return {
            "label": "Entrada util",
            "units": "0.75u",
            "bankroll_pct": f"{max(kelly * 100, 0.9):.1f}%",
            "confidence_band": "media",
            "reason": "Hay ventaja accionable, pero sin llegar al rango alto de conviccion",
        }
    return {
        "label": "Entrada prudente",
        "units": "0.50u",
        "bankroll_pct": f"{max(kelly * 100, 0.5):.1f}%",
        "confidence_band": "prudente",
        "reason": "Ventaja moderada; stake contenido",
    }


def _decorate_analysis_item(item: dict) -> dict:
    from src.league_labels import find_league_id_by_name, league_meta

    raw_league_id = item.get("league_id")
    league_id = None
    if isinstance(raw_league_id, int):
        league_id = raw_league_id
    elif isinstance(raw_league_id, str):
        try:
            league_id = int(raw_league_id.strip())
        except ValueError:
            league_id = None
    if league_id is None:
        league_id = find_league_id_by_name(item.get("league"))

    meta = league_meta(league_id) if league_id is not None else {
        "id": raw_league_id,
        "league_name": item.get("league") or "Cobertura general",
        "display_name": item.get("league") or "Cobertura general",
        "display_full": item.get("league") or "Cobertura general",
        "country_name": "Cobertura general",
        "country_code": "INT",
        "flag": "⚽",
        "region": "general",
    }
    out = dict(item)
    out["league_id"] = league_id
    out["league_meta"] = meta
    out["league_display"] = meta["display_full"]
    out["country_name"] = meta["country_name"]
    out["country_code"] = meta["country_code"]
    out["flag"] = meta["flag"]
    out["region"] = meta["region"]
    out["primary_pick"] = _derive_primary_pick(out)
    out["stake_plan"] = _derive_stake_plan(out)
    return out


def _decorate_analysis_items(items: list[dict]) -> list[dict]:
    return [_decorate_analysis_item(item) for item in (items or [])]


def _session_payload_from_request(request: Request):
    raw = request.cookies.get(config.admin_cookie_name, "")
    return verify_admin_session(raw, config.admin_session_secret, subject="admin")


def _require_admin(request: Request):
    if not config.admin_token:
        raise HTTPException(
            status_code=503,
            detail="Panel admin desactivado. Configura ADMIN_TOKEN en Railway / .env",
        )
    if not config.admin_session_secret:
        raise HTTPException(
            status_code=503,
            detail="Falta ADMIN_SESSION_SECRET para firmar sesiones administrativas.",
        )
    payload = _session_payload_from_request(request)
    if not payload:
        raise HTTPException(status_code=401, detail="Sesión administrativa no válida o expirada.")
    return payload


def _with_admin_session(response: Response):
    token = create_admin_session(
        config.admin_session_secret,
        _admin_session_max_age(),
        subject="admin",
    )
    response.set_cookie(value=token, **_admin_cookie_kwargs())
    return response


def _clear_admin_session(response: Response):
    response.delete_cookie(
        key=config.admin_cookie_name,
        path="/api/admin",
        samesite="lax",
    )
    return response


def _match_live_result_for_benchmark(pick: dict, results: list[dict]) -> dict | None:
    target_home = _normalize_text(pick.get("home"))
    target_away = _normalize_text(pick.get("away"))
    target_league_id = pick.get("league_id")
    for raw in results or []:
        item = _decorate_analysis_item(raw)
        if target_league_id and item.get("league_id") != target_league_id:
            continue
        if _normalize_text(item.get("home")) == target_home and _normalize_text(item.get("away")) == target_away:
            return item
    return None


def _benchmark_alignment(pick: dict, live_item: dict | None) -> dict:
    if not live_item:
        return {
            "status": "not_found",
            "label": "Sin cruce",
            "our_pick": None,
        }
    top = (live_item.get("value_bets") or [None])[0]
    if not top:
        return {
            "status": "watch",
            "label": "Seguimiento",
            "our_pick": {
                "market": "Radar",
                "selection": "Sin EV+ principal",
                "odds": None,
                "value": None,
            },
        }
    their_market = _normalize_text(pick.get("market"))
    their_selection = _normalize_text(pick.get("selection"))
    our_market = _normalize_text(top.get("market"))
    our_selection = _normalize_text(top.get("label") or top.get("outcome"))
    aligned = their_market == our_market and their_selection == our_selection
    return {
        "status": "aligned" if aligned else "different",
        "label": "Coincide con nuestro top" if aligned else "Lectura distinta",
        "our_pick": {
            "market": top.get("market"),
            "selection": top.get("label") or top.get("outcome"),
            "odds": top.get("odds", top.get("best_odds")),
            "value": top.get("value"),
            "confidence": (live_item.get("consensus_1x2") or {}).get("confidence"),
        },
    }


def _serialize_benchmark_pick(pick: dict) -> dict:
    live_item = _match_live_result_for_benchmark(pick, state.live.today_results or [])
    comparison = _benchmark_alignment(pick, live_item)
    decorated = dict(pick)
    if isinstance(pick.get("league_id"), int):
        from src.league_labels import league_meta

        meta = league_meta(pick["league_id"])
        decorated["league_meta"] = meta
        decorated["league_display"] = meta["display_full"]
    else:
        decorated["league_display"] = pick.get("league") or "Cobertura manual"
    decorated["comparison"] = comparison
    decorated["live_match"] = {
        "home": live_item.get("home"),
        "away": live_item.get("away"),
        "league_display": live_item.get("league_display"),
        "time": live_item.get("time"),
    } if live_item else None
    return decorated


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}


# ── Análisis en vivo (desde shared_state) ─────────────────────────────────────

@app.get("/api/analysis/live")
async def get_live_analysis():
    """
    Devuelve los resultados del análisis más reciente del bot.
    Si el shared_state está vacío, devuelve lista vacía con metadata.
    """
    from src.analysis.central_runner import next_run_utc
    from src.league_labels import league_meta

    nxt = next_run_utc()
    results = _decorate_analysis_items(state.live.today_results)
    highlights = _decorate_analysis_items(getattr(state.live, "highlight_results", []) or [])
    hero_meta = league_meta(config.hero_league_id)
    return {
        "last_run": state.live.last_run,
        "runs_today": getattr(state.live, "runs_today", 0),
        "total_value_bets": state.live.total_value_bets,
        "leagues_analyzed": state.live.leagues_analyzed,
        "report_hours_utc": list(config.report_hours_utc),
        "next_run_utc": nxt.isoformat() if nxt else None,
        "hero_league_id": config.hero_league_id,
        "hero_league_name": hero_meta["league_name"],
        "hero_league_display": hero_meta["display_full"],
        "count": len(results),
        "highlight_count": len(highlights),
        "results": results,
        "highlights": highlights,
    }


# ── Stats / Bets ──────────────────────────────────────────────────────────────

@app.get("/api/stats")
def get_stats():
    """Estadísticas globales del tracker."""
    return tracker.get_stats()


@app.get("/api/bets/recent")
def get_recent(n: int = Query(default=20, ge=1, le=100)):
    """Últimas N predicciones del tracker."""
    return tracker.get_recent(n)


@app.get("/api/bets/today")
def get_today_bets():
    """
    Value bets de hoy.
    Primero intenta shared_state (análisis en vivo del bot),
    luego cae al tracker (predicciones históricas del día).
    """
    today = datetime.now(timezone.utc).date().isoformat()

    # Preferir resultados en vivo si hay datos de hoy
    if state.live.last_run:
        last_date = state.live.last_run[:10]  # YYYY-MM-DD
        if last_date == today and state.live.today_results:
            with_value = [r for r in state.live.today_results if r.get("has_value") or r.get("value_bets")]
            return {
                "date": today,
                "source": "live",
                "last_run": state.live.last_run,
                "count": len(with_value),
                "bets": _decorate_analysis_items(with_value),
            }

    # Fallback: tracker histórico
    recent = tracker.get_recent(50)
    today_bets = [r for r in recent if r.get("date") == today]
    return {
        "date": today,
        "source": "tracker",
        "last_run": None,
        "count": len(today_bets),
        "bets": _decorate_analysis_items(today_bets),
    }


# ── Backtest ──────────────────────────────────────────────────────────────────

@app.get("/api/backtest")
def get_backtest(
    min_value: float = Query(default=0.0, ge=0),
    min_odds: float = Query(default=1.0, ge=1.0),
    max_odds: float = Query(default=99.0, le=100),
):
    """Resultados del backtesting con filtros opcionales."""
    from dataclasses import asdict
    result = backtester.run(min_value=min_value, min_odds=min_odds, max_odds=max_odds)
    d = asdict(result)
    d.pop("bets", None)
    return d


@app.get("/api/backtest/bets")
def get_backtest_bets(limit: int = Query(default=100, le=500)):
    """Lista de apuestas del backtest."""
    result = backtester.run()
    return {"bets": result.bets[-limit:], "total": result.total_bets}


# ── Calibración ───────────────────────────────────────────────────────────────

@app.get("/api/calibration")
def get_calibration():
    """Calibración del modelo por liga."""
    return calibration.compute()


@app.get("/api/calibration/{league}")
def get_calibration_league(league: str):
    stats = calibration.compute()
    if league not in stats:
        raise HTTPException(status_code=404, detail=f"Liga '{league}' sin datos suficientes.")
    return {
        "league": league,
        **stats[league],
        "ece_bins": calibration.get_ece_bins(league),
    }


# ── Bankroll / Usuarios ───────────────────────────────────────────────────────

@app.get("/api/bankroll/{user_id}")
def get_bankroll(user_id: int):
    br = bankroll_mgr.get(user_id)
    if not br:
        raise HTTPException(status_code=404, detail="Usuario sin bankroll configurado.")
    from dataclasses import asdict
    return asdict(br)


@app.get("/api/leaderboard")
def get_leaderboard():
    """Top 10 usuarios por ROI."""
    return user_mgr.leaderboard(top=10)


# ── Ligas / Mensual ───────────────────────────────────────────────────────────

@app.get("/api/leagues")
def get_leagues():
    """Lista de ligas monitoreadas (config) con su estado de calibración."""
    cal = calibration.compute()
    from src.data.odds_api import LEAGUE_TO_SPORT_KEY
    from src.league_labels import league_meta

    leagues = []
    for lid in config.target_leagues:
        meta = league_meta(lid)
        name = meta["league_name"]
        sport_key = LEAGUE_TO_SPORT_KEY.get(lid, "")
        cal_data = cal.get(name, {})
        leagues.append({
            "id": lid,
            "name": name,
            "display_name": meta["display_name"],
            "display_full": meta["display_full"],
            "country_name": meta["country_name"],
            "country_code": meta["country_code"],
            "flag": meta["flag"],
            "region": meta["region"],
            "sport_key": sport_key,
            "grade": cal_data.get("grade", "N/A"),
            "penalty_factor": cal_data.get("penalty_factor", 1.0),
            "roi": cal_data.get("roi", None),
        })
    return leagues


@app.get("/api/monthly")
def get_monthly():
    """P&L mensual acumulado."""
    result = backtester.run()
    return {"monthly": result.monthly}


# ── Admin (Premium) — acceso por sesión segura en cookie ──────────────────────

class AdminLoginBody(BaseModel):
    password: str = Field("", description="Clave administrativa")


class AdminPremiumBody(BaseModel):
    """Telegram identifica usuarios por user_id (número). El @username es opcional."""
    user_id: int = Field(..., description="ID numérico de Telegram (Settings o @userinfobot)")
    days: int = Field(30, ge=1, le=3650)
    username: str = Field("", description="Nick opcional, solo para guardar en datos")


class AdminUserIdBody(BaseModel):
    user_id: int


class AdminLineAlertsBody(BaseModel):
    user_id: int
    enabled: bool


class AdminTelegramBody(BaseModel):
    """Publicar en el chat/canal configurado en TELEGRAM_CHAT_ID."""
    mode: str = Field("summary", description="summary | custom")
    text: str = Field("", description="Si mode=custom, mensaje (HTML permitido)")


class AdminBenchmarkBody(BaseModel):
    source: str = Field(..., min_length=2, max_length=80)
    league_id: Optional[int] = None
    league: str = Field("", max_length=120)
    home: str = Field(..., min_length=2, max_length=120)
    away: str = Field(..., min_length=2, max_length=120)
    market: str = Field(..., min_length=2, max_length=80)
    selection: str = Field(..., min_length=1, max_length=120)
    odds: float = Field(..., ge=1.01, le=1000)
    kickoff_utc: str = Field("", max_length=50)
    note: str = Field("", max_length=300)


@app.get("/api/admin/status")
def admin_status(request: Request):
    """Indica si el panel admin está habilitado y si ya hay sesión activa."""
    payload = _session_payload_from_request(request)
    return {
        "admin_enabled": bool(config.admin_token),
        "auth_mode": "session_cookie",
        "authenticated": bool(payload),
    }


@app.get("/api/admin/session")
def admin_session(request: Request):
    payload = _session_payload_from_request(request)
    if not payload:
        return {
            "authenticated": False,
            "auth_mode": "session_cookie",
            "server_time_utc": datetime.now(timezone.utc).isoformat(),
        }
    return {
        "authenticated": True,
        "auth_mode": "session_cookie",
        "server_time_utc": datetime.now(timezone.utc).isoformat(),
        "session_expires_utc": datetime.fromtimestamp(payload.exp, timezone.utc).isoformat(),
    }


@app.post("/api/admin/login")
def admin_login(body: AdminLoginBody):
    if not config.admin_token:
        raise HTTPException(
            status_code=503,
            detail="Panel admin desactivado. Configura ADMIN_TOKEN en Railway / .env",
        )
    entered = str(body.password or "").strip()
    expected = str(config.admin_token or "")
    if not entered or not hmac.compare_digest(entered, expected):
        raise HTTPException(status_code=401, detail="Clave administrativa incorrecta.")

    payload = JSONResponse({
        "ok": True,
        "server_time_utc": datetime.now(timezone.utc).isoformat(),
        "message": "Acceso autorizado. Consola operativa habilitada.",
    })
    return _with_admin_session(payload)


@app.post("/api/admin/logout")
def admin_logout():
    payload = JSONResponse({
        "ok": True,
        "message": "Sesión administrativa cerrada.",
    })
    return _clear_admin_session(payload)


@app.post("/api/admin/auth/check")
def admin_auth_check(request: Request):
    """Compatibilidad: valida la sesión actual sin devolver secretos."""
    _require_admin(request)
    return {
        "ok": True,
        "server_time_utc": datetime.now(timezone.utc).isoformat(),
        "message": "Sesión administrativa activa.",
    }


@app.get("/api/admin/overview")
def admin_overview(request: Request):
    """
    Config efectiva (solo lectura; viene del .env/Railway) + estado en vivo + stats del tracker.
    No expone secretos (tokens de APIs).
    """
    _require_admin(request)
    from src.analysis.central_runner import next_run_utc
    from src.league_labels import league_meta

    leagues = []
    for lid in config.target_leagues:
        meta = league_meta(lid)
        leagues.append({
            "id": lid,
            "name": meta["league_name"],
            "display_name": meta["display_name"],
            "display_full": meta["display_full"],
            "country_name": meta["country_name"],
            "country_code": meta["country_code"],
            "flag": meta["flag"],
            "region": meta["region"],
        })

    live = state.live
    today_results = _decorate_analysis_items(live.today_results or [])
    users = user_mgr.list_users_summary()
    premium_users = [u for u in users if u.get("is_premium")]
    next_run = next_run_utc()
    runtime = analysis_run_snapshot()

    highlights_preview = []
    for item in _decorate_analysis_items((getattr(live, "highlight_results", []) or [])[:8]):
        top = (item.get("value_bets") or [None])[0]
        highlights_preview.append({
            "match_id": item.get("match_id"),
            "home": item.get("home"),
            "away": item.get("away"),
            "league": item.get("league"),
            "league_display": item.get("league_display"),
            "country_name": item.get("country_name"),
            "flag": item.get("flag"),
            "time": item.get("time"),
            "has_value": bool(item.get("has_value")),
            "max_value": item.get("max_value", 0),
            "confidence": (item.get("consensus_1x2") or {}).get("confidence", 0),
            "agreement": (item.get("consensus_1x2") or {}).get("agreement", 0),
            "top_bet": top,
            "primary_pick": item.get("primary_pick"),
            "stake_plan": item.get("stake_plan"),
        })

    recent_predictions = []
    for item in tracker.get_recent(8):
        top = (item.get("value_bets") or [None])[0]
        recent_predictions.append({
            "match_id": item.get("match_id"),
            "home": item.get("home"),
            "away": item.get("away"),
            "league": item.get("league"),
            "date": item.get("date"),
            "value_bets": [top] if top else [],
        })

    benchmark_items = [_serialize_benchmark_pick(item) for item in benchmark_store.list_picks()]
    benchmark_summary = {
        "total": len(benchmark_items),
        "aligned": sum(1 for item in benchmark_items if item["comparison"]["status"] == "aligned"),
        "different": sum(1 for item in benchmark_items if item["comparison"]["status"] == "different"),
        "watch": sum(1 for item in benchmark_items if item["comparison"]["status"] == "watch"),
        "not_found": sum(1 for item in benchmark_items if item["comparison"]["status"] == "not_found"),
    }

    return {
        "config": {
            "report_hours_utc": list(config.report_hours_utc),
            "target_leagues": leagues,
            "hero_league_id": config.hero_league_id,
            "highlight_top_n": config.highlight_top_n,
            "odds_regions": config.odds_regions,
            "telegram_publish_top_matches": config.telegram_publish_top_matches,
            "telegram_publish_match_details": config.telegram_publish_match_details,
            "auto_warmup_on_start": config.auto_warmup_on_start,
            "auto_publish_startup_report": config.auto_publish_startup_report,
            "startup_analysis_delay_sec": config.startup_analysis_delay_sec,
            "line_move_poll_interval_sec": config.line_move_poll_interval_sec,
            "admin_session_hours": config.admin_session_hours,
        },
        "server": {
            "time_utc": datetime.now(timezone.utc).isoformat(),
            "next_run_utc": next_run.isoformat() if next_run else None,
        },
        "live": {
            "last_run": live.last_run,
            "runs_today": getattr(live, "runs_today", 0),
            "matches_analyzed": len(today_results),
            "with_value": sum(1 for r in today_results if r.get("has_value")),
            "highlight_count": len(getattr(live, "highlight_results", []) or []),
            "leagues_analyzed": live.leagues_analyzed or [],
            "last_publish_utc": getattr(live, "last_publish_utc", None),
            "last_publish_kind": getattr(live, "last_publish_kind", ""),
            "last_publish_parts": getattr(live, "last_publish_parts", 0),
            "last_publish_target": getattr(live, "last_publish_target", ""),
        },
        "integrations": {
            "telegram_token_set": bool(config.telegram_token),
            "telegram_chat_id_set": bool(config.telegram_chat_id),
        },
        "analysis_job_busy": _admin_job_state["status"] in {"queued", "running"} or analysis_run_locked(),
        "analysis_job": {
            **dict(_admin_job_state),
            "runtime_owner": runtime.get("owner"),
            "runtime_started_at": runtime.get("started_at"),
        },
        "tracker": tracker.get_stats(),
        "users": {
            "total": len(users),
            "premium": len(premium_users),
            "free": len(users) - len(premium_users),
        },
        "benchmark": benchmark_summary,
        "highlights_preview": highlights_preview,
        "recent_predictions": recent_predictions,
    }


@app.get("/api/admin/users")
def admin_list_users(request: Request):
    _require_admin(request)
    return {"users": user_mgr.list_users_summary()}


@app.post("/api/admin/premium")
def admin_set_premium(
    body: AdminPremiumBody,
    request: Request,
):
    _require_admin(request)
    user = user_mgr.get_or_create(body.user_id, body.username.strip())
    updated = user_mgr.activate_premium(user.user_id, days=body.days)
    return {
        "ok": True,
        "user_id": body.user_id,
        "days_added": body.days,
        "premium_until": updated.premium_until,
    }


@app.post("/api/admin/premium/revoke")
def admin_revoke_premium(
    body: AdminUserIdBody,
    request: Request,
):
    _require_admin(request)
    user_mgr.deactivate_premium(body.user_id)
    return {"ok": True, "user_id": body.user_id}


@app.post("/api/admin/users/line-alerts")
def admin_set_line_alerts(
    body: AdminLineAlertsBody,
    request: Request,
):
    _require_admin(request)
    user_mgr.get_or_create(body.user_id)
    try:
        user_mgr.set_line_alerts(body.user_id, body.enabled)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"ok": True, "user_id": body.user_id, "enabled": body.enabled}


@app.get("/api/admin/benchmark")
def admin_benchmark_list(request: Request):
    _require_admin(request)
    picks = [_serialize_benchmark_pick(item) for item in benchmark_store.list_picks()]
    return {
        "picks": picks,
        "summary": {
            "total": len(picks),
            "aligned": sum(1 for item in picks if item["comparison"]["status"] == "aligned"),
            "different": sum(1 for item in picks if item["comparison"]["status"] == "different"),
            "watch": sum(1 for item in picks if item["comparison"]["status"] == "watch"),
            "not_found": sum(1 for item in picks if item["comparison"]["status"] == "not_found"),
        },
    }


@app.post("/api/admin/benchmark")
def admin_benchmark_add(body: AdminBenchmarkBody, request: Request):
    _require_admin(request)
    item = benchmark_store.add_pick({
        "source": body.source,
        "league_id": body.league_id,
        "league": body.league,
        "home": body.home,
        "away": body.away,
        "market": body.market,
        "selection": body.selection,
        "odds": body.odds,
        "kickoff_utc": body.kickoff_utc or datetime.now(timezone.utc).isoformat(),
        "note": body.note,
    })
    return {"ok": True, "item": _serialize_benchmark_pick(item)}


@app.delete("/api/admin/benchmark/{pick_id}")
def admin_benchmark_delete(pick_id: str, request: Request):
    _require_admin(request)
    deleted = benchmark_store.delete_pick(pick_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Comparativa no encontrada.")
    return {"ok": True, "pick_id": pick_id}


@app.post("/api/admin/analysis/run")
async def admin_run_analysis(request: Request):
    """Ejecuta el mismo pipeline que el scheduler (todas las ligas) y actualiza caché."""
    _require_admin(request)
    if _admin_job_state["status"] in {"queued", "running"} or analysis_run_locked():
        runtime = analysis_run_snapshot()
        owner = runtime.get("owner") or "otro proceso"
        return JSONResponse(
            {
                "ok": True,
                "already_running": True,
                "owner": owner,
                "started_at": runtime.get("started_at"),
                "message": f"Ya hay un análisis en curso ({owner}). Cuando termine, la caché y el tablero se actualizarán solos.",
            },
            status_code=202,
        )
    if not try_start_analysis_run("admin"):
        runtime = analysis_run_snapshot()
        owner = runtime.get("owner") or "otro proceso"
        return JSONResponse(
            {
                "ok": True,
                "already_running": True,
                "owner": owner,
                "started_at": runtime.get("started_at"),
                "message": f"Ya hay un análisis en curso ({owner}). Cuando termine, la caché y el tablero se actualizarán solos.",
            },
            status_code=202,
        )

    _admin_job_state.update({
        "status": "queued",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "error": None,
        "last_result_count": 0,
    })

    async def _wrapped():
        try:
            _admin_job_state["status"] = "running"
            from src.analysis.central_runner import run_full_analysis

            payload = await run_full_analysis()
            state.update(
                payload["results"],
                payload["leagues_done"],
                payload["highlights"],
            )
            _admin_job_state.update({
                "status": "success",
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "error": None,
                "last_result_count": len(payload["results"]),
            })
            logger.info("Análisis admin completado: %s partidos", len(payload["results"]))
        except Exception as exc:
            _admin_job_state.update({
                "status": "error",
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "error": str(exc),
            })
            logger.exception("Análisis admin fallido: %s", exc)
        finally:
            finish_analysis_run()

    asyncio.create_task(_wrapped())
    return {"ok": True, "message": "Análisis iniciado en segundo plano (puede tardar varios minutos)."}


@app.post("/api/admin/telegram/publish")
def admin_telegram_publish(
    request: Request,
    body: AdminTelegramBody = Body(default_factory=lambda: AdminTelegramBody()),
):
    """Envía un mensaje al chat/canal del bot (TELEGRAM_CHAT_ID)."""
    _require_admin(request)
    if not config.telegram_token or not config.telegram_chat_id:
        raise HTTPException(
            status_code=503,
            detail="Configura TELEGRAM_TOKEN y TELEGRAM_CHAT_ID en el servidor.",
        )

    extra_messages = []
    if body.mode == "custom":
        msg = (body.text or "").strip()
        if not msg:
            raise HTTPException(status_code=400, detail="Modo custom: el texto no puede estar vacío.")
        publish_kind = "admin_custom"
    else:
        from src.analysis.central_runner import next_run_utc
        from src.bot.formatter import format_channel_bulletin, format_match
        from src.league_labels import league_meta

        live = state.live
        highlights = _decorate_analysis_items(getattr(live, "highlight_results", []) or [])
        if not live.today_results:
            raise HTTPException(
                status_code=400,
                detail="No hay análisis en caché. Ejecuta “Forzar análisis” primero o espera al cron.",
            )
        value_count = sum(1 for r in live.today_results if r.get("has_value"))
        nxt = next_run_utc()
        msg = format_channel_bulletin(
            highlights,
            len(live.today_results),
            value_count,
            leagues_done=live.leagues_analyzed or [],
            last_run=live.last_run or "",
            next_run=nxt.isoformat() if nxt else "",
            hero_league=league_meta(config.hero_league_id)["display_full"],
        )
        if config.telegram_publish_match_details:
            detail_candidates = [r for r in highlights if r.get("has_value")] or highlights
            extra_messages = [
                format_match(match)
                for match in detail_candidates[: config.telegram_publish_top_matches]
            ]
        publish_kind = "admin_summary"

    url = f"https://api.telegram.org/bot{config.telegram_token}/sendMessage"
    parts_sent = 0
    messages = [msg] + extra_messages
    for message in messages:
        chunks = [message[i : i + 4000] for i in range(0, len(message), 4000)] or [message]
        for part in chunks:
            r = requests.post(
                url,
                json={
                    "chat_id": config.telegram_chat_id,
                    "text": part,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=45,
            )
            if r.status_code != 200:
                try:
                    detail = r.json()
                except Exception:
                    detail = r.text
                raise HTTPException(status_code=502, detail=f"Telegram: {detail}")
            parts_sent += 1
    state.record_publish(publish_kind, parts_sent, target=str(config.telegram_chat_id))
    return {"ok": True, "parts_sent": parts_sent}


# ── Servir React SPA ──────────────────────────────────────────────────────────

_FRONTEND_BUILD = Path(__file__).parent.parent.parent / "frontend" / "build"


def _setup_static():
    """Monta los archivos estáticos de React si el build existe."""
    if _FRONTEND_BUILD.exists():
        # Archivos estáticos (JS, CSS, imágenes)
        static_dir = _FRONTEND_BUILD / "static"
        if static_dir.exists():
            app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        # SPA fallback — todas las rutas no-API sirven index.html
        @app.get("/{full_path:path}")
        def spa_fallback(full_path: str):
            index = _FRONTEND_BUILD / "index.html"
            if index.exists():
                return FileResponse(str(index))
            return JSONResponse({"error": "Frontend not built"}, status_code=404)
    else:
        logger.warning("Frontend build not found at %s — dashboard no disponible", _FRONTEND_BUILD)

        @app.get("/")
        def root():
            return {
                "service": "Football Value Bot V3 API",
                "docs": "/docs",
                "health": "/api/health",
            }


_setup_static()


# ── Runner ────────────────────────────────────────────────────────────────────

def run_api(host: str = "0.0.0.0", port: int = 8000):
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="info")
