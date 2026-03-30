"""
Feature #3 — Sistema de bankroll personal por usuario
Cada usuario Telegram tiene su bankroll en €/$. El bot calcula stakes reales
con Kelly fraccionado y lleva registro de su historial personal.
"""
import json
import logging
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)
BANKROLLS_FILE = os.path.join("data", "bankrolls.json")


@dataclass
class UserBankroll:
    user_id: int
    username: str
    currency: str           # "EUR" | "USD" | "GBP"
    initial: float
    current: float
    peak: float
    bets_placed: int = 0
    bets_won: int = 0
    total_staked: float = 0.0
    total_returned: float = 0.0
    created_at: str = ""
    updated_at: str = ""

    @property
    def roi(self) -> float:
        if self.total_staked <= 0:
            return 0.0
        return round((self.total_returned - self.total_staked) / self.total_staked * 100, 2)

    @property
    def pnl(self) -> float:
        return round(self.current - self.initial, 2)

    @property
    def pnl_pct(self) -> float:
        return round(self.pnl / self.initial * 100, 2) if self.initial > 0 else 0.0

    @property
    def drawdown(self) -> float:
        return round((self.peak - self.current) / self.peak * 100, 2) if self.peak > 0 else 0.0

    @property
    def hit_rate(self) -> float:
        return round(self.bets_won / self.bets_placed, 3) if self.bets_placed > 0 else 0.0


class BankrollManager:
    """Gestiona bankrolls de todos los usuarios en un JSON local."""

    KELLY_FRACTION = 0.25    # Kelly conservador
    MAX_STAKE_PCT = 0.05     # Máximo 5% del bankroll por apuesta
    MIN_STAKE = 1.0          # Mínimo 1 unidad monetaria

    def __init__(self, filepath: str = BANKROLLS_FILE):
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

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def get(self, user_id: int) -> Optional[UserBankroll]:
        d = self._data.get(user_id)
        if not d:
            return None
        return UserBankroll(**d)

    def create(self, user_id: int, username: str, amount: float, currency: str = "EUR") -> UserBankroll:
        if amount < 10:
            raise ValueError("El bankroll mínimo es 10 unidades.")
        br = UserBankroll(
            user_id=user_id,
            username=username,
            currency=currency,
            initial=amount,
            current=amount,
            peak=amount,
            created_at=self._now(),
            updated_at=self._now(),
        )
        self._data[user_id] = asdict(br)
        self._save()
        return br

    def update(self, user_id: int, amount: float):
        """Actualiza el bankroll manualmente (depósito o retirada)."""
        d = self._data.get(user_id)
        if not d:
            raise KeyError(f"Usuario {user_id} no tiene bankroll configurado.")
        d["current"] = round(amount, 2)
        d["peak"] = max(d["peak"], amount)
        d["updated_at"] = self._now()
        self._save()

    def record_bet(self, user_id: int, staked: float, returned: float, won: bool):
        """Registra una apuesta resuelta."""
        d = self._data.get(user_id)
        if not d:
            return
        d["current"] = round(d["current"] - staked + returned, 2)
        d["peak"] = max(d["peak"], d["current"])
        d["bets_placed"] = d.get("bets_placed", 0) + 1
        if won:
            d["bets_won"] = d.get("bets_won", 0) + 1
        d["total_staked"] = round(d.get("total_staked", 0) + staked, 2)
        d["total_returned"] = round(d.get("total_returned", 0) + returned, 2)
        d["updated_at"] = self._now()
        self._save()

    def reset(self, user_id: int, new_amount: Optional[float] = None):
        """Reinicia el bankroll (nuevo ciclo)."""
        d = self._data.get(user_id)
        if not d:
            raise KeyError(f"Usuario {user_id} no registrado.")
        amount = new_amount if new_amount else d["current"]
        d.update({
            "initial": amount, "current": amount, "peak": amount,
            "bets_placed": 0, "bets_won": 0,
            "total_staked": 0.0, "total_returned": 0.0,
            "updated_at": self._now(),
        })
        self._save()

    def calculate_stake(self, user_id: int, prob: float, odds: float) -> dict:
        """
        Calcula stake recomendado en unidades monetarias.
        Retorna: {"stake": X.XX, "currency": "EUR", "kelly_pct": 0.XX}
        """
        br = self.get(user_id)
        if not br:
            return {"error": "Sin bankroll configurado. Usa /bankroll <cantidad>"}

        b = odds - 1
        if b <= 0 or prob <= 0 or prob >= 1:
            return {"stake": 0, "currency": br.currency, "kelly_pct": 0}

        kelly_raw = (prob * b - (1 - prob)) / b
        kelly_frac = max(0, kelly_raw * self.KELLY_FRACTION)
        kelly_frac = min(kelly_frac, self.MAX_STAKE_PCT)

        stake = round(br.current * kelly_frac, 2)
        stake = max(self.MIN_STAKE, stake)

        return {
            "stake": stake,
            "currency": br.currency,
            "kelly_pct": round(kelly_frac * 100, 2),
            "bankroll": br.current,
            "pct_of_bankroll": round(stake / br.current * 100, 1),
        }

    def format_status(self, user_id: int) -> str:
        br = self.get(user_id)
        if not br:
            return (
                "💰 <b>Sin bankroll configurado.</b>\n\n"
                "Usa /bankroll 500 para empezar con 500€\n"
                "O /bankroll 500 USD para dólares."
            )

        pnl_emoji = "📈" if br.pnl >= 0 else "📉"
        sym = {"EUR": "€", "USD": "$", "GBP": "£"}.get(br.currency, br.currency)

        return (
            f"💰 <b>Tu Bankroll</b>\n"
            f"{'─' * 28}\n"
            f"Inicial: {sym}{br.initial:.2f}\n"
            f"Actual:  <b>{sym}{br.current:.2f}</b>\n"
            f"{pnl_emoji} P&L: {sym}{br.pnl:+.2f} ({br.pnl_pct:+.1f}%)\n"
            f"📉 Drawdown: {br.drawdown:.1f}%\n"
            f"{'─' * 28}\n"
            f"Apuestas: {br.bets_placed} ({br.bets_won} ✅)\n"
            f"Hit rate: {br.hit_rate:.1%}\n"
            f"ROI: <b>{br.roi:+.1f}%</b>"
        )

    def format_stake_suggestion(self, user_id: int, value_bets: list) -> str:
        """Genera sugerencias de stake para una lista de value bets."""
        br = self.get(user_id)
        if not br:
            return ""
        sym = {"EUR": "€", "USD": "$", "GBP": "£"}.get(br.currency, br.currency)
        lines = [f"\n💰 <b>Stakes recomendados (bankroll {sym}{br.current:.0f}):</b>"]
        for vb in value_bets[:4]:
            s = self.calculate_stake(user_id, vb.get("prob", 0), vb.get("odds", 0))
            stake = s.get("stake", 0)
            if stake > 0:
                label = vb.get("label") or vb.get("outcome", "?")
                lines.append(
                    f"  → {vb.get('market')} {label} @ {vb.get('odds', 0):.2f}: "
                    f"<b>{sym}{stake:.2f}</b> ({s.get('pct_of_bankroll', 0):.1f}%)"
                )
        return "\n".join(lines)
