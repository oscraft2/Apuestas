"""
Formateador de mensajes para Telegram — salida limpia y enfocada
"""
from datetime import datetime


def format_match(analysis: dict) -> str:
    home = analysis.get("home", "?")
    away = analysis.get("away", "?")
    league = analysis.get("league_display") or analysis.get("league", "")
    country = analysis.get("country_name", "")

    lines = [f"🎯 <b>{home} vs {away}</b>"]
    if league:
        lines[0] += f"  |  {league}"
    if country:
        lines.append(f"🌍 {country}")

    t = analysis.get("time", "")
    if t:
        try:
            dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
            lines.append(f"📅 Kickoff {dt.strftime('%d/%m %H:%M')} UTC")
        except Exception:
            pass

    # Consenso 1X2
    c1x2 = analysis.get("consensus_1x2", {})
    if c1x2:
        p = c1x2.get("probs", {})
        fo = c1x2.get("fair_odds", {})
        lines.append(
            f"\n📊 <b>Lectura 1X2:</b>\n"
            f"  🏠 {p.get('home', 0):.1%} (justa: {fo.get('home', 0):.2f}) | "
            f"🤝 {p.get('draw', 0):.1%} | "
            f"✈️ {p.get('away', 0):.1%}"
        )

    # Consenso O/U
    cou = analysis.get("consensus_ou", {})
    if cou:
        p = cou.get("probs", {})
        lines.append(
            f"\n⚽ <b>Totales 2.5:</b>\n"
            f"  ⬆️ Over: {p.get('over', 0):.1%} | ⬇️ Under: {p.get('under', 0):.1%}"
        )

    # Poisson extra
    poi = analysis.get("poisson", {})
    if poi:
        lines.append(
            f"\n🎯 Score probable: <b>{poi.get('top_score', '?')}</b> "
            f"({poi.get('top_score_prob', 0):.1%})  |  "
            f"BTTS: {poi.get('btts', {}).get('yes', 0):.0%}"
        )

    # Value Bets
    vbs = analysis.get("value_bets", [])
    if vbs:
        lines.append("\n🔥 <b>Sugerencias con ventaja:</b>")
        for vb in vbs[:4]:
            label = vb.get("label") or vb.get("outcome", "?")
            bm = vb.get("bookmaker", "")
            bm_str = f" ({bm})" if bm else ""
            lines.append(
                f"  → {vb.get('market', '')} <b>{label}</b>\n"
                f"     @ {vb.get('odds', vb.get('best_odds', 0)):.2f}{bm_str} | "
                f"Edge: <b>+{vb.get('value', 0):.1%}</b> | "
                f"Stake Kelly: {vb.get('kelly', 0):.1%}"
            )

    # AI narrative
    ai = analysis.get("ai", {})
    if ai and ai.get("reasoning"):
        lines.append(f"\n🧠 <b>Lectura IA:</b> <i>{ai['reasoning'][:200]}</i>")

    # Confianza
    if c1x2:
        lines.append(
            f"\n📈 Convicción: {c1x2.get('confidence', 0):.0%} | "
            f"Acuerdo: {c1x2.get('agreement', 0):.0%} | "
            f"Modelos activos: {len(c1x2.get('models_used', []))}"
        )

    lines.append("\n⚠️ <i>Lectura estadística y de mercado. No constituye consejo financiero.</i>")
    return "\n".join(lines)


