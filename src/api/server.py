"""
Feature #6 — API REST (FastAPI)
Expone los datos del bot al dashboard web React en tiempo real.
Endpoints: /bets/today, /stats, /backtest, /leagues, /calibration
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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

# Cache simple en memoria (refrescada cada llamada GET)
_today_cache: dict = {"data": [], "ts": None}


@app.get("/health")
def health():
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}


@app.get("/stats")
def get_stats():
    """Estadísticas globales del tracker."""
    return tracker.get_stats()


@app.get("/bets/recent")
def get_recent(n: int = Query(default=20, ge=1, le=100)):
    """Últimas N predicciones del tracker."""
    return tracker.get_recent(n)


@app.get("/bets/today")
def get_today_bets():
    """Value bets de hoy (desde tracker, partidos de hoy)."""
    today = datetime.now(timezone.utc).date().isoformat()
    recent = tracker.get_recent(50)
    today_bets = [r for r in recent if r.get("date") == today]
    return {"date": today, "count": len(today_bets), "bets": today_bets}


@app.get("/backtest")
def get_backtest(
    min_value: float = Query(default=0.0, ge=0),
    min_odds: float = Query(default=1.0, ge=1.0),
    max_odds: float = Query(default=99.0, le=100),
):
    """Resultados del backtesting con filtros opcionales."""
    from dataclasses import asdict
    result = backtester.run(min_value=min_value, min_odds=min_odds, max_odds=max_odds)
    d = asdict(result)
    d.pop("bets", None)  # omitir lista completa por tamaño
    return d


@app.get("/backtest/bets")
def get_backtest_bets(limit: int = Query(default=100, le=500)):
    """Lista de apuestas del backtest (sin recalcular métricas)."""
    result = backtester.run()
    return {"bets": result.bets[-limit:], "total": result.total_bets}


@app.get("/calibration")
def get_calibration():
    """Calibración del modelo por liga."""
    return calibration.compute()


@app.get("/calibration/{league}")
def get_calibration_league(league: str):
    stats = calibration.compute()
    if league not in stats:
        raise HTTPException(status_code=404, detail=f"Liga '{league}' sin datos suficientes.")
    return {
        "league": league,
        **stats[league],
        "ece_bins": calibration.get_ece_bins(league),
    }


@app.get("/bankroll/{user_id}")
def get_bankroll(user_id: int):
    br = bankroll_mgr.get(user_id)
    if not br:
        raise HTTPException(status_code=404, detail="Usuario sin bankroll configurado.")
    from dataclasses import asdict
    return asdict(br)


@app.get("/leaderboard")
def get_leaderboard():
    """Top 10 usuarios por ROI (para canal público)."""
    return user_mgr.leaderboard(top=10)


@app.get("/leagues")
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


@app.get("/monthly")
def get_monthly():
    """P&L mensual acumulado."""
    stats = tracker.get_stats()
    result = backtester.run()
    return {"monthly": result.monthly}


def run_api(host: str = "0.0.0.0", port: int = 8000):
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="info")
