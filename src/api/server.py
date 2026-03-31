"""
API REST — Football Value Bot V3
Endpoints bajo /api/... + Stripe webhook + seguridad + SPA React.
"""
import logging
import hmac
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse

import src.shared_state as state
from src.tracking.tracker import PredictionTracker
from src.backtest.backtester import Backtester
from src.analytics.calibration import LeagueCalibration
from src.bankroll.manager import BankrollManager
from src.users.manager import UserManager
from src.db.models import StripeEvent
from src.db.database import SessionLocal
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

tracker      = PredictionTracker()
calibration  = LeagueCalibration()
bankroll_mgr = BankrollManager()
user_mgr     = UserManager()

# Backtester lee de DB via tracker
def _backtester():
    return Backtester(f"{config.predictions_dir}/predictions.jsonl")


# ── Seguridad ─────────────────────────────────────────────────────────────────

def _verify_api_key(x_api_key: Optional[str] = Header(default=None)):
    """Protege endpoints de escritura. Omitir si API_SECRET_KEY no está configurada."""
    if not config.api_secret_key:
        return  # sin clave configurada, endpoint abierto (solo desarrollo)
    if x_api_key != config.api_secret_key:
        raise HTTPException(status_code=401, detail="API key inválida")


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {
        "status":   "ok",
        "ts":       datetime.now(timezone.utc).isoformat(),
        "db":       "postgresql" if "postgresql" in (config.database_url or "") else "sqlite",
        "stripe":   bool(config.stripe_secret_key),
    }


# ── Análisis en vivo ──────────────────────────────────────────────────────────

@app.get("/api/analysis/live")
def get_live_analysis():
    return {
        "last_run":         state.live.last_run,
        "total_value_bets": state.live.total_value_bets,
        "leagues_analyzed": state.live.leagues_analyzed,
        "count":            len(state.live.today_results),
        "results":          state.live.today_results,
    }


# ── Bets / Stats ──────────────────────────────────────────────────────────────

@app.get("/api/stats")
def get_stats():
    return tracker.get_stats()


@app.get("/api/bets/recent")
def get_recent(n: int = Query(default=20, ge=1, le=100)):
    return tracker.get_recent(n)


@app.get("/api/bets/today")
def get_today_bets():
    today = datetime.now(timezone.utc).date().isoformat()

    # Preferir shared_state si tiene datos de hoy
    if state.live.last_run and state.live.last_run[:10] == today and state.live.today_results:
        with_value = [r for r in state.live.today_results if r.get("has_value") or r.get("value_bets")]
        return {
            "date":     today,
            "source":   "live",
            "last_run": state.live.last_run,
            "count":    len(with_value),
            "bets":     with_value,
        }

    # Fallback: DB
    today_preds = tracker.get_today()
    return {
        "date":     today,
        "source":   "db",
        "last_run": None,
        "count":    len(today_preds),
        "bets":     today_preds,
    }


@app.get("/api/bets/pending")
def get_pending():
    """Apuestas pendientes de resultado (para actualizar manualmente)."""
    return tracker.get_pending()


# ── Resultados (actualización manual o webhook externo) ───────────────────────

@app.post("/api/results")
def post_result(payload: dict, _: None = Depends(_verify_api_key)):
    """
    Registra el resultado de una apuesta.
    Body: { match_id, market, outcome, won: bool, pnl?: float }
    """
    match_id = payload.get("match_id", "")
    market   = payload.get("market", "")
    outcome  = payload.get("outcome", "")
    won      = payload.get("won")
    pnl      = payload.get("pnl")

    if not all([match_id, market, outcome, won is not None]):
        raise HTTPException(status_code=400, detail="Faltan campos: match_id, market, outcome, won")

    ok = tracker.log_result(match_id, market, outcome, bool(won), pnl)
    if not ok:
        raise HTTPException(status_code=404, detail="Predicción no encontrada o ya actualizada")
    return {"ok": True, "match_id": match_id, "market": market, "outcome": outcome, "won": won}


# ── Backtest ──────────────────────────────────────────────────────────────────

@app.get("/api/backtest")
def get_backtest(
    min_value: float = Query(default=0.0, ge=0),
    min_odds:  float = Query(default=1.0, ge=1.0),
    max_odds:  float = Query(default=99.0, le=100),
):
    from dataclasses import asdict
    result = _backtester().run(min_value=min_value, min_odds=min_odds, max_odds=max_odds)
    d = asdict(result)
    d.pop("bets", None)
    return d


