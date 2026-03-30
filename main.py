"""
Football Value Bot V3 — Entry point
Modos:
  python main.py         → lanza el bot de Telegram
  python main.py api     → lanza la API REST (puerto 8000)
  python main.py both    → lanza bot + API en paralelo
"""
import sys
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def run_bot():
    from src.bot.telegram_bot import run
    run()


def run_api():
    from src.api.server import run_api as _run
    _run()


def run_both():
    import threading
    api_thread = threading.Thread(target=run_api, daemon=True)
    api_thread.start()
    run_bot()


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "bot"
    if mode == "api":
        run_api()
    elif mode == "both":
        run_both()
    else:
        run_bot()
