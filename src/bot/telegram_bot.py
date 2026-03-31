"""
Bot de Telegram V3 — COMPLETO con todas las features premium
Comandos:
  /start /hoy /lideres /resumen /liga /stats /ayuda
  /mix — combinadas premium desde ValueX Prime
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
from datetime import datetime, timedelta, timezone, time as dtime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from src.tracking.tracker import PredictionTracker
from src.backtest.backtester import Backtester
from src.bankroll.manager import BankrollManager
from src.analytics.calibration import LeagueCalibration
from src.alerts.odds_monitor import OddsMonitor
from src.users.manager import UserManager
from src.ml.trainer import XGBoostModel
from src.bot.formatter import (
    format_match,
    format_daily_summary,
    format_daily_close,
    format_operational_status,
    format_power_mix,
    format_prime_board,
    format_roi_stats,
)
from src.analysis.central_runner import format_schedule_hint, next_run_utc, run_full_analysis
from src.analysis.runtime import finish as finish_analysis_run
from src.analysis.runtime import try_start as try_start_analysis_run
from src.league_labels import LEAGUES_DISPLAY, LEAGUE_NAMES, league_display_name
from src.tracking.result_sync import sync_pending_results
from config import config

logger = logging.getLogger(__name__)

# ── Singletons globales ────────────────────────────────────────────────────────
_user_mgr = UserManager()
_bankroll_mgr = BankrollManager()
_tracker = PredictionTracker()
_backtester = Backtester(f"{config.predictions_dir}/predictions.jsonl")
_calibration = LeagueCalibration()
_odds_monitor = OddsMonitor()
_xgb = XGBoostModel()


def split_send(text: str, max_len: int = 4000) -> list[str]:
    return [text[i:i + max_len] for i in range(0, len(text), max_len)]


async def _send_html_chunks(bot, chat_id: str | int, text: str, disable_preview: bool = True) -> int:
    sent = 0
    for part in split_send(text):
        await bot.send_message(
            chat_id=chat_id,
            text=part,
            parse_mode="HTML",
            disable_web_page_preview=disable_preview,
        )
        sent += 1
    return sent


async def _publish_channel_report(
    bot,
    chat_id: str | int,
    payload: dict,
    publish_kind: str = "scheduled",
) -> int:
    """
    Publicación editorial para canal/grupo: boletín central + detalle de los mejores partidos.
    """
    import src.shared_state as state

    highlights = payload.get("highlights") or []
    leaders = payload.get("leaders") or highlights
    mixes = payload.get("mixes") or []
    results = payload.get("results") or []
    leagues_done = payload.get("leagues_done") or []
    value_count = sum(1 for r in results if r.get("has_value"))
    bulletin = format_prime_board(
        leaders,
        mixes=mixes,
        all_count=len(results),
        value_count=value_count,
        title="📡 ValueX Prime | Apertura del ciclo",
        run_label=(
            f"Actualización {state.live.last_run[:19].replace('T', ' ')} UTC · "
            f"Radar activo: {', '.join(leagues_done[:6])}"
            if state.live.last_run
            else ""
        ),
    )
    parts_sent = await _send_html_chunks(bot, chat_id, bulletin)

    detail_candidates = [r for r in leaders if r.get("has_value")] or leaders
    if config.telegram_publish_match_details:
        for match in detail_candidates[: config.telegram_publish_top_matches]:
            parts_sent += await _send_html_chunks(bot, chat_id, format_match(match))

    state.record_publish(publish_kind, parts_sent, target=str(chat_id))
    return parts_sent


async def sync_results_job(context: ContextTypes.DEFAULT_TYPE):
    """Sincroniza resultados de partidos pasados con la DB (periódico)."""
    try:
        from src.tracking.result_sync import sync_pending_results
        result = sync_pending_results()
        synced = result.get("updated", 0) if isinstance(result, dict) else (result or 0)
        if synced:
            logger.info("sync_results_job: %d resultados actualizados", synced)
    except Exception as e:
        logger.warning("sync_results_job error: %s", e)


async def startup_warmup(context: ContextTypes.DEFAULT_TYPE):
    """
    Calienta la caché al iniciar `both` para que la web y Telegram no arranquen vacíos.
    """
    import src.shared_state as state

    if not config.auto_warmup_on_start:
        return
    from src.shared_state import is_cache_ready_today

    if is_cache_ready_today():
        return
    if not try_start_analysis_run("startup"):
        logger.info("Warmup inicial omitido: otro análisis ya está en curso")
        return

    try:
        logger.info("Warmup inicial: ejecutando análisis central al arrancar")
        payload = await run_full_analysis()
        state.update(
            payload["results"],
            payload["leagues_done"],
            payload["highlights"],
            payload.get("leaders"),
            payload.get("mixes"),
        )
        if config.telegram_chat_id and config.auto_publish_startup_report:
            await _publish_channel_report(
                context.bot,
                config.telegram_chat_id,
                payload,
                publish_kind="startup",
            )
    finally:
        finish_analysis_run()


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


def _resolve_summary_reports() -> tuple[dict, dict]:
    today = datetime.now(timezone.utc).date().isoformat()
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
    leader_today = _tracker.get_daily_report(today, leaders_only=True)
    report_today = _tracker.get_daily_report(today)
    if report_today.get("settled", 0) > 0 or leader_today.get("settled", 0) > 0:
        return report_today, leader_today
    return _tracker.get_daily_report(yesterday), _tracker.get_daily_report(yesterday, leaders_only=True)


# ── Handlers base ──────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    _user_mgr.get_or_create(uid, update.effective_user.username or "")
    await update.message.reply_text(
        "⚽ <b>ValueXPro Intelligence Bot</b>\n\n"
        "Radar central con ValueX Prime, PowerMix y lectura editorial para detectar ventajas de cuota y priorizar la jornada.\n\n"
        "<b>Comandos principales:</b>\n"
        "/hoy — Mesa Prime del último ciclo\n"
        "/lideres — Picks líderes oficiales del día\n"
        "/resumen — Cierre y estadísticas reales del día\n"
        "/estado — Salud operativa del motor y próxima pasada\n"
        "/liga — Lectura por liga\n"
        "/mix — Combinadas desde los picks líderes\n"
        "/stats — Rendimiento del tracker\n"
        "/bankroll — Gestión de stake personal\n"
        "/backtest — Historial y robustez del modelo\n"
        "/calibracion — Precisión por liga\n"
        "/perfil — Tu plan y límites\n"
        "/premium — Acceso ampliado\n"
        "/ayuda — Método y arquitectura\n\n"
        "⚠️ <i>Herramienta educativa. No constituye consejo financiero.</i>",
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

    import src.shared_state as state

    today = datetime.now(timezone.utc).date().isoformat()
    has_cache = bool(
        state.live.last_run
        and state.live.last_run[:10] == today
        and state.live.today_results
    )

    if not has_cache:
        await update.message.reply_text(
            "📭 <b>Aún no hay análisis del día en memoria.</b>\n\n"
            "El motor corre de forma <b>centralizada</b> "
            f"{len(config.report_hours_utc)} veces al día (UTC).\n"
            f"{format_schedule_hint()}\n\n"
            "Tras la próxima pasada automática, <code>/hoy</code> mostrará el resumen "
            "sin volver a gastar APIs.",
            parse_mode="HTML",
        )
        return

    all_results = state.live.today_results
    highlights = state.live.highlight_results or all_results[: config.highlight_top_n]
    leaders = getattr(state.live, "leader_results", []) or highlights[: config.leader_top_n]
    mixes = getattr(state.live, "leader_mixes", []) or []
    value_count = sum(1 for r in all_results if r.get("has_value"))
    run_note = (
        f"Pasada #{state.live.runs_today} hoy · última actualización "
        f"{state.live.last_run[:19].replace('T', ' ')} UTC"
    )
    summary = format_prime_board(
        leaders,
        mixes=mixes,
        all_count=len(all_results),
        value_count=value_count,
        title="🏆 ValueX Prime del ciclo central",
        run_label=run_note,
    )
    _user_mgr.record_alert(uid)

    for part in split_send(summary):
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text=part, parse_mode="HTML"
        )

    detail_pool = [r for r in leaders if r.get("has_value")][:8]
    if not detail_pool:
        detail_pool = leaders[:8] or highlights[:8]
    if detail_pool:
        keyboard = [
            [InlineKeyboardButton(
                f"📋 {r['home'][:12]} vs {r['away'][:12]}",
                callback_data=f"detail:{i}",
            )]
            for i, r in enumerate(detail_pool)
        ]
        context.bot_data["last_results"] = detail_pool
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Ver análisis detallado:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    br = _bankroll_mgr.get(uid)
    if br and detail_pool:
        vbs_flat = [vb for r in detail_pool for vb in r.get("value_bets", [])]
        stakes_msg = _bankroll_mgr.format_stake_suggestion(uid, vbs_flat[:4])
        if stakes_msg:
            await context.bot.send_message(
                chat_id=update.effective_chat.id, text=stakes_msg, parse_mode="HTML"
            )


async def cmd_lideres(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = _user_mgr.get_or_create(uid, update.effective_user.username or "")
    if not user.can_receive_alert():
        await update.message.reply_text(
            f"⏳ Límite diario alcanzado ({user.limits['daily_alerts']} alertas).\n"
            "Vuelve mañana o actualiza a /premium para alertas ilimitadas."
        )
        return

    import src.shared_state as state

    leaders = getattr(state.live, "leader_results", []) or []
    mixes = getattr(state.live, "leader_mixes", []) or []
    if not leaders:
        await update.message.reply_text(
            "📭 Aún no hay ValueX Prime cargado.\n\n" + format_schedule_hint(),
            parse_mode="HTML",
        )
        return

    _user_mgr.record_alert(uid)
    text = format_prime_board(
        leaders,
        mixes=mixes,
        all_count=len(state.live.today_results or []),
        value_count=sum(1 for r in (state.live.today_results or []) if r.get("has_value")),
        title="🏆 ValueX Prime del día",
        run_label=f"Última actualización {state.live.last_run[:19].replace('T', ' ')} UTC" if state.live.last_run else "",
    )
    for part in split_send(text):
        await context.bot.send_message(chat_id=update.effective_chat.id, text=part, parse_mode="HTML")


@require_premium
async def cmd_mix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import src.shared_state as state

    mixes = getattr(state.live, "leader_mixes", []) or []
    text = format_power_mix(mixes, title="⚙️ ValueX PowerMix")
    for part in split_send(text):
        await context.bot.send_message(chat_id=update.effective_chat.id, text=part, parse_mode="HTML")


async def cmd_resumen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sync_pending_results(_tracker)
    report, leader_report = _resolve_summary_reports()
    text = format_daily_close(report, leader_report)
    for part in split_send(text):
        await update.message.reply_text(part, parse_mode="HTML")


async def cmd_liga(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cal = _calibration.compute()
    keyboard = []
    for lid in config.target_leagues:
        name = LEAGUES_DISPLAY.get(lid, f"⚽ {LEAGUE_NAMES.get(lid, str(lid))}")
        plain = LEAGUE_NAMES.get(lid, name.split(" ", 1)[-1] if " " in str(name) else str(name))
        grade = cal.get(plain, {}).get("grade", "")
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


async def cmd_estado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import src.shared_state as state

    live = state.live
    nxt = next_run_utc()
    text = format_operational_status(
        last_run=live.last_run or "",
        next_run=nxt.isoformat() if nxt else "",
        runs_today=getattr(live, "runs_today", 0),
        match_count=len(live.today_results or []),
        value_count=live.total_value_bets or 0,
        highlight_count=len(live.highlight_results or []),
        hero_league=league_display_name(config.hero_league_id),
    )
    if live.last_publish_utc:
        text += (
            f"\nÚltima publicación: {live.last_publish_utc[:19].replace('T', ' ')} UTC"
            f" ({live.last_publish_kind or 'telegram'})"
        )
    await update.message.reply_text(text, parse_mode="HTML")


async def cmd_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🧮 <b>Cómo trabaja el motor ValueXPro</b>\n\n"
        "<b>6 capas de análisis:</b>\n"
        "1️⃣ <b>Mercado (35%)</b> — Línea sharp Pinnacle\n"
        "2️⃣ <b>Poisson (25%)</b> — xG desde stats reales\n"
        "3️⃣ <b>ELO (15%)</b> — Rating dinámico desde standings\n"
        "4️⃣ <b>Features (15%)</b> — Forma, rachas, H2H\n"
        "5️⃣ <b>DeepSeek IA (10%)</b> — Lesiones, motivación\n"
        "6️⃣ <b>Consenso</b> — Pesos ponderados\n\n"
        "<b>Mercados activos:</b>\n"
        "🎯 1X2\n"
        "⚽ O/U 2.5\n"
        "⚡ O/U 1.5\n"
        "✅ BTTS\n\n"
        "<b>Capa editorial:</b>\n"
        "🏆 ValueX Prime — picks líderes oficiales del día\n"
        "⚙️ ValueX PowerMix — combinadas desde líderes\n"
        "📘 /resumen — cierre con estadística real del día\n\n"
        "<b>Features premium:</b>\n"
        "📊 /backtest — ROI histórico real\n"
        "🔴 Alertas steam/reverse automáticas\n"
        "💰 /bankroll — Kelly en €/$\n"
        "🎯 /calibracion — Precisión por liga\n"
        "🤖 XGBoost ML sobre historial acumulado\n"
        "⚙️ /mix — combinadas premium desde Prime Picks\n\n"
        "<b>Automatización:</b>\n"
        "🤖 /estado — salud del motor y próxima pasada\n"
        "🗞️ El canal recibe boletines centralizados con picks priorizados\n"
        "📘 Se sincronizan resultados para medir éxitos reales del día\n\n"
        "⚠️ <i>Lectura estadística y de mercado. No constituye consejo financiero.</i>",
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
        "✓ 3 alertas con edge al día\n"
        "✓ ValueX Prime base + lectura del radar\n"
        "✓ Resumen diario base\n\n"
        "<b>💎 Premium (~€9.99/mes):</b>\n"
        "✓ Alertas ilimitadas\n"
        "✓ Alertas steam/reverse en tiempo real\n"
        "✓ Bankroll personal + Kelly en €/$\n"
        "✓ Backtesting histórico completo\n"
        "✓ Calibración por liga (Brier score)\n"
        "✓ Análisis pre-partido 3h antes\n"
        "✓ Modelo XGBoost sobre tu historial\n\n"
        "✓ ValueX PowerMix desde picks líderes\n"
        "✓ Cierre operativo del día y lectura premium del canal\n\n"
        "💳 Contacta al operador para activar acceso ampliado.\n"
        "Si ya te activaron, usa /perfil para confirmar tu Telegram ID y el plan aplicado.",
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
    """Partidos con valor en las próximas 3h según último análisis central."""
    import src.shared_state as state
    from datetime import timedelta

    msg = await update.message.reply_text("🔄 Filtrando último análisis central…")
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=3)
    cached = state.live.today_results or []

    if not cached:
        await msg.edit_text(
            "No hay caché de análisis aún.\n" + format_schedule_hint(),
            parse_mode="HTML",
        )
        return

    found = []
    for r in cached:
        if not r.get("has_value"):
            continue
        t_str = r.get("time", "")
        if not t_str:
            continue
        try:
            t = datetime.fromisoformat(t_str.replace("Z", "+00:00"))
            if now <= t <= cutoff:
                found.append(r)
        except Exception:
            pass

    if not found:
        await msg.edit_text(
            "No hay partidos con value en las próximas 3h según el último análisis central.\n"
            + format_schedule_hint(),
            parse_mode="HTML",
        )
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
        import src.shared_state as state
        try:
            league_id = int(data.split(":")[1])
        except (ValueError, IndexError):
            await query.edit_message_text("Liga no válida.")
            return
        league_name = LEAGUES_DISPLAY.get(league_id, "Liga")
        cached = state.live.today_results or []
        results = [r for r in cached if r.get("league_id") == league_id]

        if not results:
            await query.edit_message_text(
                f"📭 Sin datos en caché para <b>{league_name}</b>.\n\n"
                f"{format_schedule_hint()}",
                parse_mode="HTML",
            )
            return

        summary = format_daily_summary(results, f"📊 {league_name} · último análisis central")
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
    import src.shared_state as state

    if not try_start_analysis_run("scheduled"):
        logger.info("Scheduler omitido: otro análisis central sigue en curso")
        return

    payload = None
    try:
        payload = await run_full_analysis()
        state.update(
            payload["results"],
            payload["leagues_done"],
            payload["highlights"],
            payload.get("leaders"),
            payload.get("mixes"),
        )
    except Exception as exc:
        logger.error("Scheduler: fallo ejecutando análisis central: %s", exc)
        return
    finally:
        finish_analysis_run()

    chat_id = config.telegram_chat_id
    if not chat_id or not payload:
        return
    await _publish_channel_report(
        context.bot,
        chat_id,
        payload,
        publish_kind="scheduled",
    )


async def line_move_notify(context: ContextTypes.DEFAULT_TYPE):
    """Polling de movimientos de cuota — notifica a suscriptores premium."""
    from src.data.odds_api import get_odds_for_league
    for league_id in config.target_leagues:
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
                    except Exception as exc:
                        logger.warning("No se pudo enviar line move a %s: %s", uid, exc)
            _odds_monitor.update_snapshot(
                mid, bms,
                match.get("home_team", ""),
                match.get("away_team", ""),
                match.get("sport_title", ""),
            )


# ── Admin ─────────────────────────────────────────────────────────────────────

def require_admin(func):
    """Decorador: solo el ADMIN_USER_ID puede ejecutar el comando."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        if config.admin_user_id and uid != config.admin_user_id:
            await update.message.reply_text("⛔ Acceso restringido.")
            return
        return await func(update, context)
    return wrapper


