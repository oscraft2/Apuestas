"""
Bot de Telegram V3 — COMPLETO con todas las features premium
Comandos:
  /start /hoy /liga /stats /ayuda
  /bankroll — gestión de bankroll personal
  /backtest — backtesting histórico
  /calibracion — calibración por liga
  /perfil — tier, alertas, límites
  /premium — info de planes
  /entrenar — re-entrena modelo XGBoost
  /previa — análisis pre-partido 3h antes
"""
import asyncio
import logging
from datetime import timezone, time as dtime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from src.engine import FootballAnalyzerV3
from src.data.football_api import get_standings
from src.data.odds_api import get_odds_for_league
from src.tracking.tracker import PredictionTracker
from src.backtest.backtester import Backtester
from src.bankroll.manager import BankrollManager
from src.analytics.calibration import LeagueCalibration
from src.alerts.odds_monitor import OddsMonitor, OddsPollingService
from src.users.manager import UserManager
from src.ml.trainer import XGBoostModel
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

# ── Singletons globales ────────────────────────────────────────────────────────
_analyzer: FootballAnalyzerV3 | None = None
_user_mgr = UserManager()
_bankroll_mgr = BankrollManager()
_tracker = PredictionTracker()
_backtester = Backtester(f"{config.predictions_dir}/predictions.jsonl")
_calibration = LeagueCalibration()
_odds_monitor = OddsMonitor()
_xgb = XGBoostModel()


def get_analyzer() -> FootballAnalyzerV3:
    global _analyzer
    if _analyzer is None:
        _analyzer = FootballAnalyzerV3()
    return _analyzer


def split_send(text: str, max_len: int = 4000) -> list[str]:
    return [text[i:i + max_len] for i in range(0, len(text), max_len)]


async def analyze_league_full(league_id: int) -> list:
    analyzer = get_analyzer()
    standings = get_standings(league_id)
    if standings:
        analyzer.elo.load_from_standings(standings)
    odds_data = get_odds_for_league(league_id)
    results = []
    for match in odds_data:
        try:
            result = await analyzer.analyze(match)
            # Enriquecer con XGBoost si disponible
            if _xgb.is_available and result.get("has_value"):
                xgb_prob = _xgb.predict_proba(result)
                if xgb_prob is not None:
                    result["xgb_win_prob"] = xgb_prob
            results.append(result)
        except Exception as e:
            logger.warning(f"Error analizando {match.get('home_team', '?')}: {e}")
    results.sort(key=lambda x: x.get("max_value", 0), reverse=True)
    return results


