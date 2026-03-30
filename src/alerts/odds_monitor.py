"""
Feature #2 — Monitor de movimiento de cuotas
Detecta cuando Pinnacle u otras sharps mueven la cuota >N% en un intervalo.
Señal fiable de información nueva en el mercado (lesión, alineación, etc).
"""
import asyncio
import json
import logging
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config import config

logger = logging.getLogger(__name__)

SNAPSHOTS_FILE = os.path.join(config.cache_dir, "odds_snapshots.json")
SHARP_BOOKS = {"pinnacle", "pinnacle_com", "matchbook", "betfair_ex_eu"}


@dataclass
class OddsMovement:
    match_id: str
    home: str
    away: str
    league: str
    bookmaker: str
    market: str
    outcome: str
    old_odds: float
    new_odds: float
    change_pct: float        # positivo = cuota sube (equipo menos favorito)
    direction: str           # "steam" (baja rápido) | "reverse" (sube)
    detected_at: str
    sharp: bool


class OddsMonitor:
    """
    Polling cada 30 minutos. Compara snapshot anterior con actual.
    Dispara alerta si |cambio| > threshold.
    """

    STEAM_THRESHOLD = 0.04    # 4% de caída de cuota = steam move
    REVERSE_THRESHOLD = 0.06  # 6% de subida = reverse line movement

    def __init__(self, snapshots_file: str = SNAPSHOTS_FILE):
        self.snapshots_file = Path(snapshots_file)
        self._snapshots: dict = self._load_snapshots()

    def _load_snapshots(self) -> dict:
        if self.snapshots_file.exists():
            try:
                return json.loads(self.snapshots_file.read_text())
            except Exception:
                pass
        return {}

    def _save_snapshots(self):
        self.snapshots_file.parent.mkdir(parents=True, exist_ok=True)
        self.snapshots_file.write_text(json.dumps(self._snapshots, indent=2))

    def update_snapshot(self, match_id: str, bookmakers: list, home: str, away: str, league: str):
        """Actualiza el snapshot de cuotas para un partido."""
        entry: dict = {"home": home, "away": away, "league": league, "books": {}}
        for bm in bookmakers:
            key = bm.get("key", "")
            for mkt in bm.get("markets", []):
                for o in mkt.get("outcomes", []):
                    k = f"{key}:{mkt['key']}:{o['name']}"
                    entry["books"][k] = o["price"]
        entry["ts"] = datetime.now(timezone.utc).isoformat()
        self._snapshots[match_id] = entry
        self._save_snapshots()

    def detect_movements(self, match_id: str, bookmakers: list) -> list[OddsMovement]:
        """Compara cuotas actuales contra el snapshot. Retorna lista de movimientos."""
        if match_id not in self._snapshots:
            return []

        prev = self._snapshots[match_id]
        movements: list[OddsMovement] = []

        for bm in bookmakers:
            key = bm.get("key", "")
            name = bm.get("title", key)
            is_sharp = key.lower() in SHARP_BOOKS

            for mkt in bm.get("markets", []):
                for o in mkt.get("outcomes", []):
                    snap_key = f"{key}:{mkt['key']}:{o['name']}"
                    old_price = prev["books"].get(snap_key)
                    new_price = o.get("price")

                    if not old_price or not new_price or old_price <= 1 or new_price <= 1:
                        continue

                    change_pct = (new_price - old_price) / old_price

                    # Steam move: cuota cae rápido (mucho dinero en un lado)
                    if change_pct <= -self.STEAM_THRESHOLD:
                        direction = "steam"
                    # Reverse line movement: cuota sube aunque hay dinero contrario
                    elif change_pct >= self.REVERSE_THRESHOLD and is_sharp:
                        direction = "reverse"
                    else:
                        continue

                    movements.append(OddsMovement(
                        match_id=match_id,
                        home=prev.get("home", "?"),
                        away=prev.get("away", "?"),
                        league=prev.get("league", "?"),
                        bookmaker=name,
                        market=mkt["key"],
                        outcome=o["name"],
                        old_odds=round(old_price, 3),
                        new_odds=round(new_price, 3),
                        change_pct=round(change_pct, 4),
                        direction=direction,
                        detected_at=datetime.now(timezone.utc).isoformat(),
                        sharp=is_sharp,
                    ))

        return movements

    @staticmethod
    def format_movement(mv: OddsMovement) -> str:
        icon = "🔴 STEAM" if mv.direction == "steam" else "🔵 REVERSE"
        sharp_tag = " 🎯 SHARP" if mv.sharp else ""
        return (
            f"{icon}{sharp_tag}\n"
            f"⚽ {mv.home} vs {mv.away}\n"
            f"📊 {mv.market.upper()} · {mv.outcome}\n"
            f"📉 {mv.old_odds:.2f} → {mv.new_odds:.2f} ({mv.change_pct:+.1%})\n"
            f"🏦 {mv.bookmaker}"
        )


class OddsPollingService:
    """
    Servicio asyncio que corre en background, hace polling cada 30 min
    y notifica al bot cuando detecta movimientos.
    """

    def __init__(self, monitor: OddsMonitor, notify_callback, interval_seconds: int = 1800):
        self.monitor = monitor
        self.notify = notify_callback
        self.interval = interval_seconds
        self._running = False

    async def start(self, leagues_getter, odds_getter):
        """
        leagues_getter: función que retorna lista de league_ids activos
        odds_getter: función(league_id) → lista de partidos con bookmakers
        """
        self._running = True
        logger.info("OddsPollingService iniciado.")
        while self._running:
            try:
                await self._poll(leagues_getter, odds_getter)
            except Exception as e:
                logger.error(f"OddsPollingService error: {e}")
            await asyncio.sleep(self.interval)

    async def _poll(self, leagues_getter, odds_getter):
        for lid in leagues_getter():
            matches = odds_getter(lid)
            for match in matches:
                mid = match.get("id", "")
                bms = match.get("bookmakers", [])
                home = match.get("home_team", "")
                away = match.get("away_team", "")
                league = match.get("sport_title", "")

                # Detectar movimientos vs snapshot anterior
                movements = self.monitor.detect_movements(mid, bms)
                for mv in movements:
                    msg = self.monitor.format_movement(mv)
                    await self.notify(msg)
                    logger.info(f"Movimiento detectado: {mv.direction} en {mv.home} vs {mv.away}")

                # Actualizar snapshot
                self.monitor.update_snapshot(mid, bms, home, away, league)

    def stop(self):
        self._running = False
