"""
Football Value Bot V3 — Entry point
Modos:
  python main.py         → lanza el bot de Telegram
  python main.py api     → lanza la API REST (puerto 8000)
  python main.py both    → lanza bot + API en paralelo
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
)


def run_bot():
    from src.bot.telegram_bot import run
    # Garantizar un event loop limpio en el hilo actual
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    run()


def run_api():
    import uvicorn
    import os
    from src.api.server import app
    # Railway inyecta PORT dinámicamente; fallback a 8000 en local
    port = int(os.getenv("PORT", os.getenv("API_PORT", 8000)))
    host = os.getenv("API_HOST", "0.0.0.0")
    # loop="asyncio" evita que uvloop sobreescriba la policy global
    uvicorn.run(app, host=host, port=port, loop="asyncio", log_level="info")


def run_both():
    """
    Bot + API en paralelo. Sin TELEGRAM_TOKEN solo arranca la API (Railway puede servir el dashboard).
    """
    from config import config

    if not config.telegram_token:
        logging.getLogger(__name__).warning(
            "TELEGRAM_TOKEN no definido: arrancando solo la API (dashboard /api). "
            "Configura el token para el bot de Telegram."
        )
        run_api()
        return

    # API en hilo daemon con su propio event loop
    def _api_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        run_api()

    t = threading.Thread(target=_api_thread, daemon=True)
    t.start()

    # Bot en hilo principal con event loop fresco
    run_bot()


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "bot"
    if mode == "api":
        run_api()
    elif mode == "both":
        run_both()
    else:
        run_bot()
