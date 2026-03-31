"""
BankrollManager — bankroll personal por usuario en PostgreSQL.
Kelly fraccionado (×0.25), stake máximo 5% del bankroll.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from src.db.database import SessionLocal
from src.db.models import Bankroll

logger = logging.getLogger(__name__)

KELLY_FRACTION = 0.25
MAX_STAKE_PCT  = 0.05   # nunca más del 5% del bankroll en una apuesta


class BankrollManager:

    def get(self, user_id: int) -> Optional[Bankroll]:
        with SessionLocal() as db:
            br = db.query(Bankroll).filter(Bankroll.user_id == user_id).first()
            if br:
                db.expunge(br)
            return br

    def set_bankroll(self, user_id: int, amount: float, currency: str = "EUR") -> Bankroll:
        with SessionLocal() as db:
            br = db.query(Bankroll).filter(Bankroll.user_id == user_id).first()
            if br:
                br.initial  = amount
                br.current  = amount
                br.currency = currency.upper()
                br.pnl      = 0.0
                br.bets_placed = 0
                br.bets_won    = 0
                br.total_staked = 0.0
            else:
                br = Bankroll(
                    user_id  = user_id,
                    currency = currency.upper(),
                    initial  = amount,
                    current  = amount,
                )
                db.add(br)
            db.commit()
            db.refresh(br)
            db.expunge(br)
            logger.info("Bankroll configurado: user=%s %s%s", user_id, amount, currency)
            return br

    def kelly_stake(self, user_id: int, model_prob: float, odds: float) -> float:
        """Devuelve el stake en unidades monetarias (Kelly fraccionado)."""
        br = self.get(user_id)
        if not br or br.current <= 0:
            return 0.0
        b = odds - 1
        q = 1 - model_prob
        kelly_pct = (model_prob * b - q) / b if b > 0 else 0
        kelly_pct = max(0, kelly_pct * KELLY_FRACTION)
        kelly_pct = min(kelly_pct, MAX_STAKE_PCT)
        return round(br.current * kelly_pct, 2)

    def record_bet(self, user_id: int, stake: float, won: bool, odds: float):
        """Actualiza el bankroll tras resolver una apuesta."""
        with SessionLocal() as db:
            br = db.query(Bankroll).filter(Bankroll.user_id == user_id).first()
            if not br:
                return
            pnl = stake * (odds - 1) if won else -stake
            br.current      = round(br.current + pnl, 2)
            br.pnl          = round(br.pnl + pnl, 2)
            br.bets_placed += 1
            if won:
                br.bets_won += 1
            br.total_staked = round(br.total_staked + stake, 2)
            db.commit()

    def format_stake_suggestion(self, user_id: int, value_bets: list) -> str:
        br = self.get(user_id)
        if not br or not value_bets:
            return ""
        lines = [
            f"💰 <b>Stakes recomendados</b> (bankroll: {br.current:.0f}{br.currency})\n"
            f"{'─' * 30}"
        ]
        for vb in value_bets[:4]:
            model_prob = vb.get("model_prob", 0)
            odds       = vb.get("odds", vb.get("best_odds", 0))
            if not model_prob or not odds:
                continue
            stake  = self.kelly_stake(user_id, model_prob, odds)
            market = vb.get("market", "")
            label  = vb.get("label") or vb.get("outcome", "")
            lines.append(
                f"→ {market} <b>{label}</b>\n"
                f"   @ {odds:.2f} | Stake: <b>{stake:.1f}{br.currency}</b> "
                f"({stake/br.current*100:.1f}%)"
            )
        return "\n".join(lines) if len(lines) > 1 else ""

    def format_bankroll_status(self, user_id: int) -> str:
        br = self.get(user_id)
        if not br:
            return (
                "💰 No tienes un bankroll configurado.\n\n"
                "Usa /bankroll <cantidad> <moneda> para empezar.\n"
                "Ejemplo: /bankroll 500 EUR"
            )
        pnl_emoji = "📈" if br.pnl >= 0 else "📉"
        return (
            f"💰 <b>Tu Bankroll</b>\n"
            f"{'─' * 28}\n"
            f"Inicial:    {br.initial:.2f} {br.currency}\n"
            f"Actual:     <b>{br.current:.2f} {br.currency}</b>\n"
            f"{pnl_emoji} P&L:       {br.pnl:+.2f} {br.currency}\n"
            f"ROI:        <b>{br.roi:+.1f}%</b>\n"
            f"Apuestas:   {br.bets_placed} ({br.bets_won} ganadas)\n"
            f"Apostado:   {br.total_staked:.2f} {br.currency}\n\n"
            f"Kelly fracción: ×{KELLY_FRACTION} | Máx stake: {MAX_STAKE_PCT*100:.0f}%"
        )
