"""
Feature #7 — Sistema de usuarios y suscripciones
Free tier: 3 alertas/día
Premium: ilimitadas + Kelly personalizado + alertas de movimiento
Stripe/PayPal via webhook (skeleton listo para integrar)
"""
import json
import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)
USERS_FILE = "data/users.json"

TIER_FREE = "free"
TIER_PREMIUM = "premium"
TIER_LIMITS = {
    TIER_FREE:    {"daily_alerts": 3,   "line_alerts": False, "bankroll": False, "backtest": False},
    TIER_PREMIUM: {"daily_alerts": 999, "line_alerts": True,  "bankroll": True,  "backtest": True},
}


@dataclass
class User:
    user_id: int
    username: str
    tier: str = TIER_FREE
    alerts_today: int = 0
    last_alert_date: str = ""
    premium_until: Optional[str] = None     # ISO date
    stripe_customer_id: Optional[str] = None
    joined_at: str = ""
    total_alerts_sent: int = 0
    notify_line_moves: bool = False

    @property
    def is_premium(self) -> bool:
        if self.tier != TIER_PREMIUM:
            return False
        if self.premium_until:
            try:
                exp = datetime.fromisoformat(self.premium_until)
                if datetime.now(timezone.utc) > exp:
                    return False
            except Exception:
                pass
        return True

    @property
    def limits(self) -> dict:
        return TIER_LIMITS[TIER_PREMIUM if self.is_premium else TIER_FREE]

    def can_receive_alert(self) -> bool:
        today = datetime.now(timezone.utc).date().isoformat()
        if self.last_alert_date != today:
            return True  # nuevo día, contador reseteado
        return self.alerts_today < self.limits["daily_alerts"]

    def premium_expires_in_days(self) -> Optional[int]:
        if not self.premium_until:
            return None
        try:
            exp = datetime.fromisoformat(self.premium_until)
            delta = exp - datetime.now(timezone.utc)
            return max(0, delta.days)
        except Exception:
            return None


