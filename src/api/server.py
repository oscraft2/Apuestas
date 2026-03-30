"""
API REST (FastAPI) — Football Value Bot V3
Endpoints bajo /api/... + sirve el dashboard React como SPA.
"""
import logging
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse

import src.shared_state as state
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
    return {
        "last_run": state.live.last_run,
        "total_value_bets": state.live.total_value_bets,
        "leagues_analyzed": state.live.leagues_analyzed,
        "count": len(state.live.today_results),
        "results": state.live.today_results,
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
    """Lista de ligas monitoreadas con su estado de calibración."""
    cal = calibration.compute()
    from src.data.odds_api import LEAGUE_TO_SPORT_KEY
    leagues = []
    for lid, name in {
        39: "Premier League", 140: "La Liga", 135: "Serie A",
        78: "Bundesliga", 61: "Ligue 1", 2: "Champions League",
    }.items():
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
