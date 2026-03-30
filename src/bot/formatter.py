"""
Formateador de mensajes para Telegram — salida limpia y enfocada
"""
from datetime import datetime


def _stake_label(vb: dict | None, confidence: float = 0.0, stake_plan: dict | None = None) -> str:
    if stake_plan and stake_plan.get("units"):
        label = str(stake_plan.get("label") or "").strip().lower()
        units = stake_plan.get("units")
        return f"{units} {label}".strip()

    if not vb:
        if confidence >= 0.70:
            return "0.75u consenso fuerte"
        if confidence >= 0.60:
            return "0.50u seguimiento activo"
        if confidence > 0:
            return "0.25u lectura prudente"
        return "sin stake"
    value = float(vb.get("value") or 0)
    kelly = float(vb.get("kelly") or 0)
    if confidence >= 0.74 and (value >= 0.08 or kelly >= 0.06):
        return "1.50u alta"
    if confidence >= 0.68 and (value >= 0.05 or kelly >= 0.035):
        return "1.00u media"
    if confidence >= 0.60 or value >= 0.03 or kelly >= 0.02:
        return "0.75u util"
    return "0.50u prudente"


def _short_pick_line(pick: dict | None) -> str:
    if not pick:
        return "Sin pick oficial"
    selection = pick.get("selection") or pick.get("label") or pick.get("outcome", "?")
    odds = pick.get("odds", pick.get("best_odds", 0)) or pick.get("best_odds", 0) or 0
    return (
        f"{pick.get('market', 'Pick')} {selection} "
        f"@ {float(odds):.2f}"
    )