def format_daily_summary(results: list, title: str = "📊 Value Bets del Día") -> str:
    value_matches = [r for r in results if r.get("has_value")]
    value_matches.sort(key=lambda x: x.get("max_value", 0), reverse=True)

    lines = [f"<b>{title}</b>", f"{'─' * 32}"]
    lines.append(f"Partidos analizados: {len(results)} | Con valor: {len(value_matches)}")

    if not value_matches:
        lines.append("\nNo se detectaron value bets hoy.")
        lines.append("El mercado parece eficiente en esta jornada.")
        return "\n".join(lines)

    for match in value_matches[:6]:
        home = match.get("home", "?")
        away = match.get("away", "?")
        lines.append(f"\n⚽ <b>{home} vs {away}</b>")
        for vb in match.get("value_bets", [])[:2]:
            label = vb.get("label") or vb.get("outcome", "?")
            lines.append(
                f"  → {vb.get('market', '')} {label}: "
                f"+{vb.get('value', 0):.1%} @ {vb.get('odds', vb.get('best_odds', 0)):.2f}"
            )

    lines.append(f"\n{'─' * 32}")
    lines.append("⚠️ <i>Análisis estadístico, no consejo financiero.</i>")
    return "\n".join(lines)


def format_central_summary(
    highlights: list,
    all_count: int,
    value_count: int,
    title: str,
    run_label: str = "",
) -> str:
    """
    Resumen desde análisis central: prioriza los partidos más llamativos (ranking interno).
    """
    lines = [f"<b>{title}</b>", f"{'─' * 32}"]
    if run_label:
        lines.append(run_label)
    lines.append(
        f"Partidos analizados: {all_count} | Con valor EV+: {value_count} | "
        f"Destacados abajo: {len(highlights)}"
    )

    if not highlights:
        lines.append("\nSin datos de análisis central aún.")
        return "\n".join(lines)

    lines.append("\n<b>🔥 Mesa principal del ciclo</b> <i>(edge + consenso + narrativa)</i>")
    for match in highlights[:10]:
        home = match.get("home", "?")
        away = match.get("away", "?")
        lg = match.get("league", "")
        tag = "✅ " if match.get("has_value") else "📌 "
        lines.append(f"\n{tag}<b>{home} vs {away}</b>")
        if lg:
            lines[-1] += f" <i>({lg[:40]})</i>"
        vbs = match.get("value_bets") or []
        if vbs:
            for vb in vbs[:2]:
                label = vb.get("label") or vb.get("outcome", "?")
                lines.append(
                    f"  → {vb.get('market', '')} {label}: "
                    f"+{vb.get('value', 0):.1%} @ {vb.get('odds', vb.get('best_odds', 0)):.2f}"
                )
        else:
            c1 = match.get("consensus_1x2") or {}
            conf = c1.get("confidence", 0)
            lines.append(f"  <i>Sin edge dominante aún · convicción del modelo {conf:.0%}</i>")

    lines.append(f"\n{'─' * 32}")
    lines.append("⚠️ <i>Lectura estadística y de mercado. No constituye consejo financiero.</i>")
    return "\n".join(lines)


def format_channel_bulletin(
    highlights: list,
    all_count: int,
    value_count: int,
    leagues_done: list | None = None,
    last_run: str = "",
    next_run: str = "",
    hero_league: str = "",
) -> str:
    """
    Resumen más editorial para canal/grupo: titular, contexto y top partidos.
    """
    lines = [
        "📡 <b>ValueXPro | Apertura del ciclo</b>",
        f"{'─' * 32}",
    ]
    if last_run:
        try:
            ts = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
            lines.append(f"Actualización: {ts.strftime('%d/%m %H:%M')} UTC")
        except Exception:
            lines.append(f"Actualización: {last_run}")
    if next_run:
        try:
            ts = datetime.fromisoformat(next_run.replace("Z", "+00:00"))
            lines.append(f"Próxima pasada: {ts.strftime('%d/%m %H:%M')} UTC")
        except Exception:
            lines.append(f"Próxima pasada: {next_run}")
    if hero_league:
        lines.append(f"Foco operativo: <b>{hero_league}</b>")
    if leagues_done:
        lines.append(f"Radar activo: {', '.join(leagues_done[:6])}")

    lines.append(
        f"\nPartidos analizados: <b>{all_count}</b> | "
        f"Señales EV+: <b>{value_count}</b> | "
        f"Top seleccionados: <b>{len(highlights)}</b>"
    )

    if not highlights:
        lines.append("\nSin señales relevantes en el ciclo actual.")
        lines.append("⚠️ <i>Análisis estadístico, no consejo financiero.</i>")
        return "\n".join(lines)

    lines.append("\n<b>🔥 Radar editorial del ciclo</b>")
    for match in highlights[:5]:
        home = match.get("home", "?")
        away = match.get("away", "?")
        league = match.get("league", "")
        top = (match.get("value_bets") or [None])[0]
        c1 = match.get("consensus_1x2") or {}
        conf = c1.get("confidence", 0)
        tag = "✅" if match.get("has_value") else "📌"
        line = f"\n{tag} <b>{home} vs {away}</b>"
        if league:
            line += f" <i>({league})</i>"
        lines.append(line)
        if top:
            label = top.get("label") or top.get("outcome", "?")
            lines.append(
                f"  → Sugerencia líder: {top.get('market', '')} {label} "
                f"(edge +{top.get('value', 0):.1%} @ {top.get('odds', top.get('best_odds', 0)):.2f})"
            )
        else:
            lines.append(f"  → Seguimiento abierto: convicción modelo {conf:.0%}")

    lines.append(f"\n{'─' * 32}")
    lines.append("⚠️ <i>Lectura estadística y de mercado. No constituye consejo financiero.</i>")
    return "\n".join(lines)