@app.get("/api/backtest/bets")
def get_backtest_bets(limit: int = Query(default=100, le=500)):
    result = _backtester().run()
    return {"bets": result.bets[-limit:], "total": result.total_bets}


# ── Calibración ───────────────────────────────────────────────────────────────

@app.get("/api/calibration")
def get_calibration():
    return calibration.compute()


@app.get("/api/calibration/{league}")
def get_calibration_league(league: str):
    stats = calibration.compute()
    if league not in stats:
        raise HTTPException(status_code=404, detail=f"Liga '{league}' sin datos suficientes")
    return {"league": league, **stats[league], "ece_bins": calibration.get_ece_bins(league)}


# ── Bankroll / Usuarios ───────────────────────────────────────────────────────

@app.get("/api/bankroll/{user_id}")
def get_bankroll(user_id: int):
    br = bankroll_mgr.get(user_id)
    if not br:
        raise HTTPException(status_code=404, detail="Usuario sin bankroll configurado")
    return {
        "user_id":      br.user_id,
        "currency":     br.currency,
        "initial":      br.initial,
        "current":      br.current,
        "pnl":          br.pnl,
        "roi":          br.roi,
        "bets_placed":  br.bets_placed,
        "bets_won":     br.bets_won,
        "total_staked": br.total_staked,
    }


@app.get("/api/leaderboard")
def get_leaderboard():
    return user_mgr.leaderboard(top=10)


@app.get("/api/leagues")
def get_leagues():
    cal = calibration.compute()
    from src.data.odds_api import LEAGUE_TO_SPORT_KEY
    leagues = []
    for lid, name in {
        39: "Premier League", 140: "La Liga", 135: "Serie A",
        78: "Bundesliga", 61: "Ligue 1", 2: "Champions League",
    }.items():
        cal_data = cal.get(name, {})
        leagues.append({
            "id":             lid,
            "name":           name,
            "sport_key":      LEAGUE_TO_SPORT_KEY.get(lid, ""),
            "grade":          cal_data.get("grade", "N/A"),
            "penalty_factor": cal_data.get("penalty_factor", 1.0),
            "roi":            cal_data.get("roi"),
        })
    return leagues


@app.get("/api/monthly")
def get_monthly():
    result = _backtester().run()
    return {"monthly": result.monthly}


# ── Stripe ────────────────────────────────────────────────────────────────────

@app.post("/api/stripe/checkout")
async def create_checkout(request: Request, _: None = Depends(_verify_api_key)):
    """
    Crea una sesión de checkout de Stripe.
    Body: { user_id: int, success_url: str, cancel_url: str }
    """
    if not config.stripe_secret_key or not config.stripe_price_id:
        raise HTTPException(status_code=503, detail="Stripe no configurado")

    import stripe
    stripe.api_key = config.stripe_secret_key

    body = await request.json()
    user_id     = body.get("user_id")
    success_url = body.get("success_url", "https://t.me/valuexpro_bot")
    cancel_url  = body.get("cancel_url",  "https://t.me/valuexpro_bot")

    if not user_id:
        raise HTTPException(status_code=400, detail="Falta user_id")

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{"price": config.stripe_price_id, "quantity": 1}],
        mode="subscription",
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"telegram_user_id": str(user_id)},
    )
    return {"url": session.url, "session_id": session.id}


