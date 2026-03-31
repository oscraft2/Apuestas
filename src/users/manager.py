"""
Gestión de usuarios — PostgreSQL via SQLAlchemy.
Free tier: 3 alertas/día
Premium: ilimitadas + features extra
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from src.db.database import SessionLocal
from src.db.models import User

logger = logging.getLogger(__name__)

TIER_FREE    = "free"
TIER_PREMIUM = "premium"

TIER_LIMITS = {
    TIER_FREE:    {"daily_alerts": 3,   "line_alerts": False, "bankroll": False, "backtest": False},
    TIER_PREMIUM: {"daily_alerts": 999, "line_alerts": True,  "bankroll": True,  "backtest": True},
}


def _is_premium(user: User) -> bool:
    if user.tier != TIER_PREMIUM:
        return False
    if user.premium_until:
        if datetime.now(timezone.utc) > user.premium_until.replace(tzinfo=timezone.utc) \
                if user.premium_until.tzinfo is None else datetime.now(timezone.utc) > user.premium_until:
            return False
    return True


def _limits(user: User) -> dict:
    return TIER_LIMITS[TIER_PREMIUM if _is_premium(user) else TIER_FREE]


def _can_alert(user: User) -> bool:
    today = datetime.now(timezone.utc).date().isoformat()
    if user.last_alert_date != today:
        return True
    return user.alerts_today < _limits(user)["daily_alerts"]


class UserManager:

    def get_or_create(self, user_id: int, username: str = "") -> User:
        with SessionLocal() as db:
            user = db.query(User).filter(User.user_id == user_id).first()
            if not user:
                user = User(
                    user_id=user_id,
                    username=username,
                    joined_at=datetime.now(timezone.utc),
                )
                db.add(user)
                db.commit()
                db.refresh(user)
                logger.info("Nuevo usuario: %s (%s)", user_id, username)
            elif username and user.username != username:
                user.username = username
                db.commit()
            # Devolver objeto desacoplado de la sesión
            db.expunge(user)
            return user

    def record_alert(self, user_id: int) -> bool:
        with SessionLocal() as db:
            user = db.query(User).filter(User.user_id == user_id).first()
            if not user or not _can_alert(user):
                return False
            today = datetime.now(timezone.utc).date().isoformat()
            if user.last_alert_date != today:
                user.alerts_today = 0
                user.last_alert_date = today
            user.alerts_today += 1
            user.total_alerts_sent += 1
            db.commit()
            return True

    def activate_premium(self, user_id: int, days: int = 30,
                         stripe_customer_id: str = None,
                         stripe_sub_id: str = None) -> User:
        with SessionLocal() as db:
            user = db.query(User).filter(User.user_id == user_id).first()
            if not user:
                raise KeyError(f"Usuario {user_id} no encontrado")
            expiry = datetime.now(timezone.utc) + timedelta(days=days)
            user.tier = TIER_PREMIUM
            user.premium_until = expiry
            if stripe_customer_id:
                user.stripe_customer_id = stripe_customer_id
            if stripe_sub_id:
                user.stripe_sub_id = stripe_sub_id
            db.commit()
            db.refresh(user)
            db.expunge(user)
            logger.info("Premium activado: %s hasta %s", user_id, expiry.date())
            return user

    def deactivate_premium(self, user_id: int):
        with SessionLocal() as db:
            user = db.query(User).filter(User.user_id == user_id).first()
            if user:
                user.tier = TIER_FREE
                user.premium_until = None
                db.commit()

    def set_line_alerts(self, user_id: int, enabled: bool):
        with SessionLocal() as db:
            user = db.query(User).filter(User.user_id == user_id).first()
            if not user:
                return
            if enabled and not _is_premium(user):
                raise PermissionError("Requiere Premium")
            user.notify_line_moves = enabled
            db.commit()

    def get_line_alert_subscribers(self) -> list:
        with SessionLocal() as db:
            users = db.query(User).filter(
                User.notify_line_moves == True,
                User.tier == TIER_PREMIUM,
            ).all()
            return [u.user_id for u in users if _is_premium(u)]

    def list_users(self, limit: int = 50) -> list:
        with SessionLocal() as db:
            users = db.query(User).order_by(User.joined_at.desc()).limit(limit).all()
            for u in users:
                db.expunge(u)
            return users

    def get_by_stripe_customer(self, customer_id: str) -> Optional[User]:
        with SessionLocal() as db:
            user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
            if user:
                db.expunge(user)
            return user

    def set_note(self, user_id: int, note: str):
        with SessionLocal() as db:
            user = db.query(User).filter(User.user_id == user_id).first()
            if user:
                user.notes = note
                db.commit()

    def leaderboard(self, top: int = 10) -> list:
        from src.bankroll.manager import BankrollManager
        bm = BankrollManager()
        result = []
        with SessionLocal() as db:
            users = db.query(User).all()
            for u in users:
                br = bm.get(u.user_id)
                if br and br.bets_placed >= 5:
                    result.append({
                        "username": u.username or f"user_{u.user_id}",
                        "roi":      br.roi,
                        "pnl":      br.pnl,
                        "bets":     br.bets_placed,
                        "tier":     u.tier,
                    })
        return sorted(result, key=lambda x: x["roi"], reverse=True)[:top]

    # ── Formatters para Telegram ───────────────────────────────────────────────

    def format_profile(self, user_id: int) -> str:
        user = self.get_or_create(user_id)
        premium = _is_premium(user)
        tier_emoji = "💎" if premium else "🆓"
        limits = _limits(user)
        today = datetime.now(timezone.utc).date().isoformat()
        alerts_today = user.alerts_today if user.last_alert_date == today else 0

        expiry_str = ""
        if user.premium_until:
            exp = user.premium_until
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            days_left = max(0, (exp - datetime.now(timezone.utc)).days)
            expiry_str = f" (vence en {days_left}d)"

        return (
            f"👤 <b>Tu perfil</b>\n"
            f"{'─' * 28}\n"
            f"{tier_emoji} Plan: <b>{'Premium' if premium else 'Free'}</b>{expiry_str}\n"
            f"📨 Alertas hoy: {alerts_today}/{limits['daily_alerts']}\n"
            f"📊 Alertas totales: {user.total_alerts_sent}\n"
            f"📈 Movimientos de cuota: {'✅' if limits['line_alerts'] else '❌ (Premium)'}\n"
            f"💰 Bankroll personal: {'✅' if limits['bankroll'] else '❌ (Premium)'}\n"
            f"🔬 Backtesting: {'✅' if limits['backtest'] else '❌ (Premium)'}\n"
            + ("" if premium else
               "\n💎 <b>Actualiza a Premium</b>\n"
               "Usa /premium para ver los planes disponibles.\n")
        )

    def format_premium_info(self, checkout_url: str = "") -> str:
        url_line = f'\n\n<a href="{checkout_url}">💳 Suscribirse ahora</a>' if checkout_url else \
                   "\n\nContacta al admin o usa /pagar."
        return (
            "💎 <b>ValueXPro Premium</b>\n"
            "─────────────────────────\n\n"
            "<b>Free (gratis):</b>\n"
            "✓ 3 value bets al día\n"
            "✓ Resumen diario\n"
            "✓ Estadísticas básicas\n\n"
            "<b>Premium (~€9.99/mes):</b>\n"
            "✓ Value bets ilimitadas\n"
            "✓ Alertas steam/reverse en tiempo real\n"
            "✓ Bankroll personal + Kelly en €/$\n"
            "✓ Backtesting histórico completo\n"
            "✓ Calibración por liga (Brier Score)\n"
            "✓ Análisis pre-partido 3h antes\n"
            "✓ XGBoost ML sobre tu historial"
            + url_line
        )
