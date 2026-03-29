"""
Bot de Telegram — Football Value Bot V3
Comandos: /start /hoy /liga /stats /ayuda
Scheduler: reportes automáticos 2x/día
"""
import logging
import asyncio
from datetime import datetime, timezone, time as dtime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from src.engine import FootballAnalyzerV3
from src.data.football_api import get_standings
from src.data.odds_api import get_odds_for_league, LEAGUE_TO_SPORT_KEY
from src.tracking.tracker import PredictionTracker
from src.bot.formatter import format_match, format_daily_summary, format_roi_stats
from config import config

logger = logging.getLogger(__name__)

LEAGUES_DISPLAY = {
    39:  "🏴 Premier League",
    140: "🇪🇸 La Liga",
    135: "🇮🇹 Serie A",
    78:  "🇩🇪 Bundesliga",
    61:  "🇫🇷 Ligue 1",
    2:   "🏆 Champions League",
    3:   "🏆 Europa League",
}


# ─── Helpers ─────────────────────────────────────────────────────────────────

def get_analyzer(context: ContextTypes.DEFAULT_TYPE) -> FootballAnalyzerV3:
    return context.bot_data["analyzer"]


def split_send(text: str, max_len: int = 4000) -> list:
    return [text[i:i + max_len] for i in range(0, len(text), max_len)]


async def analyze_league_full(league_id: int) -> list:
    """Descarga cuotas + análisis completo para una liga."""
    analyzer = FootballAnalyzerV3()

    # Pre-cargar ELO desde standings
    standings = get_standings(league_id)
    if standings:
        analyzer.elo.load_from_standings(standings)

    odds_data = get_odds_for_league(league_id)
    results = []
    for match in odds_data:
        try:
            analysis = await analyzer.analyze(match)
            results.append(analysis)
        except Exception as e:
            logger.warning(f"Error analizando {match.get('home_team', '?')}: {e}")

    results.sort(key=lambda x: x.get("max_value", 0), reverse=True)
    return results


# ─── Handlers ────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "⚽ <b>Football Value Bot V3</b>\n\n"
        "Motor de 6 capas + DeepSeek IA que detecta <b>value bets</b> "
        "comparando probabilidades estimadas vs cuotas del mercado.\n\n"
        "<b>Mercados:</b> 1X2 (Resultado) + Over/Under 2.5\n\n"
        "<b>Comandos:</b>\n"
        "/hoy — Value bets del día (todas las ligas)\n"
        "/liga — Elegir liga específica\n"
        "/stats — Rendimiento histórico (ROI)\n"
        "/ayuda — Cómo funciona el modelo\n\n"
        "⚠️ <i>Herramienta educativa. No es consejo financiero.</i>"
    )
    await update.message.reply_text(msg, parse_mode="HTML")


async def cmd_hoy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔄 Analizando ligas principales…")

    all_results = []
    for league_id in [39, 140, 135, 78]:  # PL, LaLiga, SerieA, Bundesliga
        try:
            results = await analyze_league_full(league_id)
            all_results.extend(results)
        except Exception as e:
            logger.error(f"Liga {league_id}: {e}")

    summary = format_daily_summary(all_results, "📊 Value Bets de Hoy")
    for part in split_send(summary):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=part,
            parse_mode="HTML",
        )

    # Botón para ver detalles
    value_results = [r for r in all_results if r.get("has_value")][:8]
    if value_results:
        keyboard = [
            [InlineKeyboardButton(
                f"📋 {r['home'][:12]} vs {r['away'][:12]}",
                callback_data=f"detail:{i}"
            )]
            for i, r in enumerate(value_results)
        ]
        context.bot_data["last_results"] = value_results
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Selecciona un partido para ver análisis completo:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    await msg.delete()