class UserManager:

    def __init__(self, filepath: str = USERS_FILE):
        self.filepath = Path(filepath)
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[int, dict] = self._load()

    def _load(self) -> dict:
        if self.filepath.exists():
            try:
                raw = json.loads(self.filepath.read_text())
                return {int(k): v for k, v in raw.items()}
            except Exception:
                pass
        return {}

    def _save(self):
        self.filepath.write_text(json.dumps(self._data, indent=2, ensure_ascii=False))

    def _refresh(self):
        """
        Recarga desde disco para que API, bot y tareas compartan cambios recientes
        aunque cada uno tenga su propia instancia de UserManager en memoria.
        """
        self._data = self._load()

    def get_or_create(self, user_id: int, username: str = "") -> User:
        self._refresh()
        if user_id not in self._data:
            u = User(
                user_id=user_id,
                username=username,
                joined_at=datetime.now(timezone.utc).isoformat(),
            )
            self._data[user_id] = asdict(u)
            self._save()
            logger.info(f"Nuevo usuario: {user_id} ({username})")
        elif username and self._data[user_id].get("username") != username:
            self._data[user_id]["username"] = username
            self._save()
        return User(**self._data[user_id])

    def record_alert(self, user_id: int) -> bool:
        """Incrementa contador diario. Retorna False si límite alcanzado."""
        u = self.get_or_create(user_id)
        if not u.can_receive_alert():
            return False
        today = datetime.now(timezone.utc).date().isoformat()
        d = self._data[user_id]
        if d.get("last_alert_date") != today:
            d["alerts_today"] = 0
            d["last_alert_date"] = today
        d["alerts_today"] = d.get("alerts_today", 0) + 1
        d["total_alerts_sent"] = d.get("total_alerts_sent", 0) + 1
        self._save()
        return True

    def set_premium(self, user_id: int, days: int = 30, username: str = ""):
        """Crea el usuario si no existe y activa Premium (panel admin, webhooks)."""
        self.get_or_create(user_id, username or "")
        self.activate_premium(user_id, days=days)

    def activate_premium(self, user_id: int, days: int = 30, stripe_id: str = None):
        """Activa premium (llamado desde webhook de Stripe)."""
        self._refresh()
        d = self._data.get(user_id)
        if not d:
            raise KeyError(f"Usuario {user_id} no encontrado.")
        base = datetime.now(timezone.utc)
        current_expiry = d.get("premium_until")
        if current_expiry:
            try:
                parsed = datetime.fromisoformat(current_expiry)
                if parsed > base:
                    base = parsed
            except Exception:
                pass
        expiry = base + timedelta(days=days)
        d["tier"] = TIER_PREMIUM
        d["premium_until"] = expiry.isoformat()
        if stripe_id:
            d["stripe_customer_id"] = stripe_id
        self._save()
        logger.info(f"Premium activado: {user_id} hasta {expiry.date()}")
        return User(**d)

    def deactivate_premium(self, user_id: int):
        self._refresh()
        d = self._data.get(user_id)
        if d:
            d["tier"] = TIER_FREE
            d["premium_until"] = None
            d["notify_line_moves"] = False
            self._save()

    def set_line_alerts(self, user_id: int, enabled: bool):
        self._refresh()
        d = self._data.get(user_id)
        if d:
            u = User(**d)
            if not u.is_premium and enabled:
                raise PermissionError("Las alertas de movimiento de cuota requieren Premium.")
            d["notify_line_moves"] = enabled
            self._save()

    def get_line_alert_subscribers(self) -> list[int]:
        """Retorna user_ids que tienen line alerts activadas y son premium."""
        self._refresh()
        return [
            uid for uid, d in self._data.items()
            if d.get("notify_line_moves") and User(**d).is_premium
        ]

    def list_users_summary(self) -> list:
        """Lista usuarios para el panel admin (user_id es la clave en Telegram)."""
        self._refresh()
        out = []
        for uid, d in self._data.items():
            u = User(**d)
            out.append({
                "user_id": uid,
                "username": d.get("username") or "",
                "tier": d.get("tier", TIER_FREE),
                "premium_until": d.get("premium_until"),
                "is_premium": u.is_premium,
                "premium_expires_in_days": u.premium_expires_in_days(),
                "alerts_today": d.get("alerts_today", 0),
                "last_alert_date": d.get("last_alert_date", ""),
                "total_alerts_sent": d.get("total_alerts_sent", 0),
                "notify_line_moves": bool(d.get("notify_line_moves")),
                "joined_at": d.get("joined_at", ""),
            })
        return sorted(out, key=lambda x: (not x["is_premium"], x["user_id"]))

    def leaderboard(self, top: int = 10) -> list:
        """Top usuarios por ROI (requiere bankroll data)."""
        self._refresh()
        from src.bankroll.manager import BankrollManager
        bm = BankrollManager()
        result = []
        for uid in self._data:
            br = bm.get(uid)
            if br and br.bets_placed >= 5:
                result.append({
                    "username": self._data[uid].get("username", f"user_{uid}"),
                    "roi": br.roi,
                    "pnl": br.pnl,
                    "bets": br.bets_placed,
                    "tier": self._data[uid].get("tier", TIER_FREE),
                })
        return sorted(result, key=lambda x: x["roi"], reverse=True)[:top]

    def format_profile(self, user_id: int) -> str:
        u = self.get_or_create(user_id)
        tier_emoji = "💎" if u.is_premium else "🆓"
        tier_label = "Premium" if u.is_premium else "Free"
        days_left = u.premium_expires_in_days()
        expiry_str = f" (vence en {days_left}d)" if days_left is not None else ""

        limits = u.limits
        alerts_today = u.alerts_today if u.last_alert_date == datetime.now(timezone.utc).date().isoformat() else 0

        return (
            f"👤 <b>Tu perfil</b>\n"
            f"{'─' * 28}\n"
            f"🆔 Telegram ID: <code>{u.user_id}</code>\n"
            f"{tier_emoji} Plan: <b>{tier_label}</b>{expiry_str}\n"
            f"📨 Alertas hoy: {alerts_today}/{limits['daily_alerts']}\n"
            f"📊 Alertas totales: {u.total_alerts_sent}\n"
            f"📈 Movimientos de cuota: {'✅' if limits['line_alerts'] else '❌ (Premium)'}\n"
            f"💰 Bankroll personal: {'✅' if limits['bankroll'] else '❌ (Premium)'}\n"
            f"🔬 Backtesting: {'✅' if limits['backtest'] else '❌ (Premium)'}\n\n"
            + ("" if u.is_premium else
               "💎 <b>Actualiza a Premium</b>\n"
               "Usa /premium para ver los planes disponibles.\n")
        )

    def format_premium_info(self) -> str:
        return (
            "💎 <b>ValueXPro Premium</b>\n"
            "{'─' * 28}\n\n"
            "<b>Free (gratis):</b>\n"
            "✓ 3 alertas de value bets al día\n"
            "✓ Resumen diario\n"
            "✓ Estadísticas básicas\n\n"
            "<b>Premium (~€9.99/mes):</b>\n"
            "✓ Alertas ilimitadas\n"
            "✓ Alertas de movimiento de cuota (steam/reverse)\n"
            "✓ Bankroll personal + Kelly en €/$\n"
            "✓ Backtesting histórico completo\n"
            "✓ Calibración por liga\n"
            "✓ Análisis pre-partido (3h antes)\n\n"
            "💳 Usa /pagar para suscribirte."
        )