def require_premium(func):
    """Decorador: comprueba que el usuario sea premium antes de ejecutar."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        user = _user_mgr.get_or_create(uid, update.effective_user.username or "")
        if not user.is_premium:
            await update.message.reply_text(
                "💎 Esta función requiere <b>Premium</b>.\n\n"
                "Usa /premium para ver los planes disponibles.",
                parse_mode="HTML",
            )
            return
        return await func(update, context)
    wrapper.__name__ = func.__name__
    return wrapper


# ── Handlers base ──────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    _user_mgr.get_or_create(uid, update.effective_user.username or "")
    await update.message.reply_text(
        "⚽ <b>Football Value Bot V3</b>\n\n"
        "Motor de 6 capas + DeepSeek IA para detectar <b>value bets</b>.\n\n"
        "<b>Comandos principales:</b>\n"
        "/hoy — Value bets del día\n"
        "/liga — Análisis por liga\n"
        "/stats — Tu rendimiento (ROI)\n"
        "/bankroll — Gestiona tu bankroll\n"
        "/backtest — Backtesting histórico\n"
        "/calibracion — Precisión por liga\n"
        "/perfil — Tu plan y límites\n"
        "/premium — Planes Premium\n"
        "/ayuda — Cómo funciona\n\n"
        "⚠️ <i>Herramienta educativa. No es consejo financiero.</i>",
        parse_mode="HTML",
    )


async def cmd_hoy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = _user_mgr.get_or_create(uid, update.effective_user.username or "")

    if not user.can_receive_alert():
        await update.message.reply_text(
            f"⏳ Límite diario alcanzado ({user.limits['daily_alerts']} alertas).\n"
            "Vuelve mañana o actualiza a /premium para alertas ilimitadas."
        )
        return

    msg = await update.message.reply_text("🔄 Analizando ligas principales…")
    all_results = []
    for league_id in config.target_leagues[:4]:
        try:
            results = await analyze_league_full(league_id)
            all_results.extend(results)
        except Exception as e:
            logger.error(f"Liga {league_id}: {e}")

    _user_mgr.record_alert(uid)

    summary = format_daily_summary(all_results, "📊 Value Bets de Hoy")
    for part in split_send(summary):
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text=part, parse_mode="HTML"
        )

    value_results = [r for r in all_results if r.get("has_value")][:8]
    if value_results:
        keyboard = [
            [InlineKeyboardButton(
                f"📋 {r['home'][:12]} vs {r['away'][:12]}",
                callback_data=f"detail:{i}",
            )]
            for i, r in enumerate(value_results)
        ]
        context.bot_data["last_results"] = value_results
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Ver análisis detallado:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    # Añadir stakes si el usuario tiene bankroll
    br = _bankroll_mgr.get(uid)
    if br and value_results:
        vbs_flat = [vb for r in value_results for vb in r.get("value_bets", [])]
        stakes_msg = _bankroll_mgr.format_stake_suggestion(uid, vbs_flat[:4])
        if stakes_msg:
            await context.bot.send_message(
                chat_id=update.effective_chat.id, text=stakes_msg, parse_mode="HTML"
            )

    await msg.delete()


async def cmd_liga(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cal = _calibration.compute()
    keyboard = []
    for lid, name in LEAGUES_DISPLAY.items():
        grade = cal.get(name.split(" ", 1)[-1], {}).get("grade", "")
        grade_emoji = {"A": "🟢", "B": "🟡", "C": "🟠", "D": "🔴"}.get(grade, "⚪")
        keyboard.append([InlineKeyboardButton(
            f"{grade_emoji} {name}", callback_data=f"league:{lid}"
        )])
    await update.message.reply_text(
        "⚽ <b>Selecciona una liga:</b>\n<i>Color = calibración del modelo</i>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = _tracker.get_stats()
    await update.message.reply_text(format_roi_stats(stats), parse_mode="HTML")


async def cmd_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🧮 <b>Cómo funciona el motor V3</b>\n\n"
        "<b>6 capas de análisis:</b>\n"
        "1️⃣ <b>Mercado (35%)</b> — Línea sharp Pinnacle\n"
        "2️⃣ <b>Poisson (25%)</b> — xG desde stats reales\n"
        "3️⃣ <b>ELO (15%)</b> — Rating dinámico desde standings\n"
        "4️⃣ <b>Features (15%)</b> — Forma, rachas, H2H\n"
        "5️⃣ <b>DeepSeek IA (10%)</b> — Lesiones, motivación\n"
        "6️⃣ <b>Consenso</b> — Pesos ponderados\n\n"
        "<b>Features premium:</b>\n"
        "📊 /backtest — ROI histórico real\n"
        "🔴 Alertas steam/reverse automáticas\n"
        "💰 /bankroll — Kelly en €/$\n"
        "🎯 /calibracion — Precisión por liga\n"
        "🤖 XGBoost ML sobre historial acumulado\n\n"
        "⚠️ <i>Análisis estadístico, no consejo financiero.</i>",
        parse_mode="HTML",
    )


# ── Bankroll ───────────────────────────────────────────────────────────────────

async def cmd_bankroll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = _user_mgr.get_or_create(uid, update.effective_user.username or "")

    args = context.args
    if not args:
        # Mostrar estado actual
        await update.message.reply_text(
            _bankroll_mgr.format_status(uid), parse_mode="HTML"
        )
        return

    # /bankroll 500 | /bankroll 500 USD | /bankroll reset | /bankroll reset 300
    cmd = args[0].lower()

    if cmd == "reset":
        new_amount = float(args[1]) if len(args) > 1 else None
        try:
            _bankroll_mgr.reset(uid, new_amount)
            await update.message.reply_text("✅ Bankroll reiniciado.", parse_mode="HTML")
        except KeyError:
            await update.message.reply_text("Sin bankroll previo. Usa /bankroll <cantidad>")
        return

    try:
        amount = float(cmd)
        currency = args[1].upper() if len(args) > 1 and args[1].upper() in ("EUR", "USD", "GBP") else "EUR"
        existing = _bankroll_mgr.get(uid)
        if existing:
            _bankroll_mgr.update(uid, amount)
            await update.message.reply_text(
                f"✅ Bankroll actualizado a {amount:.2f} {currency}.", parse_mode="HTML"
            )
        else:
            if not user.is_premium:
                await update.message.reply_text(
                    "💎 El bankroll personal requiere <b>Premium</b>.\n"
                    "Usa /premium para más info.",
                    parse_mode="HTML",
                )
                return
            _bankroll_mgr.create(uid, update.effective_user.username or "", amount, currency)
            await update.message.reply_text(
                f"✅ Bankroll configurado: {amount:.2f} {currency}\n\n"
                f"{_bankroll_mgr.format_status(uid)}",
                parse_mode="HTML",
            )
    except ValueError:
        await update.message.reply_text(
            "Uso: /bankroll 500 | /bankroll 500 USD | /bankroll reset"
        )


# ── Backtesting ────────────────────────────────────────────────────────────────

@require_premium
async def cmd_backtest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔄 Ejecutando backtesting…")
    result = _backtester.run()
    text = _backtester.format_summary(result)
    await msg.edit_text(text, parse_mode="HTML")


# ── Calibración ────────────────────────────────────────────────────────────────

@require_premium
async def cmd_calibracion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔄 Calculando calibración…")
    text = _calibration.format_report()
    await msg.edit_text(text, parse_mode="HTML")


# ── Perfil y premium ───────────────────────────────────────────────────────────

async def cmd_perfil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    _user_mgr.get_or_create(uid, update.effective_user.username or "")
    await update.message.reply_text(
        _user_mgr.format_profile(uid), parse_mode="HTML"
    )


async def cmd_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💎 <b>ValueXPro Premium</b>\n\n"
        "<b>🆓 Free (gratis):</b>\n"
        "✓ 3 alertas de value bets al día\n"
        "✓ Resumen diario + análisis básico\n\n"
        "<b>💎 Premium (~€9.99/mes):</b>\n"
        "✓ Alertas ilimitadas\n"
        "✓ Alertas steam/reverse en tiempo real\n"
        "✓ Bankroll personal + Kelly en €/$\n"
        "✓ Backtesting histórico completo\n"
        "✓ Calibración por liga (Brier score)\n"
        "✓ Análisis pre-partido 3h antes\n"
        "✓ Modelo XGBoost sobre tu historial\n\n"
        "💳 Contacta @admin para suscribirte.",
        parse_mode="HTML",
    )


# ── Entrenamiento XGBoost ──────────────────────────────────────────────────────

@require_premium
async def cmd_entrenar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🤖 Entrenando modelo XGBoost…")
    result = _xgb.train(f"{config.predictions_dir}/predictions.jsonl")
    text = _xgb.format_train_result(result)
    await msg.edit_text(text, parse_mode="HTML")


# ── Análisis pre-partido (3h antes) ───────────────────────────────────────────

@require_premium
async def cmd_previa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Re-analiza con cuotas frescas los partidos en las próximas 3h."""
    msg = await update.message.reply_text("🔄 Buscando partidos en las próximas 3h…")
    from datetime import datetime, timezone, timedelta

    cutoff = datetime.now(timezone.utc) + timedelta(hours=3)
    found = []

    for league_id in config.target_leagues[:4]:
        try:
            results = await analyze_league_full(league_id)
            for r in results:
                t_str = r.get("time", "")
                if not t_str:
                    continue
                try:
                    t = datetime.fromisoformat(t_str.replace("Z", "+00:00"))
                    if datetime.now(timezone.utc) <= t <= cutoff:
                        found.append(r)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Previa liga {league_id}: {e}")

    if not found:
        await msg.edit_text("No hay partidos con value en las próximas 3h.")
        return

    found.sort(key=lambda x: x.get("max_value", 0), reverse=True)
    await msg.edit_text(f"⏰ <b>{len(found)} partidos próximos con valor:</b>", parse_mode="HTML")

    for r in found[:5]:
        for part in split_send(format_match(r)):
            await context.bot.send_message(
                chat_id=update.effective_chat.id, text=part, parse_mode="HTML"
            )