async def cmd_liga(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(name, callback_data=f"league:{lid}")]
        for lid, name in LEAGUES_DISPLAY.items()
    ]
    await update.message.reply_text(
        "⚽ <b>Selecciona una liga:</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tracker = PredictionTracker()
    stats = tracker.get_stats()
    await update.message.reply_text(format_roi_stats(stats), parse_mode="HTML")


async def cmd_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🧮 <b>Cómo funciona el motor V3</b>\n\n"
        "<b>6 capas de análisis:</b>\n"
        "1️⃣ <b>Mercado (35%)</b> — Cuotas de +10 casas, línea Pinnacle\n"
        "2️⃣ <b>Poisson (25%)</b> — xG desde estadísticas reales de API-Football\n"
        "3️⃣ <b>ELO (15%)</b> — Rating dinámico pre-cargado desde clasificación\n"
        "4️⃣ <b>Features (15%)</b> — Forma últimos 5, rachas, H2H\n"
        "5️⃣ <b>DeepSeek IA (10%)</b> — Lesiones, motivación, contexto\n"
        "6️⃣ <b>Consenso</b> — Combina todo con pesos ponderados\n\n"
        "<b>Filtros de calidad:</b>\n"
        "✓ Valor &gt; 3%\n"
        "✓ Mínimo 5 bookmakers\n"
        "✓ Confianza &gt; 60%\n"
        "✓ Cuota entre 1.30 – 8.00\n"
        "✓ Acuerdo &gt; 66% entre modelos\n\n"
        "<b>Mercados:</b> 1X2 + Over/Under 2.5\n\n"
        "⚠️ <i>Valor positivo NO garantiza ganar cada vez. "
        "A largo plazo, las matemáticas están a tu favor.</i>"
    )
    await update.message.reply_text(msg, parse_mode="HTML")


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("league:"):
        league_id = int(data.split(":")[1])
        league_name = LEAGUES_DISPLAY.get(league_id, "Liga")
        await query.edit_message_text(
            f"🔄 Analizando <b>{league_name}</b>…",
            parse_mode="HTML",
        )
        results = await analyze_league_full(league_id)
        summary = format_daily_summary(results, f"📊 {league_name}")
        await query.edit_message_text(summary[:4000], parse_mode="HTML")

        value_results = [r for r in results if r.get("has_value")][:8]
        if value_results:
            keyboard = [
                [InlineKeyboardButton(
                    f"📋 {r['home'][:12]} vs {r['away'][:12]}",
                    callback_data=f"detail:{i}"
                )]
                for i, r in enumerate(value_results)
            ]
            context.bot_data["last_results"] = value_results
            await query.message.reply_text(
                "Ver análisis detallado:",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

    elif data.startswith("detail:"):
        idx = int(data.split(":")[1])
        results = context.bot_data.get("last_results", [])
        if idx < len(results):
            text = format_match(results[idx])
            for part in split_send(text):
                await query.message.reply_text(part, parse_mode="HTML")
        else:
            await query.edit_message_text("Partido no disponible. Usa /hoy de nuevo.")


# ─── Scheduler (reportes automáticos 2x/día) ─────────────────────────────────

async def scheduled_report(context: ContextTypes.DEFAULT_TYPE):
    """Envía reporte automático al chat configurado."""
    chat_id = config.telegram_chat_id
    if not chat_id:
        return

    all_results = []
    for league_id in config.target_leagues[:4]:
        try:
            results = await analyze_league_full(league_id)
            all_results.extend(results)
        except Exception as e:
            logger.error(f"Scheduler - Liga {league_id}: {e}")

    summary = format_daily_summary(all_results, "🤖 Reporte Automático")
    for part in split_send(summary):
        await context.bot.send_message(chat_id=chat_id, text=part, parse_mode="HTML")


# ─── Main ─────────────────────────────────────────────────────────────────────

def run():
    if not config.telegram_token:
        print("ERROR: TELEGRAM_TOKEN no configurado.")
        return

    app = Application.builder().token(config.telegram_token).build()
    app.bot_data["analyzer"] = FootballAnalyzerV3()
    app.bot_data["last_results"] = []

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("hoy", cmd_hoy))
    app.add_handler(CommandHandler("liga", cmd_liga))
    app.add_handler(CommandHandler("ligas", cmd_liga))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("ayuda", cmd_ayuda))
    app.add_handler(CallbackQueryHandler(callback_handler))

    # Scheduler: reportes a las 8:00 y 17:00 UTC
    if config.telegram_chat_id:
        jq = app.job_queue
        for hour in config.report_hours_utc:
            jq.run_daily(scheduled_report, time=dtime(hour=hour, minute=0, tzinfo=timezone.utc))
        logger.info(f"Scheduler activo: reportes a {config.report_hours_utc} UTC")

    logger.info("🚀 Bot V3 iniciado.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
