"""
Modelos SQLAlchemy — tablas de la base de datos.
"""
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, BigInteger, String, Float, Boolean,
    DateTime, Text, JSON
)
from src.db.database import Base


def _now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id                  = Column(Integer, primary_key=True, index=True)
    user_id             = Column(BigInteger, unique=True, nullable=False, index=True)
    username            = Column(String(64), default="")
    tier                = Column(String(16), default="free")      # "free" | "premium"
    alerts_today        = Column(Integer, default=0)
    last_alert_date     = Column(String(10), default="")          # YYYY-MM-DD
    premium_until       = Column(DateTime(timezone=True), nullable=True)
    stripe_customer_id  = Column(String(64), nullable=True)
    stripe_sub_id       = Column(String(64), nullable=True)
    joined_at           = Column(DateTime(timezone=True), default=_now)
    total_alerts_sent   = Column(Integer, default=0)
    notify_line_moves   = Column(Boolean, default=False)
    notes               = Column(Text, default="")                # notas admin

    def __repr__(self):
        return f"<User {self.user_id} tier={self.tier}>"


class Prediction(Base):
    __tablename__ = "predictions"

    id          = Column(Integer, primary_key=True, index=True)
    match_id    = Column(String(64), default="", index=True)
    home        = Column(String(64), nullable=False)
    away        = Column(String(64), nullable=False)
    league      = Column(String(64), default="")
    date        = Column(String(10), default="")                  # YYYY-MM-DD
    market      = Column(String(16), nullable=False)              # "1X2" | "O/U 2.5"
    outcome     = Column(String(16), nullable=False)              # "home"|"draw"|"away"|"over"|"under"
    model_prob  = Column(Float, nullable=False)
    odds        = Column(Float, nullable=False)
    value       = Column(Float, nullable=False)
    kelly       = Column(Float, default=0.0)
    bookmaker   = Column(String(32), default="")
    won         = Column(Boolean, nullable=True)                  # None = pendiente
    pnl         = Column(Float, nullable=True)
    created_at  = Column(DateTime(timezone=True), default=_now, index=True)
    # Snapshot del análisis completo (JSON)
    analysis    = Column(JSON, nullable=True)

    def __repr__(self):
        return f"<Prediction {self.home} vs {self.away} {self.market}/{self.outcome}>"


class Bankroll(Base):
    __tablename__ = "bankrolls"

    id           = Column(Integer, primary_key=True, index=True)
    user_id      = Column(BigInteger, unique=True, nullable=False, index=True)
    currency     = Column(String(3), default="EUR")
    initial      = Column(Float, nullable=False)
    current      = Column(Float, nullable=False)
    bets_placed  = Column(Integer, default=0)
    bets_won     = Column(Integer, default=0)
    total_staked = Column(Float, default=0.0)
    pnl          = Column(Float, default=0.0)
    updated_at   = Column(DateTime(timezone=True), default=_now, onupdate=_now)

    @property
    def roi(self) -> float:
        return round(self.pnl / self.total_staked * 100, 2) if self.total_staked else 0.0

    def __repr__(self):
        return f"<Bankroll user={self.user_id} {self.current}{self.currency}>"


class StripeEvent(Base):
    """Registro de eventos de Stripe procesados (evitar duplicados)."""
    __tablename__ = "stripe_events"

    id         = Column(Integer, primary_key=True)
    event_id   = Column(String(64), unique=True, nullable=False)
    event_type = Column(String(64), nullable=False)
    processed  = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=_now)