@require_admin
async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /admin — Panel de administración
    Subcomandos:
      /admin premium <user_id> [días]   — activa premium
      /admin free <user_id>             — revoca premium
      /admin info <user_id>             — info del usuario
      /admin users                      — lista usuarios recientes
      /admin stats                      — estadísticas globales
      /admin nota <user_id> <texto>     — añade nota al usuario
    """
    args = context.args or []

    if not args:
        await update.message.reply_text(
            "🛠 <b>Panel Admin — ValueXPro</b>\n\n"
            "/admin premium &lt;user_id&gt; [días] — Activar premium\n"
            "/admin free &lt;user_id&gt;           — Revocar premium\n"
            "/admin info &lt;user_id&gt;            — Info usuario\n"
            "/admin users                       — Lista de usuarios\n"
            "/admin stats                       — Estadísticas globales\n"
            "/admin nota &lt;user_id&gt; &lt;texto&gt;   — Añadir nota",
            parse_mode="HTML",
        )
        return

    sub = args[0].lower()

    # ── premium ────────────────────────────────────────────────────────────────
    if sub == "premium":
        if len(args) < 2:
            await update.message.reply_text("Uso: /admin premium <user_id> [días]")
            return
        try:
            target_id = int(args[1])
            days      = int(args[2]) if len(args) > 2 else 30
        except ValueError:
            await update.message.reply_text("user_id y días deben ser números.")
            return

        try:
            _user_mgr.activate_premium(target_id, days=days)
        except KeyError:
            _user_mgr.get_or_create(target_id)
            _user_mgr.activate_premium(target_id, days=days)

        # Notificar al usuario
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=(
                    "🎉 <b>¡Tu cuenta Premium ha sido activada!</b>\n\n"
                    f"Duración: {days} días\n\n"
                    "Ahora tienes acceso a todas las features:\n"
                    "✅ Value bets ilimitadas\n"
                    "✅ Alertas de movimiento de cuota\n"
                    "✅ Bankroll + Kelly personalizado\n"
                    "✅ Backtesting + calibración\n\n"
                    "Usa /perfil para ver tu estado."
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass

        await update.message.reply_text(
            f"✅ Premium activado para <b>{target_id}</b> por {days} días.",
            parse_mode="HTML",
        )

    # ── free ───────────────────────────────────────────────────────────────────
    elif sub == "free":
        if len(args) < 2:
            await update.message.reply_text("Uso: /admin free <user_id>")
            return
        try:
            target_id = int(args[1])
        except ValueError:
            await update.message.reply_text("user_id debe ser un número.")
            return
        _user_mgr.deactivate_premium(target_id)
        await update.message.reply_text(f"✅ Usuario {target_id} revertido a Free.")

    # ── info ───────────────────────────────────────────────────────────────────
    elif sub == "info":
        if len(args) < 2:
            await update.message.reply_text("Uso: /admin info <user_id>")
            return
        try:
            target_id = int(args[1])
        except ValueError:
            await update.message.reply_text("user_id debe ser un número.")
            return
        user = _user_mgr.get_or_create(target_id)
        br   = _bankroll_mgr.get(target_id)
        exp  = user.premium_until.isoformat()[:10] if user.premium_until else "—"
        lines = [
            f"👤 <b>Usuario {target_id}</b>",
            f"Username: @{user.username or '—'}",
            f"Plan: {user.tier.upper()} (hasta {exp})",
            f"Alertas hoy: {user.alerts_today} | Total: {user.total_alerts_sent}",
            f"Stripe: {user.stripe_customer_id or '—'}",
            f"Notas: {user.notes or '—'}",
        ]
        if br:
            lines.append(f"Bankroll: {br.current:.2f}{br.currency} (ROI {br.roi:+.1f}%)")
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    # ── users ──────────────────────────────────────────────────────────────────
    elif sub == "users":
        users = _user_mgr.list_users(limit=20)
        if not users:
            await update.message.reply_text("No hay usuarios registrados aún.")
            return
        lines = ["👥 <b>Últimos 20 usuarios</b>\n"]
        for u in users:
            tier_icon = "💎" if u.tier == "premium" else "🆓"
            lines.append(
                f"{tier_icon} <b>{u.user_id}</b> @{u.username or '—'} "
                f"| alertas: {u.total_alerts_sent}"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    # ── stats ──────────────────────────────────────────────────────────────────
    elif sub == "stats":
        stats  = _tracker.get_stats()
        users  = _user_mgr.list_users(limit=1000)
        n_prem = sum(1 for u in users if u.tier == "premium")
        msg = (
            f"📊 <b>Estadísticas globales</b>\n\n"
            f"👥 Usuarios totales: {len(users)}\n"
            f"💎 Usuarios premium: {n_prem}\n"
            f"🆓 Usuarios free: {len(users) - n_prem}\n\n"
            f"📈 Predicciones totales: {stats['total_bets']}\n"
            f"✅ Ganadoras: {stats['won']} | ❌ Perdedoras: {stats['lost']}\n"
            f"⏳ Pendientes: {stats['pending']}\n"
            f"Hit rate: {stats['hit_rate']:.1%}\n"
            f"P&L: {stats['pnl_units']:+.2f}u | ROI: {stats['roi_pct']:+.1f}%"
        )
        await update.message.reply_text(msg, parse_mode="HTML")

    # ── nota ───────────────────────────────────────────────────────────────────
    elif sub == "nota":
        if len(args) < 3:
            await update.message.reply_text("Uso: /admin nota <user_id> <texto>")
            return
        try:
            target_id = int(args[1])
        except ValueError:
            await update.message.reply_text("user_id debe ser un número.")
            return
        note = " ".join(args[2:])
        _user_mgr.set_note(target_id, note)
        await update.message.reply_text(f"📝 Nota guardada para {target_id}.")

    else:
        await update.message.reply_text(f"Subcomando desconocido: {sub}")


# ── Pagar (genera link de Stripe) ─────────────────────────────────────────────

async def cmd_pagar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Genera un link de pago de Stripe para suscribirse a Premium."""
    if not config.stripe_secret_key or not config.stripe_price_id:
        await update.message.reply_text(
            "💳 Para suscribirte a Premium contacta al administrador.\n"
            "El sistema de pago automático estará disponible pronto."
        )
        return

    uid = update.effective_user.id
    import stripe
    stripe.api_key = config.stripe_secret_key
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{"price": config.stripe_price_id, "quantity": 1}],
            mode="subscription",
            success_url="https://t.me/valuexpro_bot",
            cancel_url="https://t.me/valuexpro_bot",
            metadata={"telegram_user_id": str(uid)},
        )
        await update.message.reply_text(
            f"💳 <b>Suscripción Premium — ValueXPro</b>\n\n"
            f"Haz clic en el link para completar el pago seguro:\n"
            f'<a href="{session.url}">✅ Pagar con Stripe</a>\n\n'
            f"Tras el pago tu cuenta se activa automáticamente.",
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.error("Error Stripe checkout: %s", e)
        await update.message.reply_text("❌ Error generando el link de pago. Intenta más tarde.")


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
    app.add_handler(CommandHandler("lideres",     cmd_lideres))
    app.add_handler(CommandHandler("resumen",     cmd_resumen))
    app.add_handler(CommandHandler("mix",         cmd_mix))
    app.add_handler(CommandHandler("estado",      cmd_estado))
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
    app.add_handler(CommandHandler("admin",       cmd_admin))
    app.add_handler(CommandHandler("pagar",       cmd_pagar))
    app.add_handler(CallbackQueryHandler(callback_handler))

    jq = app.job_queue
    # Análisis central siempre (web + caché); el envío a Telegram opcional si hay TELEGRAM_CHAT_ID
    for hour in config.report_hours_utc:
        jq.run_daily(
            scheduled_report,
            time=dtime(hour=hour, minute=0, tzinfo=timezone.utc),
        )
    jq.run_once(startup_warmup, when=config.startup_analysis_delay_sec)
    jq.run_repeating(sync_results_job, interval=config.result_sync_interval_sec, first=120)
    # Polling de movimientos de cuota cada 30 min
    jq.run_repeating(line_move_notify, interval=config.line_move_poll_interval_sec, first=60)

    logger.info("🚀 ValueXPro Intelligence Bot iniciado con automatización editorial y capa premium.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