@app.post("/api/stripe/webhook")
async def stripe_webhook(request: Request):
    """
    Webhook de Stripe. Activa premium al recibir checkout.session.completed.
    """
    if not config.stripe_secret_key:
        raise HTTPException(status_code=503, detail="Stripe no configurado")

    import stripe
    stripe.api_key = config.stripe_secret_key

    payload    = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, config.stripe_webhook_secret
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Firma Stripe inválida")

    # Idempotencia: evitar procesar el mismo evento dos veces
    with SessionLocal() as db:
        exists = db.query(StripeEvent).filter(StripeEvent.event_id == event["id"]).first()
        if exists:
            return {"ok": True, "skipped": True}
        db.add(StripeEvent(event_id=event["id"], event_type=event["type"]))
        db.commit()

    if event["type"] == "checkout.session.completed":
        session     = event["data"]["object"]
        telegram_id = int(session.get("metadata", {}).get("telegram_user_id", 0))
        customer_id = session.get("customer", "")
        sub_id      = session.get("subscription", "")

        if telegram_id:
            try:
                user = user_mgr.activate_premium(
                    telegram_id, days=30,
                    stripe_customer_id=customer_id,
                    stripe_sub_id=sub_id,
                )
                logger.info("Premium activado via Stripe: user=%s sub=%s", telegram_id, sub_id)
                # Notificar al usuario por Telegram (fire-and-forget)
                _notify_premium_activated(telegram_id)
            except KeyError:
                # Usuario aún no existe en DB — lo creamos y activamos
                user_mgr.get_or_create(telegram_id)
                user_mgr.activate_premium(telegram_id, days=30,
                                          stripe_customer_id=customer_id,
                                          stripe_sub_id=sub_id)

    elif event["type"] == "customer.subscription.deleted":
        customer_id = event["data"]["object"].get("customer", "")
        if customer_id:
            user = user_mgr.get_by_stripe_customer(customer_id)
            if user:
                user_mgr.deactivate_premium(user.user_id)
                logger.info("Premium cancelado via Stripe: user=%s", user.user_id)

    # Marcar como procesado
    with SessionLocal() as db:
        ev = db.query(StripeEvent).filter(StripeEvent.event_id == event["id"]).first()
        if ev:
            ev.processed = True
            db.commit()

    return {"ok": True}


def _notify_premium_activated(user_id: int):
    """Envía notificación de bienvenida premium por Telegram (best-effort)."""
    try:
        import asyncio, requests as req
        msg = (
            "🎉 <b>¡Bienvenido a Premium!</b>\n\n"
            "Tu suscripción está activa por 30 días.\n\n"
            "✅ Value bets ilimitadas\n"
            "✅ Alertas de movimiento de cuota\n"
            "✅ Bankroll + Kelly personalizado\n"
            "✅ Backtesting + calibración\n\n"
            "Usa /perfil para ver tu estado."
        )
        req.post(
            f"https://api.telegram.org/bot{config.telegram_token}/sendMessage",
            json={"chat_id": user_id, "text": msg, "parse_mode": "HTML"},
            timeout=5,
        )
    except Exception:
        pass


# ── Admin endpoints ───────────────────────────────────────────────────────────

@app.get("/api/admin/users")
def admin_list_users(_: None = Depends(_verify_api_key)):
    users = user_mgr.list_users(limit=100)
    return [
        {
            "user_id":       u.user_id,
            "username":      u.username,
            "tier":          u.tier,
            "premium_until": u.premium_until.isoformat() if u.premium_until else None,
            "alerts_today":  u.alerts_today,
            "total_alerts":  u.total_alerts_sent,
            "joined_at":     u.joined_at.isoformat() if u.joined_at else None,
        }
        for u in users
    ]


@app.post("/api/admin/premium")
def admin_activate_premium(payload: dict, _: None = Depends(_verify_api_key)):
    """Body: { user_id: int, days: int }"""
    user_id = payload.get("user_id")
    days    = payload.get("days", 30)
    if not user_id:
        raise HTTPException(status_code=400, detail="Falta user_id")
    try:
        user_mgr.activate_premium(int(user_id), days=int(days))
    except KeyError:
        user_mgr.get_or_create(int(user_id))
        user_mgr.activate_premium(int(user_id), days=int(days))
    return {"ok": True, "user_id": user_id, "days": days}


# ── SPA React ─────────────────────────────────────────────────────────────────

_FRONTEND_BUILD = Path(__file__).parent.parent.parent / "frontend" / "build"


def _setup_static():
    if _FRONTEND_BUILD.exists():
        static_dir = _FRONTEND_BUILD / "static"
        if static_dir.exists():
            app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        @app.get("/{full_path:path}")
        def spa_fallback(full_path: str):
            index = _FRONTEND_BUILD / "index.html"
            if index.exists():
                return FileResponse(str(index))
            return JSONResponse({"error": "Frontend no disponible"}, status_code=404)
    else:
        @app.get("/")
        def root():
            return {"service": "Football Value Bot V3 API", "docs": "/docs"}


_setup_static()


def run_api(host: str = "0.0.0.0", port: int = 8000):
    import uvicorn
    uvicorn.run(app, host=host, port=port, loop="asyncio", log_level="info")