# ── Callback handler ───────────────────────────────────────────────────────────

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("league:"):
        try:
            league_id = int(data.split(":")[1])
        except (ValueError, IndexError):
            await query.edit_message_text("Liga no válida.")
            return
        league_name = LEAGUES_DISPLAY.get(league_id, "Liga")
        await query.edit_message_text(
            f"🔄 Analizando <b>{league_name}</b>…", parse_mode="HTML"
        )
        results = await analyze_league_full(league_id)
        summary = format_daily_summary(results, f"📊 {league_name}")
        await query.edit_message_text(summary[:4000], parse_mode="HTML")

        value_results = [r for r in results if r.get("has_value")][:8]
        if value_results:
            keyboard = [
                [InlineKeyboardButton(
                    f"📋 {r['home'][:12]} vs {r['away'][:12]}",
                    callback_data=f"detail:{i}",
                )]
                for i, r in enumerate(value_results)
            ]
            context.bot_data["last_results"] = value_results
            await query.message.reply_text(
                "Ver análisis detallado:",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

    elif data.startswith("detail:"):
        try:
            idx = int(data.split(":")[1])
        except (ValueError, IndexError):
            await query.edit_message_text("Selección no válida.")
            return
        results = context.bot_data.get("last_results", [])
        if 0 <= idx < len(results):
            uid = update.effective_user.id
            match = results[idx]
            text = format_match(match)
            # Añadir stakes personalizados si tiene bankroll
            vbs = match.get("value_bets", [])
            if vbs:
                stakes = _bankroll_mgr.format_stake_suggestion(uid, vbs)
                if stakes:
                    text += stakes
            for part in split_send(text):
                await query.message.reply_text(part, parse_mode="HTML")
        else:
            await query.edit_message_text("Partido no disponible. Usa /hoy de nuevo.")


# ── Scheduler ─────────────────────────────────────────────────────────────────

async def scheduled_report(context: ContextTypes.DEFAULT_TYPE):
    chat_id = config.telegram_chat_id
    if not chat_id:
        return
    all_results = []
    for league_id in config.target_leagues[:4]:
        try:
            results = await analyze_league_full(league_id)
            all_results.extend(results)
        except Exception as e:
            logger.error(f"Scheduler liga {league_id}: {e}")
    summary = format_daily_summary(all_results, "🤖 Reporte Automático")
    for part in split_send(summary):
        await context.bot.send_message(chat_id=chat_id, text=part, parse_mode="HTML")


async def line_move_notify(context: ContextTypes.DEFAULT_TYPE):
    """Polling de movimientos de cuota — notifica a suscriptores premium."""
    from src.data.odds_api import get_odds_for_league
    for league_id in config.target_leagues[:4]:
        matches = get_odds_for_league(league_id)
        for match in matches:
            mid = match.get("id", "")
            bms = match.get("bookmakers", [])
            movements = _odds_monitor.detect_movements(mid, bms)
            for mv in movements:
                msg = (
                    f"🔔 <b>Movimiento de cuota detectado</b>\n\n"
                    + _odds_monitor.format_movement(mv)
                )
                for uid in _user_mgr.get_line_alert_subscribers():
                    try:
                        await context.bot.send_message(
                            chat_id=uid, text=msg, parse_mode="HTML"
                        )
                    except Exception:
                        pass
            _odds_monitor.update_snapshot(
                mid, bms,
                match.get("home_team", ""),
                match.get("away_team", ""),
                match.get("sport_title", ""),
            )


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    if not config.telegram_token:
        print("ERROR: TELEGRAM_TOKEN no configurado. Copia .env.example → .env")
        return

    app = Application.builder().token(config.telegram_token).build()
    app.bot_data["last_results"] = []

    # Comandos
    app.add_handler(CommandHandler("start",       cmd_start))
    app.add_handler(CommandHandler("hoy",         cmd_hoy))
    app.add_handler(CommandHandler("liga",        cmd_liga))
    app.add_handler(CommandHandler("ligas",       cmd_liga))
    app.add_handler(CommandHandler("stats",       cmd_stats))
    app.add_handler(CommandHandler("ayuda",       cmd_ayuda))
    app.add_handler(CommandHandler("bankroll",    cmd_bankroll))
    app.add_handler(CommandHandler("backtest",    cmd_backtest))
    app.add_handler(CommandHandler("calibracion", cmd_calibracion))
    app.add_handler(CommandHandler("perfil",      cmd_perfil))
    app.add_handler(CommandHandler("premium",     cmd_premium))
    app.add_handler(CommandHandler("entrenar",    cmd_entrenar))
    app.add_handler(CommandHandler("previa",      cmd_previa))
    app.add_handler(CallbackQueryHandler(callback_handler))

    jq = app.job_queue
    if config.telegram_chat_id:
        for hour in config.report_hours_utc:
            jq.run_daily(
                scheduled_report,
                time=dtime(hour=hour, minute=0, tzinfo=timezone.utc),
            )
    # Polling de movimientos de cuota cada 30 min
    jq.run_repeating(line_move_notify, interval=1800, first=60)

    logger.info("🚀 Football Value Bot V3 iniciado con todas las features premium.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
