"""
API REST (FastAPI) — Football Value Bot V3
Endpoints bajo /api/... + sirve el dashboard React como SPA.
"""
import logging
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
from pydantic import BaseModel, Field

from fastapi import Body, FastAPI, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse

import src.shared_state as state
from src.analysis.runtime import finish as finish_analysis_run
from src.analysis.runtime import locked as analysis_run_locked
from src.analysis.runtime import snapshot as analysis_run_snapshot
from src.analysis.runtime import try_start as try_start_analysis_run
from src.tracking.tracker import PredictionTracker
from src.backtest.backtester import Backtester
from src.analytics.calibration import LeagueCalibration
from src.bankroll.manager import BankrollManager
from src.users.manager import UserManager
from config import _normalize_secret, config

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Football Value Bot V3 API",
    description="API REST para el dashboard ValueXPro",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

tracker = PredictionTracker()
backtester = Backtester(f"{config.predictions_dir}/predictions.jsonl")
calibration = LeagueCalibration()
bankroll_mgr = BankrollManager()
user_mgr = UserManager()

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
    from src.league_labels import LEAGUE_NAMES

    nxt = next_run_utc()
    return {
        "last_run": state.live.last_run,
        "runs_today": getattr(state.live, "runs_today", 0),
        "total_value_bets": state.live.total_value_bets,
        "leagues_analyzed": state.live.leagues_analyzed,
        "report_hours_utc": list(config.report_hours_utc),
        "next_run_utc": nxt.isoformat() if nxt else None,
        "hero_league_id": config.hero_league_id,
        "hero_league_name": LEAGUE_NAMES.get(config.hero_league_id, f"Liga {config.hero_league_id}"),
        "count": len(state.live.today_results),
        "highlight_count": len(getattr(state.live, "highlight_results", []) or []),
        "results": state.live.today_results,
        "highlights": getattr(state.live, "highlight_results", []) or [],
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
                "bets": with_value,
            }

    # Fallback: tracker histórico
    recent = tracker.get_recent(50)
    today_bets = [r for r in recent if r.get("date") == today]
    return {
        "date": today,
        "source": "tracker",
        "last_run": None,
        "count": len(today_bets),
        "bets": today_bets,
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
    from src.league_labels import LEAGUE_NAMES

    leagues = []
    for lid in config.target_leagues:
        name = LEAGUE_NAMES.get(lid, f"League {lid}")
        sport_key = LEAGUE_TO_SPORT_KEY.get(lid, "")
        cal_data = cal.get(name, {})
        leagues.append({
            "id": lid,
            "name": name,
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


# ── Admin (Premium) — requiere ADMIN_TOKEN en el servidor ─────────────────────

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


def _require_admin(x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token")) -> None:
    if not config.admin_token:
        raise HTTPException(
            status_code=503,
            detail="Panel admin desactivado. Configura ADMIN_TOKEN en Railway / .env",
        )
    got = _normalize_secret(x_admin_token or "")
    expected = _normalize_secret(config.admin_token or "")
    if not got or got != expected:
        raise HTTPException(status_code=401, detail="Token de administrador incorrecto.")


@app.get("/api/admin/status")
def admin_status():
    """Indica si el panel admin está habilitado (sin exponer el token)."""
    return {"admin_enabled": bool(config.admin_token)}


@app.post("/api/admin/auth/check")
def admin_auth_check(x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token")):
    """Valida el token del panel sin devolver secretos."""
    _require_admin(x_admin_token)
    return {
        "ok": True,
        "server_time_utc": datetime.now(timezone.utc).isoformat(),
        "message": "Token válido. Panel administrativo habilitado.",
    }


@app.get("/api/admin/overview")
def admin_overview(x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token")):
    """
    Config efectiva (solo lectura; viene del .env/Railway) + estado en vivo + stats del tracker.
    No expone secretos (tokens de APIs).
    """
    _require_admin(x_admin_token)
    from src.analysis.central_runner import next_run_utc
    from src.league_labels import LEAGUE_NAMES

    leagues = [
        {"id": lid, "name": LEAGUE_NAMES.get(lid, f"Liga {lid}")}
        for lid in config.target_leagues
    ]
    live = state.live
    today_results = live.today_results or []
    users = user_mgr.list_users_summary()
    premium_users = [u for u in users if u.get("is_premium")]
    next_run = next_run_utc()
    runtime = analysis_run_snapshot()

    highlights_preview = []
    for item in (getattr(live, "highlight_results", []) or [])[:8]:
        top = (item.get("value_bets") or [None])[0]
        highlights_preview.append({
            "match_id": item.get("match_id"),
            "home": item.get("home"),
            "away": item.get("away"),
            "league": item.get("league"),
            "time": item.get("time"),
            "has_value": bool(item.get("has_value")),
            "max_value": item.get("max_value", 0),
            "confidence": (item.get("consensus_1x2") or {}).get("confidence", 0),
            "agreement": (item.get("consensus_1x2") or {}).get("agreement", 0),
            "top_bet": top,
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
        "highlights_preview": highlights_preview,
        "recent_predictions": recent_predictions,
    }


@app.get("/api/admin/users")
def admin_list_users(x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token")):
    _require_admin(x_admin_token)
    return {"users": user_mgr.list_users_summary()}


@app.post("/api/admin/premium")
def admin_set_premium(
    body: AdminPremiumBody,
    x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
):
    _require_admin(x_admin_token)
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
    x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
):
    _require_admin(x_admin_token)
    user_mgr.deactivate_premium(body.user_id)
    return {"ok": True, "user_id": body.user_id}


@app.post("/api/admin/users/line-alerts")
def admin_set_line_alerts(
    body: AdminLineAlertsBody,
    x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
):
    _require_admin(x_admin_token)
    user_mgr.get_or_create(body.user_id)
    try:
        user_mgr.set_line_alerts(body.user_id, body.enabled)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"ok": True, "user_id": body.user_id, "enabled": body.enabled}


class AdminTelegramBody(BaseModel):
    """Publicar en el chat/canal configurado en TELEGRAM_CHAT_ID."""
    mode: str = Field("summary", description="summary | custom")
    text: str = Field("", description="Si mode=custom, mensaje (HTML permitido)")


@app.post("/api/admin/analysis/run")
async def admin_run_analysis(
    x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
):
    """Ejecuta el mismo pipeline que el scheduler (todas las ligas) y actualiza caché."""
    _require_admin(x_admin_token)
    if _admin_job_state["status"] in {"queued", "running"} or analysis_run_locked():
        runtime = analysis_run_snapshot()
        owner = runtime.get("owner") or "otro proceso"
        raise HTTPException(status_code=409, detail=f"Ya hay un análisis en curso ({owner}). Espera a que termine.")
    if not try_start_analysis_run("admin"):
        runtime = analysis_run_snapshot()
        owner = runtime.get("owner") or "otro proceso"
        raise HTTPException(status_code=409, detail=f"Ya hay un análisis en curso ({owner}). Espera a que termine.")

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
    body: AdminTelegramBody = Body(default_factory=lambda: AdminTelegramBody()),
    x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
):
    """Envía un mensaje al chat/canal del bot (TELEGRAM_CHAT_ID)."""
    _require_admin(x_admin_token)
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
        from src.league_labels import LEAGUE_NAMES

        live = state.live
        highlights = getattr(live, "highlight_results", []) or []
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
            hero_league=LEAGUE_NAMES.get(config.hero_league_id, ""),
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
