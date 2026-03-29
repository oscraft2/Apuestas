"""
Football Value Bot V3 — Entry point
"""
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from src.bot.telegram_bot import run

if __name__ == "__main__":
    run()
