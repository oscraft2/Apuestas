"""
API REST — Football Value Bot V3
Endpoints bajo /api/... + Stripe webhook + seguridad + SPA React.
"""
import logging
import asyncio
import hmac
import hashlib
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request, Header, Depends
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
from src.db.models import StripeEvent
from src.db.database import SessionLocal
from config import config

logger = logging.getLogger(__name__)


def _should_run_scheduled_hour_utc() -> bool:
    """Una pasada por ventana horaria (min 0–4 UTC) en report_hours_utc, sin duplicar la misma hora."""
    now = datetime.now(timezone.utc)
    hours = sorted(set(getattr(config, "report_hours_utc", [8, 15, 22])))
    if now.hour not in hours:
        return False
    if now.minute > 4:
        return False
    lr = state.live.last_run
    if not lr:
        return True
    try:
        last = datetime.fromisoformat(lr.replace("Z", "+00:00"))
    except Exception:
        return True
    if last.date() == now.date() and last.hour == now.hour:
        return False
    return True


async def _run_central_and_update() -> None:
    """Misma carga que el scheduler del bot / admin run."""
    if not try_start_analysis_run("api_central"):
        logger.debug("Análisis central omitido: ya hay otro en curso")
        return
    try:
        from src.analysis.central_runner import run_full_analysis

        payload = await run_full_analysis()
        state.update(
            payload["results"],
            payload["leagues_done"],
            payload["highlights"],
            payload.get("leaders"),
            payload.get("mixes"),
        )
        logger.info(
            "Análisis central OK: %s partidos · %s destacados · %s Prime",
            len(payload.get("results") or []),
            len(payload.get("highlights") or []),
            len(payload.get("leaders") or []),
        )
    except Exception:
        logger.exception("Fallo ejecutando análisis central desde la API")
    finally:
        finish_analysis_run()


async def _api_startup_warmup():
    delay = max(3, int(getattr(config, "startup_analysis_delay_sec", 20)))
    await asyncio.sleep(delay)
    if not getattr(config, "auto_warmup_on_start", True):
        return
    from src.shared_state import is_cache_ready_today

    if is_cache_ready_today():
        logger.info("API: caché de análisis ya cargada para hoy — warmup omitido")
        return
    logger.info("API: ejecutando warmup de análisis (dashboard sin datos previos)")
    await _run_central_and_update()


async def _api_scheduled_loop():
    """Replica REPORT_HOURS_UTC cuando solo existe el proceso uvicorn (sin bot Telegram)."""
    await asyncio.sleep(75)
    while True:
        await asyncio.sleep(60)
        if not getattr(config, "api_schedule_central", True):
            continue
        if not _should_run_scheduled_hour_utc():
            continue
        logger.info("API scheduler: ventana horaria — ejecutando análisis central")
        await _run_central_and_update()


@asynccontextmanager
async def _lifespan(_: FastAPI):
    try:
        from src.analysis.live_snapshot import restore_live_snapshot

        restore_live_snapshot()
    except Exception as exc:
        logger.warning("No se pudo restaurar snapshot de análisis: %s", exc)
    asyncio.create_task(_api_startup_warmup())
    if getattr(config, "api_schedule_central", True):
        asyncio.create_task(_api_scheduled_loop())
    yield


