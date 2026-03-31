"""
Football Value Bot V3 — Entry point
Modos:
  python main.py         → bot de Telegram
  python main.py api     → API REST (puerto $PORT o 8000)
  python main.py both    → bot + API en paralelo
"""
import sys
import logging
import asyncio
import threading
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),              # stdout (Railway logs)
    ],
)

logger = logging.getLogger(__name__)


def _validate_and_init():
    """Valida ENV y prepara la base de datos."""
    from config import validate_env
    from src.db.database import init_db
    from src.tracking.tracker import PredictionTracker

    ok = validate_env()
    if not ok:
        logger.warning("⚠️  Algunas variables requeridas no están configuradas — el bot puede fallar")

    # Crear tablas si no existen (idempotente)
    init_db()

    # Migrar predicciones JSONL legacy si existen
    try:
        tracker = PredictionTracker()
        n = tracker.migrate_from_jsonl()
        if n:
            logger.info("✅ Migración JSONL completada: %d predicciones", n)
    except Exception as e:
        logger.warning("Migración JSONL fallida (no crítico): %s", e)


def run_bot():
    from src.bot.telegram_bot import run
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    run()


def run_api():
    import uvicorn
    import os
    from src.api.server import app
    port = int(os.getenv("PORT", os.getenv("API_PORT", 8000)))
    host = os.getenv("API_HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port, loop="asyncio", log_level="info")


def run_both():
    def _api_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        run_api()

    t = threading.Thread(target=_api_thread, daemon=True)
    t.start()
    run_bot()


if __name__ == "__main__":
    _validate_and_init()

    mode = sys.argv[1] if len(sys.argv) > 1 else "bot"
    logger.info("🚀 Iniciando en modo: %s", mode)

    if mode == "api":
        run_api()
    elif mode == "both":
        run_both()
    else:
        run_bot()