def format_match(analysis: dict) -> str:
    home = analysis.get("home", "?")
    away = analysis.get("away", "?")
    league = analysis.get("league_display") or analysis.get("league", "")
    country = analysis.get("country_name", "")

    lines = [f"🎯 <b>{home} vs {away}</b>"]
    if analysis.get("leader_name"):
        lines = [f"🏆 <b>{analysis.get('leader_name')}</b>", lines[0]]
    if league:
        lines[-1] += f"  |  {league}"
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

    cou15 = analysis.get("consensus_ou15", {})
    if cou15:
        p = cou15.get("probs", {})
        lines.append(
            f"\n⚡ <b>Totales 1.5:</b>\n"
            f"  ⬆️ Over: {p.get('over', 0):.1%} | ⬇️ Under: {p.get('under', 0):.1%}"
        )

    btts = analysis.get("consensus_btts", {})
    if btts:
        p = btts.get("probs", {})
        lines.append(
            f"\n🎯 <b>BTTS:</b>\n"
            f"  ✅ Sí: {p.get('yes', 0):.1%} | ❌ No: {p.get('no', 0):.1%}"
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
        top = vbs[0] if vbs else None
        stake_plan = analysis.get("stake_plan")
        lines.append(
            f"🎚️ Stake guía: <b>{_stake_label(top, c1x2.get('confidence', 0), stake_plan)}</b>"
        )

    lines.append("\n⚠️ <i>Lectura estadística y de mercado. No constituye consejo financiero.</i>")
    return "\n".join(lines)


def format_prime_board(
    leaders: list,
    mixes: list | None = None,
    all_count: int = 0,
    value_count: int = 0,
    title: str = "🏆 ValueX Prime del día",
    run_label: str = "",
) -> str:
    lines = [f"<b>{title}</b>", f"{'─' * 32}"]
    if run_label:
        lines.append(run_label)
    lines.append(
        f"Partidos analizados: {all_count} | Señales EV+: {value_count} | Prime Picks: {len(leaders or [])}"
    )

    if not leaders:
        lines.append("\nNo hay Prime Picks disponibles todavía.")
        lines.append("⚠️ <i>Lectura estadística y de mercado. No constituye consejo financiero.</i>")
        return "\n".join(lines)

    lines.append("\n<b>🔥 Mesa Prime</b>")
    for leader in leaders[:5]:
        official = leader.get("official_pick") or (leader.get("value_bets") or [None])[0]
        stake = leader.get("stake_plan") or {}
        label = leader.get("leader_name") or f"ValueX Prime #{leader.get('leader_rank', '?')}"
        lines.append(
            f"\n🏆 <b>{label}</b> · {leader.get('home', '?')} vs {leader.get('away', '?')}"
        )
        if leader.get("league_display") or leader.get("league"):
            lines.append(f"  {leader.get('league_display') or leader.get('league')}")
        if official:
            metric_line = (
                f"edge +{official.get('value', 0):.1%}"
                if float(official.get("value") or 0) > 0
                else f"confianza {float(official.get('confidence') or 0):.0%}"
            )
            lines.append(
                f"  → Pick oficial: {_short_pick_line(official)} | {metric_line}"
            )
            lines.append(
                f"  → Stake guía: {_stake_label(official, official.get('confidence', 0), stake)}"
            )
        else:
            lines.append("  → Aún sin pick oficial liquidable")

    if mixes:
        lines.append("\n<b>⚙️ ValueX PowerMix</b>")
        for mix in mixes[:2]:
            legs_desc = " + ".join(
                f"{leg.get('market')} {leg.get('selection')}" for leg in mix.get("legs", [])
            )
            lines.append(
                f"  → <b>{mix.get('name')}</b>: {legs_desc}\n"
                f"     Factor {mix.get('combined_odds', 0):.2f} | Prob. modelo {mix.get('combined_probability', 0):.1%}"
            )

    lines.append(f"\n{'─' * 32}")
    lines.append("⚠️ <i>Los éxitos oficiales se medirán sobre ValueX Prime. No constituye consejo financiero.</i>")
    return "\n".join(lines)


def format_power_mix(mixes: list, title: str = "⚙️ ValueX PowerMix") -> str:
    lines = [f"<b>{title}</b>", f"{'─' * 32}"]
    if not mixes:
        lines.append("Aún no hay combinadas disponibles en este ciclo.")
        return "\n".join(lines)

    for mix in mixes[:3]:
        lines.append(f"\n<b>{mix.get('name', 'PowerMix')}</b>")
        for leg in mix.get("legs", []):
            lines.append(
                f"  → {leg.get('home', '?')} vs {leg.get('away', '?')} · "
                f"{leg.get('market', 'Pick')} {leg.get('selection', '?')} @ {leg.get('odds', 0):.2f}"
            )
        lines.append(
            f"  Factor: <b>{mix.get('combined_odds', 0):.2f}</b> | "
            f"Prob. modelo: <b>{mix.get('combined_probability', 0):.1%}</b> | "
            f"Riesgo: <b>{mix.get('risk_label', 'media')}</b>"
        )

    lines.append("\n⚠️ <i>Combinada orientativa. Mayor factor implica mayor varianza.</i>")
    return "\n".join(lines)


def format_daily_close(report: dict, leader_report: dict | None = None) -> str:
    leader_report = leader_report or {}
    lines = [
        "<b>📘 Cierre oficial del día</b>",
        f"{'─' * 32}",
        f"Fecha: {report.get('date', '—')}",
        f"Radar total: {report.get('won', 0)}✅ {report.get('lost', 0)}❌ {report.get('pending', 0)}⏳",
        f"Radar ROI: <b>{report.get('roi_pct', 0):+.1f}%</b> | P&L: <b>{report.get('pnl_units', 0):+.2f}u</b>",
    ]

    if leader_report:
        lines.append(
            f"ValueX Prime: {leader_report.get('won', 0)}✅ {leader_report.get('lost', 0)}❌ {leader_report.get('pending', 0)}⏳"
        )
        lines.append(
            f"Prime ROI: <b>{leader_report.get('roi_pct', 0):+.1f}%</b> | P&L: <b>{leader_report.get('pnl_units', 0):+.2f}u</b>"
        )

    top_hits = report.get("top_hits") or []
    top_misses = report.get("top_misses") or []
    if top_hits:
        best = top_hits[0]
        lines.append(
            f"\n🔥 Mejor acierto: <b>{best.get('home')} vs {best.get('away')}</b> · "
            f"{best.get('market')} {best.get('label')} ({best.get('pnl', 0):+.2f}u)"
        )
    if top_misses:
        worst = top_misses[0]
        lines.append(
            f"🧱 Mayor fallo: <b>{worst.get('home')} vs {worst.get('away')}</b> · "
            f"{worst.get('market')} {worst.get('label')} ({worst.get('pnl', 0):+.2f}u)"
        )

    by_market = leader_report.get("by_market") or report.get("by_market") or {}
    if by_market:
        top_market = sorted(by_market.items(), key=lambda item: item[1].get("pnl", 0), reverse=True)[0]
        lines.append(f"📊 Mercado líder: <b>{top_market[0]}</b> ({top_market[1].get('pnl', 0):+.2f}u)")

    lines.append("\n⚠️ <i>Métrica oficial en base flat 1u. No constituye consejo financiero.</i>")
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
        stake_plan = match.get("stake_plan")
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
            lines.append(
                f"  → Stake guía: {_stake_label(top, conf, stake_plan)}"
            )
        else:
            lines.append(f"  → Seguimiento abierto: convicción modelo {conf:.0%} · stake {_stake_label(top, conf, stake_plan)}")

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
