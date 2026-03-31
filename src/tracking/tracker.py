"""
PredictionTracker — persiste predicciones en PostgreSQL.
Mantiene compatibilidad con el JSONL legacy (migración automática al arrancar).
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import desc

from src.db.database import SessionLocal
from src.db.models import Prediction

logger = logging.getLogger(__name__)

MARKET_KEY = "O/U 2.5"


class PredictionTracker:

    # ── Escritura ──────────────────────────────────────────────────────────────

    def log_prediction(self, analysis: dict):
        """Registra todos los value bets de un análisis en la DB."""
        vbs = analysis.get("value_bets", [])
        if not vbs:
            return
        date_str = datetime.now(timezone.utc).date().isoformat()
        with SessionLocal() as db:
            for vb in vbs:
                pred = Prediction(
                    match_id   = str(analysis.get("match_id", "")),
                    home       = analysis.get("home", ""),
                    away       = analysis.get("away", ""),
                    league     = analysis.get("league", ""),
                    date       = date_str,
                    market     = vb.get("market", ""),
                    outcome    = vb.get("outcome", vb.get("label", "")),
                    model_prob = float(vb.get("model_prob", vb.get("prob", 0))),
                    odds       = float(vb.get("odds", vb.get("best_odds", 0))),
                    value      = float(vb.get("value", 0)),
                    kelly      = float(vb.get("kelly", 0)),
                    bookmaker  = vb.get("bookmaker", ""),
                    analysis   = {
                        "consensus_1x2": analysis.get("consensus_1x2"),
                        "consensus_ou":  analysis.get("consensus_ou"),
                        "poisson":       analysis.get("poisson"),
                        "ai":            analysis.get("ai"),
                        "xgb_win_prob":  analysis.get("xgb_win_prob"),
                    },
                )
                db.add(pred)
            db.commit()

    def log_result(self, match_id: str, market: str, outcome: str,
                   won: bool, pnl: float = None) -> bool:
        """Registra el resultado real. pnl se calcula si no se provee (stake = 1u)."""
        with SessionLocal() as db:
            pred = db.query(Prediction).filter(
                Prediction.match_id == match_id,
                Prediction.market   == market,
                Prediction.outcome  == outcome,
                Prediction.won      == None,
            ).first()
            if not pred:
                logger.warning("Predicción no encontrada: %s %s/%s", match_id, market, outcome)
                return False
            pred.won = won
            if pnl is None:
                pnl = (pred.odds - 1) if won else -1.0
            pred.pnl = round(pnl, 4)
            db.commit()
            return True

    def tag_cycle(self, analysis_date: str, highlights: list, leaders: list) -> int:
        """
        Etiqueta predicciones del ciclo actual para trazabilidad en dashboard/tracking.
        Devuelve cuántos registros fueron marcados.
        """
        highlight_ids = {str(r.get("match_id")) for r in (highlights or []) if r.get("match_id")}
        leader_ids = {str(r.get("match_id")) for r in (leaders or []) if r.get("match_id")}
        if not highlight_ids and not leader_ids:
            return 0

        touched = 0
        with SessionLocal() as db:
            preds = db.query(Prediction).filter(Prediction.date == analysis_date).all()
            for pred in preds:
                mid = str(pred.match_id or "")
                if mid not in highlight_ids and mid not in leader_ids:
                    continue
                analysis = dict(pred.analysis or {})
                analysis["cycle_date"] = analysis_date
                analysis["is_highlight"] = mid in highlight_ids
                analysis["is_leader"] = mid in leader_ids
                pred.analysis = analysis
                touched += 1
            if touched:
                db.commit()
        return touched

    # ── Lectura ───────────────────────────────────────────────────────────────

    def get_recent(self, n: int = 20) -> list:
        with SessionLocal() as db:
            preds = db.query(Prediction)\
                      .order_by(desc(Prediction.created_at))\
                      .limit(n * 4)\
                      .all()
            return [self._serialize(p) for p in preds]

    def get_today(self) -> list:
        today = datetime.now(timezone.utc).date().isoformat()
        with SessionLocal() as db:
            preds = db.query(Prediction)\
                      .filter(Prediction.date == today)\
                      .order_by(desc(Prediction.created_at))\
                      .all()
            return [self._serialize(p) for p in preds]

    def get_pending_predictions(self, max_days_back: int = 4) -> list:
        """Alias usado por result_sync — predicciones pendientes de los últimos N días."""
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max_days_back)).date().isoformat()
        with SessionLocal() as db:
            preds = db.query(Prediction)\
                      .filter(Prediction.won == None, Prediction.date >= cutoff)\
                      .order_by(Prediction.created_at)\
                      .all()
            return [self._serialize(p) for p in preds]

    def get_pending(self) -> list:
        with SessionLocal() as db:
            preds = db.query(Prediction)\
                      .filter(Prediction.won == None)\
                      .order_by(Prediction.created_at)\
                      .all()
            return [self._serialize(p) for p in preds]

    def get_stats(self) -> dict:
        with SessionLocal() as db:
            all_preds = db.query(Prediction).all()

        if not all_preds:
            return {
                "total_bets": 0, "won": 0, "lost": 0, "pending": 0,
                "hit_rate": 0.0, "pnl_units": 0.0, "roi_pct": 0.0,
                "by_market": {}, "by_league": {},
            }

        settled = [p for p in all_preds if p.won is not None]
        won_list = [p for p in settled if p.won]
        pending  = [p for p in all_preds if p.won is None]
        pnl      = sum(p.pnl or 0 for p in settled)
        roi      = round(pnl / len(settled) * 100, 2) if settled else 0.0

        by_market: dict = {}
        by_league: dict = {}
        for p in settled:
            for d, key in [(by_market, p.market), (by_league, p.league or "Desconocida")]:
                if key not in d:
                    d[key] = {"won": 0, "lost": 0, "pnl": 0.0}
                d[key]["won" if p.won else "lost"] += 1
                d[key]["pnl"] = round(d[key]["pnl"] + (p.pnl or 0), 4)

        return {
            "total_bets": len(all_preds),
            "won":        len(won_list),
            "lost":       len(settled) - len(won_list),
            "pending":    len(pending),
            "hit_rate":   round(len(won_list) / len(settled), 4) if settled else 0.0,
            "pnl_units":  round(pnl, 2),
            "roi_pct":    roi,
            "by_market":  by_market,
            "by_league":  by_league,
        }

    # ── Migración JSONL legacy ────────────────────────────────────────────────

    def migrate_from_jsonl(self, jsonl_path: str = "data/predictions/predictions.jsonl") -> int:
        path = Path(jsonl_path)
        if not path.exists():
            return 0
        imported = 0
        with SessionLocal() as db:
            for line in path.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    for vb in rec.get("value_bets", []):
                        exists = db.query(Prediction).filter(
                            Prediction.match_id == str(rec.get("match_id", "")),
                            Prediction.market   == vb.get("market", ""),
                            Prediction.outcome  == vb.get("outcome", ""),
                        ).first()
                        if not exists:
                            db.add(Prediction(
                                match_id   = str(rec.get("match_id", "")),
                                home       = rec.get("home", ""),
                                away       = rec.get("away", ""),
                                league     = rec.get("league", ""),
                                date       = rec.get("date", ""),
                                market     = vb.get("market", ""),
                                outcome    = vb.get("outcome", ""),
                                model_prob = float(vb.get("model_prob", vb.get("prob", 0))),
                                odds       = float(vb.get("odds", vb.get("best_odds", 0))),
                                value      = float(vb.get("value", 0)),
                                kelly      = float(vb.get("kelly", 0)),
                                won        = vb.get("won"),
                                pnl        = vb.get("pnl"),
                            ))
                            imported += 1
                except Exception as e:
                    logger.warning("Error migrando JSONL: %s", e)
            db.commit()
        if imported:
            logger.info("Migración JSONL: %d predicciones importadas", imported)
        return imported

    # ── Helper ────────────────────────────────────────────────────────────────

    def _serialize(self, p: Prediction) -> dict:
        d = {
            "id":         p.id,
            "match_id":   p.match_id,
            "home":       p.home,
            "away":       p.away,
            "league":     p.league,
            "date":       p.date,
            "market":     p.market,
            "outcome":    p.outcome,
            "model_prob": p.model_prob,
            "odds":       p.odds,
            "value":      p.value,
            "kelly":      p.kelly,
            "bookmaker":  p.bookmaker,
            "won":        p.won,
            "pnl":        p.pnl,
            "created_at": p.created_at.isoformat() if p.created_at else "",
        }
        if p.analysis:
            d.update(p.analysis)
        return d