app = FastAPI(
    title="Football Value Bot V3 API",
    description="API REST para el dashboard ValueXPro",
    version="3.0.0",
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
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


def _market_focus_labels(meta: dict) -> list[str]:
    bias = meta.get("market_bias") or {}
    focus = []
    if any(key.startswith("O/U 1.5:over") or key.startswith("O/U 2.5:over") for key, value in bias.items() if value > 1.04):
        focus.append("over")
    if any(key.startswith("O/U 2.5:under") for key, value in bias.items() if value > 1.04):
        focus.append("under")
    if any(key.startswith("BTTS:yes") for key, value in bias.items() if value > 1.04):
        focus.append("btts")
    if any(key.startswith("BTTS:no") for key, value in bias.items() if value > 1.04):
        focus.append("no-btts")
    return focus or ["balanceado"]


def _best_market_odds(item: dict, market_label: str, outcome: str):
    market_data = item.get("market") or {}
    if market_label == "1X2":
        return ((market_data.get("h2h") or {}).get("best_odds") or {}).get(outcome)
    if market_label == "Totales 2.5":
        raw = market_data.get("ou25") or market_data.get("ou") or {}
        return raw.get("best_over") if outcome == "over" else raw.get("best_under")
    if market_label == "O/U 1.5":
        raw = market_data.get("ou15") or {}
        return raw.get("best_over") if outcome == "over" else raw.get("best_under")
    if market_label == "BTTS":
        raw = market_data.get("btts") or {}
        return raw.get("best_yes") if outcome == "yes" else raw.get("best_no")
    return None


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
        "odds": _best_market_odds(item, "1X2", outcome) or (c1.get("fair_odds") or {}).get(outcome),
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
        "odds": _best_market_odds(item, "Totales 2.5", outcome) or (cou.get("fair_odds") or {}).get(outcome),
        "source": "consensus",
    }


def _recommendation_from_binary(item: dict, consensus_key: str, market_label: str, label_map: dict[str, str]) -> dict | None:
    consensus = item.get(consensus_key) or {}
    probs = consensus.get("probs") or {}
    if not probs:
        return None
    outcome = max(probs, key=probs.get)
    return {
        "market": market_label,
        "selection": label_map.get(outcome, outcome),
        "outcome": outcome,
        "probability": float(probs.get(outcome, 0)),
        "odds": _best_market_odds(item, market_label, outcome) or (consensus.get("fair_odds") or {}).get(outcome),
        "source": "consensus",
    }


def _confidence_for_market(item: dict, market: str) -> float:
    if market == "1X2":
        return float((item.get("consensus_1x2") or {}).get("confidence") or 0)
    if market == "O/U 2.5":
        return float((item.get("consensus_ou") or {}).get("confidence") or 0)
    if market == "O/U 1.5":
        return float((item.get("consensus_ou15") or {}).get("confidence") or 0)
    if market == "BTTS":
        return float((item.get("consensus_btts") or {}).get("confidence") or 0)
    return float((item.get("consensus_1x2") or {}).get("confidence") or 0)


def _derive_primary_pick(item: dict) -> dict:
    top = (item.get("value_bets") or [None])[0]
    if top:
        market = top.get("market") or ""
        return {
            "market": market,
            "selection": top.get("label") or top.get("outcome"),
            "outcome": top.get("outcome"),
            "probability": top.get("prob"),
            "odds": top.get("odds", top.get("best_odds")),
            "value": top.get("value"),
            "kelly": top.get("kelly"),
            "confidence": _confidence_for_market(item, market),
            "source": "value",
        }

    picks = [
        candidate
        for candidate in (
            _recommendation_from_1x2(item),
            _recommendation_from_totals(item),
            _recommendation_from_binary(
                item,
                "consensus_ou15",
                "O/U 1.5",
                {"over": "Over 1.5", "under": "Under 1.5"},
            ),
            _recommendation_from_binary(
                item,
                "consensus_btts",
                "BTTS",
                {"yes": "Ambos marcan", "no": "No marcan ambos"},
            ),
        )
        if candidate
    ]
    if not picks:
        return {
            "market": "Radar",
            "selection": "Sin recomendación principal",
            "source": "none",
            "confidence": float((item.get("consensus_1x2") or {}).get("confidence") or 0),
        }

    picks.sort(key=lambda candidate: float(candidate.get("probability") or 0), reverse=True)
    best = picks[0]
    best["confidence"] = _confidence_for_market(item, best.get("market", ""))
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
    from src.league_labels import league_meta

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