def format_operational_status(
    last_run: str = "",
    next_run: str = "",
    runs_today: int = 0,
    match_count: int = 0,
    value_count: int = 0,
    highlight_count: int = 0,
    hero_league: str = "",
) -> str:
    """
    Estado corto para Telegram / comando /estado.
    """
    lines = [
        "🧭 <b>Control operativo del motor</b>",
        f"{'─' * 32}",
        f"Pasadas hoy: <b>{runs_today}</b>",
        f"Partidos en caché: <b>{match_count}</b>",
        f"Señales EV+: <b>{value_count}</b>",
        f"Destacados: <b>{highlight_count}</b>",
    ]
    if hero_league:
        lines.append(f"Liga prioritaria: <b>{hero_league}</b>")
    if last_run:
        try:
            ts = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
            lines.append(f"Última actualización: {ts.strftime('%d/%m %H:%M')} UTC")
        except Exception:
            lines.append(f"Última actualización: {last_run}")
    if next_run:
        try:
            ts = datetime.fromisoformat(next_run.replace("Z", "+00:00"))
            lines.append(f"Próxima pasada: {ts.strftime('%d/%m %H:%M')} UTC")
        except Exception:
            lines.append(f"Próxima pasada: {next_run}")
    return "\n".join(lines)


def format_roi_stats(stats: dict) -> str:
    if not stats or stats.get("total_bets", 0) == 0:
        return "📈 Sin predicciones registradas aún."

    pnl = stats.get("pnl_units", 0)
    roi = stats.get("roi_pct", 0)
    hr = stats.get("hit_rate", 0)
    pnl_emoji = "📈" if pnl >= 0 else "📉"

    lines = [
        "<b>📊 Rendimiento histórico</b>",
        f"{'─' * 32}",
        f"Apuestas totales: {stats['total_bets']}",
        f"Acertadas: {stats['won']} | Falladas: {stats['lost']} | Pendientes: {stats.get('pending', 0)}",
        f"Hit rate: <b>{hr:.1%}</b>",
        f"{pnl_emoji} P&L: <b>{pnl:+.2f} u</b>",
        f"ROI: <b>{roi:+.1f}%</b>",
    ]

    by_market = stats.get("by_market", {})
    if by_market:
        lines.append("\n<b>Por mercado:</b>")
        for market, s in by_market.items():
            settled = s["won"] + s["lost"]
            hr_m = s["won"] / settled if settled else 0
            lines.append(
                f"  {market}: {s['won']}/{settled} aciertos | "
                f"P&L: {s['pnl']:+.2f}u | HR: {hr_m:.0%}"
            )

    return "\n".join(lines)
