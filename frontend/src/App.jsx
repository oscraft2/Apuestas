import React, { useState, useEffect, useCallback } from "react";
import {
  TrendingUp, Target, Zap, BarChart2, Shield,
  Activity, RefreshCw, AlertTriangle, ChevronRight,
  Send, Globe, Award, BookOpen, Brain, Wallet, Settings,
} from "lucide-react";
import heroAnalytics from "./assets/hero-analytics.svg";
import trustFooter from "./assets/trust-footer.svg";

// En producción las rutas son relativas (mismo servidor).
// En desarrollo local apunta a localhost:8000.
const API_BASE = process.env.REACT_APP_API_URL || "";

// ── Helpers ──────────────────────────────────────────────────────────────────

function useFetch(url, deps = []) {
  const [data, setData]   = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}${url}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setData(await res.json());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [url]);

  useEffect(() => { load(); }, deps);
  return { data, loading, error, reload: load };
}

function pct(v, decimals = 1) {
  return `${(v * 100).toFixed(decimals)}%`;
}

function fmtDateTime(iso, options = true) {
  const withDate = typeof options === "boolean" ? options : options?.withDate ?? true;
  const timeZone = typeof options === "object" ? options?.timeZone : undefined;
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("es-CL", {
      day: withDate ? "2-digit" : undefined,
      month: withDate ? "short" : undefined,
      hour: "2-digit",
      minute: "2-digit",
      timeZone,
    });
  } catch {
    return iso;
  }
}

function fmtTimeOnly(iso, options = {}) {
  const timeZone = options?.timeZone;
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleTimeString("es-CL", {
      hour: "2-digit",
      minute: "2-digit",
      timeZone,
    });
  } catch {
    return iso;
  }
}

function fmtUtcDateTime(iso, withDate = true) {
  return fmtDateTime(iso, { withDate, timeZone: "UTC" });
}

function fmtUtcTime(iso) {
  return fmtTimeOnly(iso, { timeZone: "UTC" });
}

function fmtOdds(v) {
  const n = Number(v);
  return Number.isFinite(n) && n > 0 ? n.toFixed(2) : "—";
}

function sortByKickoff(items = []) {
  return [...items].sort((a, b) => {
    const ta = a?.time ? new Date(a.time).getTime() : Number.MAX_SAFE_INTEGER;
    const tb = b?.time ? new Date(b.time).getTime() : Number.MAX_SAFE_INTEGER;
    return ta - tb;
  });
}

function getTopBet(match) {
  return match?.value_bets?.[0] || null;
}

function getMatchDateKey(match) {
  if (!match?.time) return "sin-fecha";
  const dt = new Date(match.time);
  if (Number.isNaN(dt.getTime())) return "sin-fecha";
  return dt.toLocaleDateString("sv-SE");
}

function getMatchDateLabel(dateKey) {
  if (!dateKey || dateKey === "all") return "Todo el ciclo";
  if (dateKey === "sin-fecha") return "Sin horario";
  try {
    return new Date(`${dateKey}T12:00:00`).toLocaleDateString("es-CL", {
      weekday: "short",
      day: "2-digit",
      month: "short",
    });
  } catch {
    return dateKey;
  }
}

function getMatchMarkets(match) {
  const markets = new Set();
  if (match?.consensus_1x2?.probs) markets.add("1X2");
  if (match?.consensus_ou?.probs) markets.add("Totales 2.5");
  if (match?.poisson?.btts) markets.add("BTTS");
  (match?.value_bets || []).forEach((vb) => {
    if (vb?.market) markets.add(vb.market);
  });
  return [...markets];
}

function sortMatches(items = [], sortBy = "kickoff") {
  const list = [...items];
  list.sort((a, b) => {
    if (sortBy === "value") {
      return (b?.max_value || getTopBet(b)?.value || 0) - (a?.max_value || getTopBet(a)?.value || 0);
    }
    if (sortBy === "confidence") {
      return (b?.consensus_1x2?.confidence || 0) - (a?.consensus_1x2?.confidence || 0);
    }
    if (sortBy === "league") {
      return String(a?.league_display || a?.league || "").localeCompare(String(b?.league_display || b?.league || ""), "es");
    }
    const ta = a?.time ? new Date(a.time).getTime() : Number.MAX_SAFE_INTEGER;
    const tb = b?.time ? new Date(b.time).getTime() : Number.MAX_SAFE_INTEGER;
    return ta - tb;
  });
  return list;
}

function groupMatches(items = [], groupBy = "country") {
  const grouped = new Map();
  items.forEach((item) => {
    const key = groupBy === "league"
      ? `league:${item?.league_id || item?.league_display || item?.league || "general"}`
      : `country:${item?.country_code || item?.country_name || "general"}`;
    if (!grouped.has(key)) {
      grouped.set(key, {
        key,
        title: groupBy === "league"
          ? (item?.league_display || item?.league || "Cobertura general")
          : `${item?.flag || "⚽"} ${item?.country_name || "Cobertura general"}`,
        subtitle: groupBy === "league"
          ? (item?.country_name || "Cobertura general")
          : `${item?.league_display || item?.league || "Cobertura general"}`,
        items: [],
      });
    }
    grouped.get(key).items.push(item);
  });
  return [...grouped.values()];
}

const EMPTY_BENCHMARK_FORM = {
  source: "",
  leagueId: "",
  league: "",
  home: "",
  away: "",
  market: "",
  selection: "",
  odds: "",
  kickoffUtc: "",
  note: "",
};

async function parseJsonResponse(res) {
  const json = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(typeof json.detail === "string" ? json.detail : JSON.stringify(json.detail || json));
  }
  return json;
}

function ValueBadge({ value }) {
  const p = (value * 100).toFixed(1);
  const cls = value >= 0.07 ? "bg-green-500" : value >= 0.04 ? "bg-yellow-500" : "bg-blue-500";
  return <span className={`${cls} text-white text-xs font-bold px-2 py-0.5 rounded-full`}>+{p}%</span>;
}

function Spinner() {
  return (
    <div className="flex items-center justify-center py-12">
      <RefreshCw size={24} className="text-blue-400 animate-spin" />
    </div>
  );
}

function ErrorBox({ msg, onRetry }) {
  return (
    <div className="bg-red-900/30 border border-red-700/40 rounded-xl p-4 text-center">
      <AlertTriangle size={20} className="text-red-400 mx-auto mb-2" />
      <p className="text-red-300 text-sm">{msg}</p>
      {onRetry && (
        <button onClick={onRetry} className="mt-2 text-xs text-blue-400 underline">
          Reintentar
        </button>
      )}
    </div>
  );
}

// ── Stat card ────────────────────────────────────────────────────────────────

function StatCard({ icon: Icon, label, value, sub, color, loading }) {
  return (
    <div className="bg-gray-800 rounded-xl p-4 flex items-center gap-4 border border-gray-700">
      <div className={`p-3 rounded-lg ${color}`}>
        <Icon size={20} className="text-white" />
      </div>
      <div>
        <p className="text-gray-400 text-xs">{label}</p>
        {loading
          ? <div className="h-6 w-16 bg-gray-700 animate-pulse rounded mt-1" />
          : <p className="text-white text-xl font-bold">{value}</p>}
        {sub && !loading && <p className="text-gray-500 text-xs">{sub}</p>}
      </div>
    </div>
  );
}

// ── Weekly chart ─────────────────────────────────────────────────────────────

function WeeklyChart({ monthly }) {
  if (!monthly) return null;
  const entries = Object.entries(monthly).slice(-8);
  if (!entries.length) return <p className="text-gray-500 text-xs text-center py-4">Sin datos mensuales aún.</p>;
  const max = Math.max(...entries.map(([, d]) => Math.abs(d.pnl)), 0.1);
  return (
    <div>
      <div className="flex items-end gap-1 h-14">
        {entries.map(([month, d]) => {
          const h = Math.round((Math.abs(d.pnl) / max) * 48) + 4;
          return (
            <div key={month} className="flex-1 flex flex-col items-center gap-0.5">
              <div
                className={`w-full rounded-sm ${d.pnl >= 0 ? "bg-green-500" : "bg-red-500"}`}
                style={{ height: h }}
                title={`${month}: ${d.pnl >= 0 ? "+" : ""}${d.pnl}u`}
              />
            </div>
          );
        })}
      </div>
      <div className="flex justify-between text-xs text-gray-500 mt-1">
        {entries.map(([m]) => <span key={m}>{m.slice(5)}</span>)}
      </div>
    </div>
  );
}

function SectionTitle({ eyebrow, title, subtitle, action }) {
  return (
    <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
      <div>
        {eyebrow && <p className="text-blue-400 text-xs font-semibold tracking-[0.18em] uppercase">{eyebrow}</p>}
        <h2 className="text-white text-2xl font-bold mt-1">{title}</h2>
        {subtitle && <p className="text-gray-400 text-sm mt-1 max-w-3xl">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

function QuickInsight({ label, value, hint }) {
  return (
    <div className="rounded-2xl border border-gray-700 bg-gray-800/80 p-4">
      <p className="text-gray-500 text-[11px] uppercase tracking-[0.18em]">{label}</p>
      <p className="text-white text-xl font-bold mt-1">{value}</p>
      {hint && <p className="text-gray-400 text-xs mt-1">{hint}</p>}
    </div>
  );
}

function RadarMatchCard({ match, compact = false }) {
  const top = getTopBet(match);
  const c1 = match?.consensus_1x2?.probs || {};
  const confidence = match?.consensus_1x2?.confidence || 0;
  const agreement = match?.consensus_1x2?.agreement || 0;

  return (
    <div className={`rounded-2xl border border-gray-700 bg-gray-800/85 p-4 ${compact ? "" : "h-full"}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-blue-400 text-xs font-semibold">{match?.league_display || match?.league || "Partido"}</p>
          <h3 className="text-white font-semibold text-lg leading-tight mt-1">
            {match?.home} <span className="text-gray-500">vs</span> {match?.away}
          </h3>
          <p className="text-gray-500 text-xs mt-1">
            {match?.country_name ? `${match.flag || "⚽"} ${match.country_name} · ` : ""}
            {fmtDateTime(match?.time)}
          </p>
        </div>
        {top ? <ValueBadge value={top.value} /> : <span className="text-xs text-blue-300 bg-blue-900/30 px-2 py-1 rounded-full">Radar activo</span>}
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <div className="rounded-xl bg-gray-900/70 p-3">
          <p className="text-gray-500 text-xs">Confianza</p>
          <p className="text-green-400 font-bold text-lg">{pct(confidence)}</p>
        </div>
        <div className="rounded-xl bg-gray-900/70 p-3">
          <p className="text-gray-500 text-xs">Acuerdo modelos</p>
          <p className="text-blue-400 font-bold text-lg">{pct(agreement)}</p>
        </div>
      </div>

      <div className="mt-4 flex gap-0.5 h-2 rounded-full overflow-hidden bg-gray-900">
        <div className="bg-blue-500" style={{ width: pct(c1.home || 0) }} />
        <div className="bg-gray-500" style={{ width: pct(c1.draw || 0) }} />
        <div className="bg-red-500" style={{ width: pct(c1.away || 0) }} />
      </div>
      <div className="mt-2 flex justify-between text-[11px] text-gray-400">
        <span>1 {pct(c1.home || 0)}</span>
        <span>X {pct(c1.draw || 0)}</span>
        <span>2 {pct(c1.away || 0)}</span>
      </div>

      <div className="mt-4 rounded-xl border border-blue-900/30 bg-blue-950/20 p-3">
        {top ? (
          <>
            <p className="text-blue-300 text-xs font-semibold">Señal principal</p>
            <p className="text-white font-semibold mt-1">{top.market} · {top.label || top.outcome}</p>
            <p className="text-gray-300 text-sm mt-1">
              Cuota {fmtOdds(top.odds || top.best_odds)} · Kelly {pct(top.kelly || 0)}
            </p>
          </>
        ) : (
          <>
            <p className="text-blue-300 text-xs font-semibold">Seguimiento del radar</p>
            <p className="text-white font-semibold mt-1">Lectura fuerte del modelo, aún sin ventaja de cuota dominante</p>
            <p className="text-gray-300 text-sm mt-1">
              Ideal para seguir movimiento de mercado y reevaluar en la próxima ventana automática.
            </p>
          </>
        )}
      </div>
    </div>
  );
}

function LeagueCoverageCard({ league, isHero }) {
  const gradeColor = {
    A: "text-green-400 bg-green-900/30",
    B: "text-yellow-400 bg-yellow-900/30",
    C: "text-orange-400 bg-orange-900/30",
    D: "text-red-400 bg-red-900/30",
    "N/A": "text-gray-400 bg-gray-700/50",
  }[league?.grade || "N/A"] || "text-gray-400 bg-gray-700/50";

  return (
    <div className={`rounded-2xl border p-4 ${isHero ? "border-blue-500/60 bg-blue-950/20" : "border-gray-700 bg-gray-800/85"}`}>
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-white font-semibold">{league?.display_full || league?.name}</p>
          <p className="text-gray-500 text-xs mt-1">{league?.country_name || "Cobertura general"} · {league?.sport_key || "Sin sport_key visible"}</p>
        </div>
        <span className={`px-2.5 py-1 rounded-full text-xs font-semibold ${gradeColor}`}>
          {league?.grade || "N/A"}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-3 mt-4 text-sm">
        <div>
          <p className="text-gray-500 text-xs">ROI histórico</p>
          <p className="text-white font-semibold">{league?.roi != null ? `${league.roi >= 0 ? "+" : ""}${league.roi}%` : "—"}</p>
        </div>
        <div>
          <p className="text-gray-500 text-xs">Penalización</p>
          <p className="text-white font-semibold">×{league?.penalty_factor ?? 1}</p>
        </div>
      </div>
      {isHero && (
        <p className="text-blue-300 text-xs mt-3">
          Liga priorizada en el radar editorial y en la jerarquía visual del producto.
        </p>
      )}
    </div>
  );
}

function RecentSignalRow({ pred }) {
  const top = pred?.value_bets?.[0];
  return (
    <div className="flex items-center justify-between gap-4 rounded-2xl border border-gray-700 bg-gray-800/80 p-4">
      <div>
        <p className="text-white font-medium">{pred?.home} <span className="text-gray-500">vs</span> {pred?.away}</p>
        <p className="text-gray-500 text-xs mt-1">{pred?.league || "Cobertura general"} · {pred?.date || "—"}</p>
      </div>
      <div className="text-right">
        <p className="text-gray-400 text-xs">{top ? `${top.market} · ${top.label || top.outcome}` : "Sin señal"}</p>
        <p className="text-white font-semibold mt-1">
          {top ? `@ ${fmtOdds(top.odds || top.best_odds)}` : "—"}
        </p>
      </div>
    </div>
  );
}

function AdminHighlightMini({ item }) {
  const top = item?.top_bet;
  return (
    <div className="rounded-2xl border border-gray-700 bg-gray-800/80 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-blue-400 text-xs font-semibold">{item?.league_display || item?.league || "Análisis"}</p>
          <p className="text-white font-semibold mt-1">{item?.home} <span className="text-gray-500">vs</span> {item?.away}</p>
          <p className="text-gray-500 text-xs mt-1">{item?.country_name ? `${item.flag || "⚽"} ${item.country_name} · ` : ""}{fmtDateTime(item?.time)}</p>
        </div>
        {top ? <ValueBadge value={item?.max_value || top?.value || 0} /> : <span className="text-xs text-gray-400">Radar</span>}
      </div>
      <div className="grid grid-cols-2 gap-2 mt-3 text-xs">
        <div className="rounded-xl bg-gray-900/70 p-3">
          <p className="text-gray-500">Confianza</p>
          <p className="text-green-400 font-semibold mt-1">{pct(item?.confidence || 0)}</p>
        </div>
        <div className="rounded-xl bg-gray-900/70 p-3">
          <p className="text-gray-500">Acuerdo</p>
          <p className="text-blue-400 font-semibold mt-1">{pct(item?.agreement || 0)}</p>
        </div>
      </div>
      <div className="mt-3">
        {top ? (
          <>
            <p className="text-gray-400 text-xs">{top?.market} · {top?.label || top?.outcome}</p>
            <p className="text-white text-sm font-medium mt-1">@ {fmtOdds(top?.odds || top?.best_odds)} · Kelly {pct(top?.kelly || 0)}</p>
          </>
        ) : (
          <p className="text-gray-500 text-xs">Sin EV+ principal, pero sigue en seguimiento del radar.</p>
        )}
      </div>
    </div>
  );
}

function TabHome() {
  const liveReq = useFetch("/api/analysis/live", []);
  const leaguesReq = useFetch("/api/leagues", []);
  const statsReq = useFetch("/api/stats", []);
  const btReq = useFetch("/api/backtest", []);
  const recentReq = useFetch("/api/bets/recent?n=8", []);

  useEffect(() => {
    const id = setInterval(() => {
      liveReq.reload();
      leaguesReq.reload();
      statsReq.reload();
      btReq.reload();
      recentReq.reload();
    }, 5 * 60 * 1000);
    return () => clearInterval(id);
  }, []);

  if (liveReq.loading && !liveReq.data) return <Spinner />;
  if (liveReq.error && !liveReq.data) return <ErrorBox msg={liveReq.error} onRetry={liveReq.reload} />;

  const live = liveReq.data || {};
  const stats = statsReq.data || {};
  const bt = btReq.data || {};
  const leagues = leaguesReq.data || [];
  const recent = recentReq.data || [];
  const highlights = live.highlights || [];
  const featured = highlights.slice(0, 4);
  const upcoming = sortByKickoff(highlights).slice(0, 3);
  const heroLeague = live.hero_league_name || "Cobertura prioritaria";
  const avgConfidence = featured.length
    ? featured.reduce((acc, m) => acc + (m?.consensus_1x2?.confidence || 0), 0) / featured.length
    : 0;

  const refreshAll = () => {
    liveReq.reload();
    leaguesReq.reload();
    statsReq.reload();
    btReq.reload();
    recentReq.reload();
  };

  return (
    <div className="space-y-6">
      <div className="overflow-hidden rounded-[28px] border border-blue-700/30 bg-gradient-to-br from-slate-900 via-blue-950 to-indigo-950">
        <div className="grid lg:grid-cols-[1.1fr,0.9fr] gap-6 items-center p-6 lg:p-8">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-blue-500/30 bg-blue-950/30 px-3 py-1 text-xs text-blue-300">
              <Award size={14} />
              Desk de inteligencia futbolística premium
            </div>

            <h1 className="mt-4 text-3xl md:text-5xl font-bold leading-tight text-white">
              Tu mesa central para leer valor, mercado y narrativa en el fútbol del día.
            </h1>
            <p className="mt-4 text-sm md:text-base text-slate-300 max-w-2xl">
              ValueXPro concentra el análisis, ordena las ligas clave y convierte la jornada en una lectura clara:
              qué mirar, dónde está la señal y qué piezas merecen publicación inmediata.
            </p>

            <div className="mt-5 flex flex-wrap gap-2 text-xs">
              <span className="rounded-full bg-white/5 px-3 py-1 text-slate-300 border border-white/10">
                Próxima pasada: {fmtUtcDateTime(live.next_run_utc)}
              </span>
              <span className="rounded-full bg-white/5 px-3 py-1 text-slate-300 border border-white/10">
                Horarios UTC: {(live.report_hours_utc || []).join(", ") || "—"}
              </span>
              <span className="rounded-full bg-white/5 px-3 py-1 text-slate-300 border border-white/10">
                Liga protagonista: {live.hero_league_display || heroLeague}
              </span>
            </div>

            <div className="mt-6 grid sm:grid-cols-2 xl:grid-cols-4 gap-3">
              <QuickInsight
                label="Partidos monitorizados"
                value={live.count ?? 0}
                hint={`Ligas activas: ${(live.leagues_analyzed || []).length}`}
              />
              <QuickInsight
                label="Señales EV+"
                value={live.total_value_bets ?? 0}
                hint={`${live.highlight_count ?? 0} destacados priorizados`}
              />
              <QuickInsight
                label="ROI tracker"
                value={stats.total_bets ? `${stats.roi_pct >= 0 ? "+" : ""}${stats.roi_pct}%` : "—"}
                hint={`${stats.total_bets || 0} apuestas históricas`}
              />
              <QuickInsight
                label="Pasadas hoy"
                value={live.runs_today ?? 0}
                hint={`Última: ${fmtUtcTime(live.last_run)} UTC`}
              />
            </div>
          </div>

          <div className="relative">
            <img
              src={heroAnalytics}
              alt="Ilustración original de control de análisis futbolístico"
              className="w-full rounded-3xl border border-white/10 shadow-2xl"
            />
          </div>
        </div>
      </div>

      <SectionTitle
        eyebrow="Radar del día"
        title="Lo más importante del ciclo actual"
        subtitle="Selección priorizada por edge, confianza del consenso y jerarquía editorial. Es la lectura rápida para decidir qué revisar primero."
        action={(
          <button onClick={refreshAll} className="inline-flex items-center gap-2 text-sm text-blue-300 hover:text-white">
            <RefreshCw size={14} /> Actualizar
          </button>
        )}
      />

      {featured.length === 0 ? (
        <div className="rounded-2xl border border-gray-700 bg-gray-800 p-6 text-center">
          <p className="text-gray-300 font-semibold">Aún no hay destacados en caché.</p>
          <p className="text-gray-500 text-sm mt-1">
            La portada se poblará automáticamente tras la próxima pasada central del motor.
          </p>
        </div>
      ) : (
        <div className="grid xl:grid-cols-2 gap-4">
          {featured.map((match, idx) => (
            <RadarMatchCard key={`${match.match_id || idx}-${idx}`} match={match} />
          ))}
        </div>
      )}

      <div className="grid xl:grid-cols-[1.05fr,0.95fr] gap-4">
        <div className="rounded-2xl border border-gray-700 bg-gray-800/85 p-5">
          <SectionTitle
            eyebrow="Briefing"
            title="Briefing ejecutivo de jornada"
            subtitle="Resumen profesional para detectar dónde está la conversación real del día."
          />
          <div className="grid md:grid-cols-2 gap-3 mt-5">
            <QuickInsight
              label="Confianza media destacados"
              value={featured.length ? pct(avgConfidence) : "—"}
              hint="Media de los encuentros más relevantes del ciclo actual."
            />
            <QuickInsight
              label="ROI flat backtest"
              value={bt.roi_flat != null ? `${bt.roi_flat >= 0 ? "+" : ""}${bt.roi_flat}%` : "—"}
              hint={bt.sharpe != null ? `Sharpe ${bt.sharpe}` : "Backtest histórico disponible"}
            />
            <QuickInsight
              label="P&L acumulado"
              value={stats.pnl_units != null ? `${stats.pnl_units >= 0 ? "+" : ""}${stats.pnl_units}u` : "—"}
              hint={`${stats.won || 0} ganadas · ${stats.lost || 0} perdidas`}
            />
            <QuickInsight
              label="Cobertura activa"
              value={`${(live.leagues_analyzed || []).length} ligas`}
              hint={(live.leagues_analyzed || []).slice(0, 3).join(" · ") || "Esperando análisis"}
            />
          </div>

          <div className="mt-5 rounded-2xl border border-gray-700 bg-gray-900/60 p-4">
            <p className="text-white font-semibold">Agenda prioritaria del fútbol de hoy</p>
            <div className="space-y-3 mt-4">
              {upcoming.length ? upcoming.map((match, idx) => (
                <div key={`${match.match_id || idx}-agenda`} className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-white text-sm font-medium">{match.home} <span className="text-gray-500">vs</span> {match.away}</p>
                    <p className="text-gray-500 text-xs">{match.league} · {fmtDateTime(match.time)}</p>
                  </div>
                  <div className="text-right">
                    {match.value_bets?.[0]
                      ? <ValueBadge value={match.value_bets[0].value} />
                      : <span className="text-xs text-blue-300 bg-blue-950/40 px-2 py-1 rounded-full">Seguimiento</span>}
                  </div>
                </div>
              )) : (
                <p className="text-gray-500 text-sm">Sin agenda prioritaria todavía.</p>
              )}
            </div>
          </div>
        </div>

        <div className="rounded-2xl border border-gray-700 bg-gray-800/85 p-5">
          <SectionTitle
            eyebrow="Cobertura"
            title="Ligas y calidad de señal"
            subtitle="Panorama de competiciones activas, calibración disponible y prioridad táctica."
          />
          <div className="grid sm:grid-cols-2 gap-3 mt-5">
            {leagues.length ? leagues.map((league) => (
              <LeagueCoverageCard
                key={league.id}
                league={league}
                isHero={league.id === live.hero_league_id}
              />
            )) : (
              <div className="col-span-full rounded-2xl border border-gray-700 bg-gray-900/60 p-4">
                <p className="text-gray-500 text-sm">La lista de ligas aparecerá cuando la API cargue su configuración activa.</p>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="grid xl:grid-cols-[1fr,1fr] gap-4">
        <div className="rounded-2xl border border-gray-700 bg-gray-800/85 p-5">
          <SectionTitle
            eyebrow="Últimas señales"
            title="Rastro reciente del sistema"
            subtitle="Una muestra del histórico reciente para entender continuidad, ritmo y disciplina de publicación."
          />
          <div className="space-y-3 mt-5">
            {recent.length ? recent.slice().reverse().slice(0, 5).map((pred, idx) => (
              <RecentSignalRow key={`${pred.match_id || idx}-${idx}`} pred={pred} />
            )) : (
              <p className="text-gray-500 text-sm">Aún no hay señales recientes guardadas.</p>
            )}
          </div>
        </div>

        <div className="rounded-2xl border border-gray-700 bg-gradient-to-br from-gray-800 to-gray-900 p-5">
          <SectionTitle
            eyebrow="Contexto"
            title="Marco de lectura y cobertura"
            subtitle="La portada no solo muestra picks: explica foco, cobertura, método y ritmo del motor."
          />
          <div className="grid sm:grid-cols-2 gap-3 mt-5">
            <div className="rounded-2xl border border-gray-700 bg-gray-900/70 p-4">
              <p className="text-white font-semibold">Cobertura principal</p>
              <p className="text-gray-400 text-sm mt-2">
                El sistema arranca con foco fuerte en Chile y LATAM, manteniendo Brasil, Liga MX, MLS, Argentina,
                Colombia, Perú y Ecuador como mesa principal de lectura.
              </p>
            </div>
            <div className="rounded-2xl border border-gray-700 bg-gray-900/70 p-4">
              <p className="text-white font-semibold">Mercados y lectura</p>
              <p className="text-gray-400 text-sm mt-2">
                El motor opera sobre 1X2 y O/U 2.5 con consenso, cuotas justas, edge estimado y control de calidad.
              </p>
            </div>
            <div className="rounded-2xl border border-gray-700 bg-gray-900/70 p-4">
              <p className="text-white font-semibold">Arquitectura central</p>
              <p className="text-gray-400 text-sm mt-2">
                El análisis se ejecuta en ventanas fijas para reducir carga, mantener coherencia y evitar recalcular por cada usuario.
              </p>
            </div>
            <div className="rounded-2xl border border-gray-700 bg-gray-900/70 p-4">
              <p className="text-white font-semibold">Uso responsable</p>
              <p className="text-gray-400 text-sm mt-2">
                Las señales son estadísticas y deben usarse como soporte de lectura, no como promesa de rendimiento.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ProfessionalFooter({ live, onOpenAdmin }) {
  return (
    <footer className="mt-8 rounded-[28px] border border-gray-700 bg-gray-900/90 overflow-hidden">
      <div className="grid xl:grid-cols-[1.1fr,0.9fr] gap-0">
        <div className="p-6 lg:p-8">
          <p className="text-blue-400 text-xs font-semibold tracking-[0.18em] uppercase">Infraestructura, confianza y operadores</p>
          <h3 className="text-white text-2xl font-bold mt-2">Base operativa pensada para lectura premium, control privado y publicaciones ordenadas.</h3>
          <p className="text-gray-400 text-sm mt-3 max-w-2xl">
            La parte pública prioriza análisis, mercados y jerarquía visual. El acceso de operadores vive aquí abajo,
            fuera de la navegación principal, con sesión segura y lógica sensible concentrada en backend.
          </p>

          <div className="grid md:grid-cols-3 gap-3 mt-6">
            <div className="rounded-2xl border border-gray-700 bg-gray-800/85 p-4">
              <p className="text-white font-semibold">Protección de datos</p>
              <p className="text-gray-400 text-sm mt-2">
                Las claves privadas ya no se mueven como token manual en el navegador. El control se hace con sesión segura.
              </p>
            </div>
            <div className="rounded-2xl border border-gray-700 bg-gray-800/85 p-4">
              <p className="text-white font-semibold">Fuentes operativas</p>
              <p className="text-gray-400 text-sm mt-2">
                Mercado, datos futbolísticos y modelos de consenso trabajan desde el backend para reducir exposición y ruido.
              </p>
            </div>
            <div className="rounded-2xl border border-gray-700 bg-gray-800/85 p-4">
              <p className="text-white font-semibold">Ventanas automáticas</p>
              <p className="text-gray-400 text-sm mt-2">
                Horarios UTC: {(live?.report_hours_utc || []).join(", ") || "—"} · próxima pasada {fmtUtcDateTime(live?.next_run_utc)}.
              </p>
            </div>
          </div>

          <div className="mt-6 rounded-2xl border border-blue-700/40 bg-blue-950/20 p-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="text-white font-semibold">Acceso de operadores</p>
              <p className="text-gray-400 text-sm mt-1">
                Consola privada para publicar en el canal, revisar benchmark, ejecutar análisis y gestionar usuarios premium.
              </p>
            </div>
            <button
              type="button"
              onClick={onOpenAdmin}
              className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-3 rounded-xl text-sm font-semibold"
            >
              Abrir consola privada
            </button>
          </div>

          <div className="mt-6 flex flex-wrap gap-2 text-xs text-gray-400">
            <span className="rounded-full border border-gray-700 px-3 py-1 bg-gray-800/80">Backend protegido</span>
            <span className="rounded-full border border-gray-700 px-3 py-1 bg-gray-800/80">Sesión segura de operadores</span>
            <span className="rounded-full border border-gray-700 px-3 py-1 bg-gray-800/80">Análisis centralizado</span>
            <span className="rounded-full border border-gray-700 px-3 py-1 bg-gray-800/80">Radar editorial de mercado</span>
          </div>
        </div>

        <div className="bg-gradient-to-br from-blue-950/50 to-slate-950 p-6 lg:p-8 flex flex-col justify-between">
          <img
            src={trustFooter}
            alt="Visual original de protección de datos y confiabilidad del sistema"
            className="w-full rounded-3xl border border-white/10"
          />
          <div className="mt-5">
            <p className="text-white font-semibold">ValueXPro Intelligence Suite</p>
            <p className="text-gray-400 text-sm mt-2">
              Plataforma de inteligencia futbolística para analizar, ordenar, publicar y auditar decisiones con una lectura mucho más clara.
            </p>
            <p className="text-gray-500 text-xs mt-4">
              Las predicciones y rankings son informativos. No constituyen asesoría financiera ni garantizan resultados futuros.
            </p>
          </div>
        </div>
      </div>
    </footer>
  );
}

// ── Tab: Hoy ─────────────────────────────────────────────────────────────────

function BetCard({ bet, onSelect }) {
  const top = getTopBet(bet);
  const c1 = bet.consensus_1x2?.probs || {};
  const availableMarkets = getMatchMarkets(bet);

  return (
    <div
      className="bg-gray-800 border border-gray-700 rounded-2xl p-4 cursor-pointer hover:border-blue-500 transition-all"
      onClick={() => onSelect(bet)}
    >
      <div className="flex justify-between items-start mb-2">
        <div>
          <p className="text-xs text-gray-400">
            {bet.league_display || bet.league || "Cobertura general"}
            {bet.country_name ? ` · ${bet.flag || "⚽"} ${bet.country_name}` : ""}
          </p>
          <p className="text-white font-bold">{bet.home} <span className="text-gray-400">vs</span> {bet.away}</p>
          <p className="text-gray-500 text-xs mt-1">{fmtDateTime(bet.time)}</p>
        </div>
        <div className="text-right">
          <p className="text-xs text-gray-400">Confianza</p>
          <p className="text-green-400 font-bold">{pct(bet.consensus_1x2?.confidence || 0)}</p>
        </div>
      </div>

      {/* Barra 1X2 */}
      {c1.home != null && (
        <>
          <div className="flex gap-0.5 h-2 rounded-full overflow-hidden my-2">
            <div className="bg-blue-500 rounded-l-full" style={{ width: pct(c1.home) }} />
            <div className="bg-gray-500" style={{ width: pct(c1.draw || 0) }} />
            <div className="bg-red-500 rounded-r-full" style={{ width: pct(c1.away || 0) }} />
          </div>
          <div className="flex justify-between text-xs text-gray-400 mb-3">
            <span>🏠 {pct(c1.home)}</span>
            <span>🤝 {pct(c1.draw || 0)}</span>
            <span>✈️ {pct(c1.away || 0)}</span>
          </div>
        </>
      )}

      <div className="flex flex-wrap gap-1.5 my-3">
        {availableMarkets.slice(0, 4).map((market) => (
          <span key={market} className="rounded-full border border-gray-700 bg-gray-900/70 px-2.5 py-1 text-[11px] text-gray-300">
            {market}
          </span>
        ))}
      </div>

      <div className="border-t border-gray-700 pt-3 flex items-center justify-between">
        {top ? (
          <div>
            <p className="text-xs text-gray-400">Lectura líder</p>
            <p className="text-white font-semibold">{top.market} · {top.label || top.outcome}</p>
            <p className="text-gray-400 text-xs mt-1">@ {fmtOdds(top.odds || top.best_odds)}</p>
          </div>
        ) : (
          <div>
            <p className="text-xs text-gray-400">Seguimiento activo</p>
            <p className="text-white font-semibold">Sin EV+ principal, pero con lectura abierta</p>
            <p className="text-gray-500 text-xs mt-1">Útil para revisar mercado y nuevas pasadas.</p>
          </div>
        )}
          <div className="flex items-center gap-2">
            {top ? <ValueBadge value={top.value} /> : <span className="text-xs text-blue-300 bg-blue-900/30 px-2 py-1 rounded-full">Monitor</span>}
            {top && bet.value_bets.length > 1 && (
              <span className="text-xs text-gray-500">+{bet.value_bets.length - 1}</span>
            )}
            <ChevronRight size={16} className="text-gray-500" />
          </div>
      </div>

      {bet.xgb_win_prob != null && (
        <p className="text-xs text-purple-400 mt-2">🤖 XGBoost win prob: {pct(bet.xgb_win_prob)}</p>
      )}
    </div>
  );
}

function BetDetail({ bet, onBack }) {
  const c1 = bet.consensus_1x2?.probs || {};
  const f1 = bet.consensus_1x2?.fair_odds || {};
  const cou = bet.consensus_ou?.probs || {};
  const poi = bet.poisson || {};

  return (
    <div className="space-y-4">
      <button onClick={onBack} className="text-blue-400 text-sm hover:text-blue-300">← Volver</button>

      <div className="bg-gray-800 rounded-xl p-5 border border-gray-700">
        <p className="text-xs text-gray-400">{bet.league_display || bet.league || "Cobertura general"}</p>
        <h2 className="text-xl font-bold text-white">{bet.home} vs {bet.away}</h2>
        <p className="text-gray-400 text-sm">
          {bet.country_name ? `${bet.flag || "⚽"} ${bet.country_name} · ` : ""}
          {fmtDateTime(bet.time)}
        </p>
      </div>

      {/* 1X2 */}
      {c1.home != null && (
        <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
          <h3 className="text-gray-300 font-semibold mb-3">📊 Resultado (1X2)</h3>
          <div className="grid grid-cols-3 gap-2 text-center">
            {[["🏠 " + bet.home, "home"], ["🤝 Empate", "draw"], ["✈️ " + bet.away, "away"]].map(([label, k]) => (
              <div key={k} className="bg-gray-700 rounded-lg p-3">
                <p className="text-xs text-gray-400 truncate">{label}</p>
                <p className="text-white text-lg font-bold">{pct(c1[k] || 0)}</p>
                <p className="text-gray-500 text-xs">cuota justa: {f1[k] || "—"}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* O/U */}
      {cou.over != null && (
        <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
          <h3 className="text-gray-300 font-semibold mb-3">⚽ Goles O/U 2.5</h3>
          <div className="flex gap-3">
            <div className="flex-1 bg-gray-700 rounded-lg p-3 text-center">
              <p className="text-xs text-gray-400">⬆️ Over</p>
              <p className="text-white text-lg font-bold">{pct(cou.over)}</p>
            </div>
            <div className="flex-1 bg-gray-700 rounded-lg p-3 text-center">
              <p className="text-xs text-gray-400">⬇️ Under</p>
              <p className="text-white text-lg font-bold">{pct(cou.under || 0)}</p>
            </div>
          </div>
          {poi.top_score && (
            <p className="text-xs text-gray-500 mt-2">
              🎯 Score probable: <strong className="text-white">{poi.top_score}</strong>
              {" · "}xG: {poi.xg_home} – {poi.xg_away}
            </p>
          )}
        </div>
      )}

      {/* Value bets */}
      {bet.value_bets?.length > 0 && (
        <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
          <h3 className="text-gray-300 font-semibold mb-3">🔥 Señales con ventaja</h3>
          <div className="space-y-2">
            {bet.value_bets.map((vb, i) => (
              <div key={i} className="bg-gray-700 rounded-lg p-3 flex justify-between items-center">
                <div>
                  <p className="text-xs text-gray-400">{vb.market}</p>
                  <p className="text-white font-semibold">{vb.label || vb.outcome}</p>
                  <p className="text-gray-400 text-xs">@ {vb.odds || vb.best_odds}</p>
                </div>
                <div className="text-right">
                  <ValueBadge value={vb.value} />
                  <p className="text-xs text-gray-500 mt-1">Kelly {pct(vb.kelly)}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* AI */}
      {bet.ai?.reasoning && (
        <div className="bg-blue-900/20 border border-blue-700/30 rounded-xl p-4">
          <p className="text-xs text-blue-400 mb-1">🧠 DeepSeek IA</p>
          <p className="text-gray-300 text-sm italic">{bet.ai.reasoning}</p>
          {bet.ai.key_factors?.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {bet.ai.key_factors.map((f, i) => (
                <span key={i} className="text-xs bg-blue-900/40 text-blue-300 px-2 py-0.5 rounded-full">{f}</span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* XGBoost */}
      {bet.xgb_win_prob != null && (
        <div className="bg-purple-900/20 border border-purple-700/30 rounded-xl p-4">
          <p className="text-xs text-purple-400 mb-1">🤖 XGBoost ML</p>
          <p className="text-gray-300 text-sm">Probabilidad de ganar: <strong className="text-white">{pct(bet.xgb_win_prob)}</strong></p>
        </div>
      )}

      <div className="bg-gray-800 rounded-xl p-3 border border-gray-700 flex justify-around text-center">
        <div>
          <p className="text-xs text-gray-400">Confianza</p>
          <p className="text-green-400 font-bold">{pct(bet.consensus_1x2?.confidence || 0)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-400">Acuerdo</p>
          <p className="text-blue-400 font-bold">{pct(bet.consensus_1x2?.agreement || 0)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-400">Modelos</p>
          <p className="text-yellow-400 font-bold">{bet.consensus_1x2?.models_used?.length || 0}</p>
        </div>
      </div>

      <p className="text-center text-gray-500 text-xs pb-2">
        Lectura estadística y de mercado. Úsala como apoyo de decisión, no como garantía de resultado.
      </p>
    </div>
  );
}

function TabToday() {
  const { data, loading, error, reload } = useFetch("/api/analysis/live", []);
  const [selected, setSelected] = useState(null);
  const [viewMode, setViewMode] = useState("all");
  const [groupBy, setGroupBy] = useState("country");
  const [dateFilter, setDateFilter] = useState("all");
  const [countryFilter, setCountryFilter] = useState("all");
  const [leagueFilter, setLeagueFilter] = useState("all");
  const [marketFilter, setMarketFilter] = useState("all");
  const [sortBy, setSortBy] = useState("kickoff");
  const [query, setQuery] = useState("");

  // Auto-refresh cada 5 minutos
  useEffect(() => {
    const id = setInterval(reload, 5 * 60 * 1000);
    return () => clearInterval(id);
  }, [reload]);

  if (selected) return <BetDetail bet={selected} onBack={() => setSelected(null)} />;
  if (loading) return <Spinner />;
  if (error) return <ErrorBox msg={error} onRetry={reload} />;

  const matches = data?.results || [];
  const valueMatches = matches.filter((match) => match.value_bets?.length > 0);
  const todayKey = new Date().toLocaleDateString("sv-SE");
  const availableDates = [...new Set(matches.map(getMatchDateKey))].sort();
  const availableCountries = Array.from(
    new Map(
      matches.map((match) => [
        match.country_code || match.country_name || "general",
        {
          code: match.country_code || "general",
          label: `${match.flag || "⚽"} ${match.country_name || "Cobertura general"}`,
        },
      ])
    ).values()
  );
  const availableLeagues = Array.from(
    new Map(
      matches.map((match) => [
        match.league_id || match.league_display || match.league || "general",
        {
          key: match.league_id || match.league_display || match.league || "general",
          label: match.league_display || match.league || "Cobertura general",
        },
      ])
    ).values()
  );
  const availableMarkets = [...new Set(matches.flatMap(getMatchMarkets))].sort((a, b) => a.localeCompare(b, "es"));

  const filtered = matches.filter((match) => {
    const top = getTopBet(match);
    const haystack = `${match.home || ""} ${match.away || ""} ${match.league_display || match.league || ""} ${match.country_name || ""}`.toLowerCase();
    if (viewMode === "value" && !top) return false;
    if (dateFilter !== "all" && getMatchDateKey(match) !== dateFilter) return false;
    if (countryFilter !== "all" && (match.country_code || "general") !== countryFilter) return false;
    if (leagueFilter !== "all" && String(match.league_id || match.league_display || match.league || "general") !== leagueFilter) return false;
    if (marketFilter !== "all" && !getMatchMarkets(match).includes(marketFilter)) return false;
    if (query.trim() && !haystack.includes(query.trim().toLowerCase())) return false;
    return true;
  });

  const marketSource = matches.filter((match) => {
    if (dateFilter !== "all") return getMatchDateKey(match) === dateFilter;
    return getMatchDateKey(match) === todayKey;
  });
  const marketHeat = Object.values(
    marketSource.reduce((acc, match) => {
      const top = getTopBet(match);
      getMatchMarkets(match).forEach((market) => {
        if (!acc[market]) acc[market] = { market, matches: 0, valueMatches: 0 };
        acc[market].matches += 1;
        if (top && (top.market === market || market === "1X2")) {
          acc[market].valueMatches += 1;
        }
      });
      return acc;
    }, {})
  ).sort((a, b) => b.matches - a.matches).slice(0, 6);

  const sortedMatches = sortMatches(filtered, sortBy);
  const grouped = groupMatches(sortedMatches, groupBy);
  const filteredValueCount = filtered.filter((match) => match.value_bets?.length > 0).length;
  const activeDateLabel = dateFilter === "all" ? "Todo el ciclo cargado" : getMatchDateLabel(dateFilter);

  return (
    <div className="space-y-5">
      <SectionTitle
        eyebrow="Explorador del ciclo"
        title="Partidos analizados, mercados vivos y foco operativo"
        subtitle="Navega todo el análisis cargado, no solo las señales EV+. Filtra por fecha, país, liga, mercado y prioriza lo que más te conviene revisar primero."
        action={(
          <button onClick={reload} className="inline-flex items-center gap-2 text-sm text-blue-300 hover:text-white">
            <RefreshCw size={14} /> Actualizar ciclo
          </button>
        )}
      />

      <div className="grid md:grid-cols-2 xl:grid-cols-4 gap-3">
        <QuickInsight
          label="Partidos cargados"
          value={matches.length}
          hint={`${filtered.length} visibles con filtros activos`}
        />
        <QuickInsight
          label="Señales EV+"
          value={valueMatches.length}
          hint={`${filteredValueCount} dentro de tu vista actual`}
        />
        <QuickInsight
          label="Fecha en foco"
          value={activeDateLabel}
          hint={`Última pasada ${fmtUtcTime(data?.last_run)} UTC`}
        />
        <QuickInsight
          label="Próxima ventana"
          value={fmtUtcTime(data?.next_run_utc)}
          hint={`Hero league: ${data?.hero_league_display || data?.hero_league_name || "—"}`}
        />
      </div>

      <div className="rounded-2xl border border-gray-700 bg-gray-800/85 p-5">
        <SectionTitle
          eyebrow="Mercados del día"
          title="Dónde se concentra la lectura de hoy"
          subtitle="Mapa rápido de mercados activos para detectar qué merece revisión inmediata en la jornada."
        />
        <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-3 mt-5">
          {marketHeat.length ? marketHeat.map((item) => (
            <div key={item.market} className="rounded-2xl border border-gray-700 bg-gray-900/70 p-4">
              <p className="text-blue-300 text-xs font-semibold uppercase tracking-[0.18em]">{item.market}</p>
              <p className="text-white text-2xl font-bold mt-2">{item.matches}</p>
              <p className="text-gray-400 text-sm mt-1">partidos con ese mercado visible</p>
              <p className="text-gray-500 text-xs mt-2">{item.valueMatches} con señal prioritaria o edge visible</p>
            </div>
          )) : (
            <div className="md:col-span-2 xl:col-span-3 rounded-2xl border border-gray-700 bg-gray-900/60 p-4">
              <p className="text-gray-400 text-sm">Todavía no hay mercados suficientes para destacar en la fecha seleccionada.</p>
            </div>
          )}
        </div>
      </div>

      <div className="rounded-2xl border border-gray-700 bg-gray-800/85 p-5">
        <SectionTitle
          eyebrow="Filtros"
          title="Construye tu lectura"
          subtitle="Alterna entre vista total o solo EV+, cambia el criterio de orden y separa el tablero por país o por liga."
        />
        <div className="grid lg:grid-cols-2 xl:grid-cols-4 gap-3 mt-5">
          <div>
            <label className="text-xs text-gray-400">Buscar partido</label>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Equipo, liga o país..."
              className="w-full mt-1 bg-gray-900 border border-gray-600 rounded-xl px-3 py-3 text-sm text-white"
            />
          </div>
          <div>
            <label className="text-xs text-gray-400">Fecha</label>
            <select
              value={dateFilter}
              onChange={(e) => setDateFilter(e.target.value)}
              className="w-full mt-1 bg-gray-900 border border-gray-600 rounded-xl px-3 py-3 text-sm text-white"
            >
              <option value="all">Todo el ciclo</option>
              {availableDates.map((dateKey) => (
                <option key={dateKey} value={dateKey}>{getMatchDateLabel(dateKey)}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-400">País</label>
            <select
              value={countryFilter}
              onChange={(e) => setCountryFilter(e.target.value)}
              className="w-full mt-1 bg-gray-900 border border-gray-600 rounded-xl px-3 py-3 text-sm text-white"
            >
              <option value="all">Todos los países</option>
              {availableCountries.map((country) => (
                <option key={country.code} value={country.code}>{country.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-400">Liga</label>
            <select
              value={leagueFilter}
              onChange={(e) => setLeagueFilter(e.target.value)}
              className="w-full mt-1 bg-gray-900 border border-gray-600 rounded-xl px-3 py-3 text-sm text-white"
            >
              <option value="all">Todas las ligas</option>
              {availableLeagues.map((league) => (
                <option key={league.key} value={String(league.key)}>{league.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-400">Mercado</label>
            <select
              value={marketFilter}
              onChange={(e) => setMarketFilter(e.target.value)}
              className="w-full mt-1 bg-gray-900 border border-gray-600 rounded-xl px-3 py-3 text-sm text-white"
            >
              <option value="all">Todos los mercados</option>
              {availableMarkets.map((market) => (
                <option key={market} value={market}>{market}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-400">Orden</label>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="w-full mt-1 bg-gray-900 border border-gray-600 rounded-xl px-3 py-3 text-sm text-white"
            >
              <option value="kickoff">Hora de inicio</option>
              <option value="value">Mayor valor</option>
              <option value="confidence">Mayor confianza</option>
              <option value="league">Liga</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-400">Vista</label>
            <div className="mt-1 grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setViewMode("all")}
                className={`rounded-xl px-3 py-3 text-sm ${viewMode === "all" ? "bg-blue-600 text-white" : "bg-gray-900 border border-gray-600 text-gray-300"}`}
              >
                Todos
              </button>
              <button
                type="button"
                onClick={() => setViewMode("value")}
                className={`rounded-xl px-3 py-3 text-sm ${viewMode === "value" ? "bg-blue-600 text-white" : "bg-gray-900 border border-gray-600 text-gray-300"}`}
              >
                Solo EV+
              </button>
            </div>
          </div>
          <div>
            <label className="text-xs text-gray-400">Agrupar por</label>
            <div className="mt-1 grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setGroupBy("country")}
                className={`rounded-xl px-3 py-3 text-sm ${groupBy === "country" ? "bg-gray-700 text-white" : "bg-gray-900 border border-gray-600 text-gray-300"}`}
              >
                País
              </button>
              <button
                type="button"
                onClick={() => setGroupBy("league")}
                className={`rounded-xl px-3 py-3 text-sm ${groupBy === "league" ? "bg-gray-700 text-white" : "bg-gray-900 border border-gray-600 text-gray-300"}`}
              >
                Liga
              </button>
            </div>
          </div>
        </div>
      </div>

      {grouped.length === 0 ? (
        <div className="bg-gray-800 rounded-2xl p-6 text-center border border-gray-700">
          <p className="text-gray-300 font-semibold">No hay partidos que coincidan con tu filtro.</p>
          <p className="text-gray-500 text-sm mt-1">Ajusta fecha, mercado o modo de vista para reabrir el radar.</p>
        </div>
      ) : (
        <div className="space-y-5">
          {grouped.map((section) => (
            <div key={section.key} className="rounded-2xl border border-gray-700 bg-gray-800/85 p-5">
              <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
                <div>
                  <p className="text-white text-lg font-semibold">{section.title}</p>
                  <p className="text-gray-500 text-xs mt-1">{section.items.length} partidos · {section.subtitle}</p>
                </div>
                <p className="text-xs text-gray-500">
                  {section.items.filter((match) => match.value_bets?.length > 0).length} con edge visible
                </p>
              </div>
              <div className="grid xl:grid-cols-2 gap-3 mt-4">
                {section.items.map((match, idx) => (
                  <BetCard key={`${section.key}-${match.match_id || idx}-${idx}`} bet={match} onSelect={setSelected} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Tab: Historial ────────────────────────────────────────────────────────────

function TabHistory() {
  const { data: stats, loading: ls } = useFetch("/api/stats", []);
  const { data: recent, loading: lr } = useFetch("/api/bets/recent?n=30", []);
  const { data: bt } = useFetch("/api/backtest", []);

  const pnlColor = (v) => v >= 0 ? "text-green-400" : "text-red-400";

  return (
    <div className="space-y-4">
      {/* KPIs */}
      <div className="grid grid-cols-3 gap-2">
        {[
          ["Tasa de acierto", ls ? "—" : `${((stats?.hit_rate || 0) * 100).toFixed(0)}%`],
          ["ROI", ls ? "—" : `${stats?.roi_pct >= 0 ? "+" : ""}${stats?.roi_pct || 0}%`],
          ["P&L", ls ? "—" : `${stats?.pnl_units >= 0 ? "+" : ""}${stats?.pnl_units || 0}u`],
        ].map(([label, val]) => (
          <div key={label} className="bg-gray-800 rounded-lg p-3 text-center border border-gray-700">
            <p className="text-xs text-gray-400">{label}</p>
            <p className={`font-bold text-lg ${val.startsWith("+") || val.startsWith("5") || val.startsWith("6") || val.startsWith("7") || val.startsWith("8") ? "text-green-400" : val.startsWith("-") ? "text-red-400" : "text-white"}`}>{val}</p>
          </div>
        ))}
      </div>

      {/* Backtest extra si disponible */}
      {bt && (
        <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
          <p className="text-gray-300 font-semibold text-sm mb-2">📊 Backtesting histórico</p>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <p className="text-gray-400 text-xs">Sharpe ratio</p>
              <p className="text-white font-bold">{bt.sharpe ?? "—"}</p>
            </div>
            <div>
              <p className="text-gray-400 text-xs">Max drawdown</p>
              <p className="text-red-400 font-bold">{bt.max_drawdown != null ? `-${bt.max_drawdown}u` : "—"}</p>
            </div>
            <div>
              <p className="text-gray-400 text-xs">ROI flat</p>
              <p className={`font-bold ${pnlColor(bt.roi_flat)}`}>{bt.roi_flat != null ? `${bt.roi_flat >= 0 ? "+" : ""}${bt.roi_flat}%` : "—"}</p>
            </div>
            <div>
              <p className="text-gray-400 text-xs">ROI Kelly</p>
              <p className={`font-bold ${pnlColor(bt.roi_kelly)}`}>{bt.roi_kelly != null ? `${bt.roi_kelly >= 0 ? "+" : ""}${bt.roi_kelly}%` : "—"}</p>
            </div>
          </div>
        </div>
      )}

      {/* Tabla reciente */}
      {lr
        ? <Spinner />
        : <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-700 text-gray-400 text-xs">
                  <th className="p-3 text-left">Partido</th>
                  <th className="p-2 text-center">Apuesta</th>
                  <th className="p-2 text-center">P&L</th>
                </tr>
              </thead>
              <tbody>
                {(recent || []).slice(-15).reverse().map((pred, i) => (
                  pred.value_bets?.map((vb, j) => (
                    <tr key={`${i}-${j}`} className="border-b border-gray-700/50">
                      <td className="p-3">
                        <p className="text-white text-xs font-medium truncate max-w-[120px]">
                          {pred.home} vs {pred.away}
                        </p>
                        <p className="text-gray-500 text-xs">{pred.date}</p>
                      </td>
                      <td className="p-2 text-center">
                        <p className="text-gray-300 text-xs">{vb.market}</p>
                        <p className="text-gray-400 text-xs">@ {vb.odds || vb.best_odds}</p>
                      </td>
                      <td className="p-2 text-center">
                        {"won" in vb
                          ? <p className={`font-bold text-xs ${vb.won ? "text-green-400" : "text-red-400"}`}>
                              {vb.won ? "✅" : "❌"} {vb.pnl >= 0 ? "+" : ""}{vb.pnl}u
                            </p>
                          : <p className="text-yellow-400 text-xs">⏳</p>
                        }
                      </td>
                    </tr>
                  ))
                ))}
              </tbody>
            </table>
          </div>
      }
    </div>
  );
}

// ── Tab: Calibración ─────────────────────────────────────────────────────────

function TabCalibration() {
  const { data, loading, error, reload } = useFetch("/api/calibration", []);

  if (loading) return <Spinner />;
  if (error) return <ErrorBox msg={error} onRetry={reload} />;

  const entries = Object.entries(data || {});
  if (!entries.length) {
    return (
      <div className="bg-gray-800 rounded-xl p-6 text-center border border-gray-700">
        <p className="text-gray-400">Sin datos de calibración aún.</p>
        <p className="text-gray-500 text-sm mt-1">Se calculará automáticamente con el historial.</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-gray-400 text-sm">Precisión del modelo por liga (Brier Score + ECE)</p>
      {entries.sort((a, b) => b[1].penalty_factor - a[1].penalty_factor).map(([league, d]) => {
        const gradeColor = { A: "text-green-400", B: "text-yellow-400", C: "text-orange-400", D: "text-red-400" }[d.grade] || "text-gray-400";
        const barWidth = `${d.penalty_factor * 100}%`;
        return (
          <div key={league} className="bg-gray-800 rounded-xl p-4 border border-gray-700">
            <div className="flex justify-between items-center mb-2">
              <p className="text-white font-semibold text-sm">{league}</p>
              <span className={`font-bold text-lg ${gradeColor}`}>{d.grade}</span>
            </div>
            <div className="flex gap-4 text-xs text-gray-400 mb-2">
              <span>n={d.n}</span>
              <span>HR {pct(d.hit_rate)}</span>
              <span>Cal.error {d.calibration_error?.toFixed(3)}</span>
              <span>Brier {d.brier_score?.toFixed(3)}</span>
            </div>
            <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
              <div className="h-full bg-blue-500 rounded-full" style={{ width: barWidth }} />
            </div>
            <p className="text-xs text-gray-500 mt-1">Factor penalización: ×{d.penalty_factor}</p>
          </div>
        );
      })}
    </div>
  );
}

// ── Tab: Admin (Premium) ──────────────────────────────────────────────────────

function TabAdmin({ open, onClose }) {
  const { data: status, loading: stLoading } = useFetch("/api/admin/status", [open]);
  const [password, setPassword] = useState("");
  const [authOk, setAuthOk] = useState(false);
  const [sessionInfo, setSessionInfo] = useState(null);
  const [authLoading, setAuthLoading] = useState(false);
  const [overview, setOverview] = useState(null);
  const [ovLoading, setOvLoading] = useState(false);
  const [userId, setUserId] = useState("");
  const [username, setUsername] = useState("");
  const [days, setDays] = useState(30);
  const [msg, setMsg] = useState(null);
  const [err, setErr] = useState(null);
  const [users, setUsers] = useState(null);
  const [busy, setBusy] = useState(false);
  const [customTg, setCustomTg] = useState("");
  const [userFilter, setUserFilter] = useState("");
  const [benchmark, setBenchmark] = useState([]);
  const [benchmarkSummary, setBenchmarkSummary] = useState(null);
  const [benchmarkForm, setBenchmarkForm] = useState(EMPTY_BENCHMARK_FORM);

  const adminRequest = async (path, options = {}) => {
    const init = {
      credentials: "include",
      ...options,
    };
    const headers = {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    };
    if (Object.keys(headers).length) init.headers = headers;
    const res = await fetch(`${API_BASE}${path}`, init);
    return parseJsonResponse(res);
  };

  const loadSession = async () => {
    const j = await adminRequest("/api/admin/session");
    setSessionInfo(j);
    setAuthOk(Boolean(j?.authenticated));
    return j;
  };

  const loadOverview = async ({ silent = false, rethrow = false } = {}) => {
    if (!silent) setOvLoading(true);
    try {
      const j = await adminRequest("/api/admin/overview");
      setOverview(j);
      return j;
    } catch (e) {
      if (!silent) setOverview(null);
      setAuthOk(false);
      if (rethrow) throw e;
    } finally {
      if (!silent) setOvLoading(false);
    }
    return null;
  };

  const loadUsers = async ({ silent = false, rethrow = false } = {}) => {
    if (!silent) setBusy(true);
    try {
      const j = await adminRequest("/api/admin/users");
      setUsers(j.users || []);
      return j.users || [];
    } catch (e) {
      if (!silent) setUsers(null);
      setAuthOk(false);
      if (rethrow) throw e;
    } finally {
      if (!silent) setBusy(false);
    }
    return null;
  };

  const loadBenchmark = async ({ silent = false, rethrow = false } = {}) => {
    if (!silent) setBusy(true);
    try {
      const j = await adminRequest("/api/admin/benchmark");
      setBenchmark(j.picks || []);
      setBenchmarkSummary(j.summary || null);
      return j;
    } catch (e) {
      if (!silent) {
        setBenchmark([]);
        setBenchmarkSummary(null);
      }
      setAuthOk(false);
      if (rethrow) throw e;
    } finally {
      if (!silent) setBusy(false);
    }
    return null;
  };

  const hydrateAdmin = async () => {
    await Promise.all([
      loadOverview({ silent: true, rethrow: true }),
      loadUsers({ silent: true, rethrow: true }),
      loadBenchmark({ silent: true, rethrow: true }),
    ]);
  };

  useEffect(() => {
    if (!open) return;
    setErr(null);
    setMsg(null);
    loadSession()
      .then((session) => {
        if (session?.authenticated) {
          hydrateAdmin().catch((e) => setErr(e.message));
        }
      })
      .catch((e) => setErr(e.message));
  }, [open]);

  useEffect(() => {
    if (!open || !authOk || !overview?.analysis_job_busy) return undefined;
    const id = setInterval(() => {
      loadOverview({ silent: true });
    }, 4000);
    return () => clearInterval(id);
  }, [open, authOk, overview?.analysis_job_busy]);

  const connectAdmin = async () => {
    if (!password.trim()) {
      setErr("Escribe la clave administrativa para abrir la consola.");
      return;
    }
    setAuthLoading(true);
    setErr(null);
    setMsg(null);
    try {
      const j = await adminRequest("/api/admin/login", {
        method: "POST",
        body: JSON.stringify({ password }),
      });
      setPassword("");
      setMsg(j.message || "Acceso autorizado.");
      setAuthOk(true);
      await loadSession();
      await hydrateAdmin();
    } catch (e) {
      setAuthOk(false);
      setOverview(null);
      setUsers(null);
      setBenchmark([]);
      setBenchmarkSummary(null);
      setErr(e.message);
    } finally {
      setAuthLoading(false);
    }
  };

  const logoutAdmin = async () => {
    setBusy(true);
    try {
      const j = await adminRequest("/api/admin/logout", { method: "POST" });
      setAuthOk(false);
      setSessionInfo(null);
      setOverview(null);
      setUsers(null);
      setBenchmark([]);
      setBenchmarkSummary(null);
      setMsg(j.message || "Sesión cerrada.");
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  const forceAnalysis = async () => {
    if (!window.confirm("¿Ejecutar análisis completo ahora? Puede tardar varios minutos y consumir cuota de APIs externas.")) return;
    setBusy(true);
    setErr(null);
    try {
      const j = await adminRequest("/api/admin/analysis/run", { method: "POST" });
      setMsg(j.message || "Análisis lanzado.");
      await loadOverview({ silent: true });
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  const publishTelegram = async (mode) => {
    setBusy(true);
    setErr(null);
    try {
      const j = await adminRequest("/api/admin/telegram/publish", {
        method: "POST",
        body: JSON.stringify(mode === "custom" ? { mode: "custom", text: customTg } : { mode: "summary", text: "" }),
      });
      setMsg(`Canal: enviado (${j.parts_sent || 1} bloque(s)).`);
      await loadOverview({ silent: true });
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  const activatePremium = async (e) => {
    e.preventDefault();
    setErr(null);
    setMsg(null);
    const uid = parseInt(String(userId).trim(), 10);
    if (!uid || Number.isNaN(uid)) {
      setErr("Introduce un User ID numérico válido de Telegram.");
      return;
    }
    setBusy(true);
    try {
      const j = await adminRequest("/api/admin/premium", {
        method: "POST",
        body: JSON.stringify({
          user_id: uid,
          days: Math.min(3650, Math.max(1, Number(days) || 30)),
          username: username.trim(),
        }),
      });
      setMsg(`Premium actualizado para ${j.user_id}. Vence: ${j.premium_until?.slice(0, 10) || "—"}`);
      setUserId("");
      setUsername("");
      await loadUsers({ silent: true });
      await loadOverview({ silent: true });
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  const revokePremium = async (uid) => {
    if (!window.confirm(`¿Quitar Premium al usuario ${uid}?`)) return;
    setBusy(true);
    setErr(null);
    try {
      const j = await adminRequest("/api/admin/premium/revoke", {
        method: "POST",
        body: JSON.stringify({ user_id: uid }),
      });
      setMsg(`Premium revocado para ${j.user_id}.`);
      await loadUsers({ silent: true });
      await loadOverview({ silent: true });
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  const toggleLineAlerts = async (uid, enabled) => {
    setBusy(true);
    setErr(null);
    try {
      const j = await adminRequest("/api/admin/users/line-alerts", {
        method: "POST",
        body: JSON.stringify({ user_id: uid, enabled }),
      });
      setMsg(`Alertas de cuota ${enabled ? "activadas" : "desactivadas"} para ${j.user_id}.`);
      await loadUsers({ silent: true });
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  const saveBenchmark = async (e) => {
    e.preventDefault();
    if (!benchmarkForm.source.trim() || !benchmarkForm.home.trim() || !benchmarkForm.away.trim() || !benchmarkForm.market.trim() || !benchmarkForm.selection.trim() || !benchmarkForm.odds) {
      setErr("Completa fuente, partido, mercado, selección y cuota para guardar la comparativa.");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await adminRequest("/api/admin/benchmark", {
        method: "POST",
        body: JSON.stringify({
          source: benchmarkForm.source.trim(),
          league_id: benchmarkForm.leagueId ? Number(benchmarkForm.leagueId) : null,
          league: benchmarkForm.league.trim(),
          home: benchmarkForm.home.trim(),
          away: benchmarkForm.away.trim(),
          market: benchmarkForm.market.trim(),
          selection: benchmarkForm.selection.trim(),
          odds: Number(benchmarkForm.odds),
          kickoff_utc: benchmarkForm.kickoffUtc ? new Date(benchmarkForm.kickoffUtc).toISOString() : "",
          note: benchmarkForm.note.trim(),
        }),
      });
      setBenchmarkForm(EMPTY_BENCHMARK_FORM);
      setMsg("Benchmark guardado y comparado contra el radar actual.");
      await loadBenchmark({ silent: true });
      await loadOverview({ silent: true });
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  const deleteBenchmark = async (pickId) => {
    if (!window.confirm("¿Eliminar esta referencia externa del benchmark?")) return;
    setBusy(true);
    try {
      await adminRequest(`/api/admin/benchmark/${pickId}`, { method: "DELETE" });
      setMsg("Benchmark eliminado.");
      await loadBenchmark({ silent: true });
      await loadOverview({ silent: true });
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  const filteredUsers = (users || []).filter((u) => {
    const q = userFilter.trim().toLowerCase();
    if (!q) return true;
    return (
      String(u.user_id).includes(q)
      || String(u.username || "").toLowerCase().includes(q)
    );
  });

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm overflow-y-auto p-4">
      <div className="max-w-7xl mx-auto">
        <div className="rounded-[32px] border border-gray-700 bg-gray-900 shadow-2xl overflow-hidden">
          <div className="sticky top-0 z-10 border-b border-gray-800 bg-gray-900/95 backdrop-blur px-5 py-4">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <p className="text-blue-400 text-xs font-semibold tracking-[0.18em] uppercase">Acceso operadores</p>
                <h2 className="text-white text-2xl font-bold mt-1">Consola administrativa segura</h2>
                <p className="text-gray-400 text-sm mt-2 max-w-3xl">
                  Control privado para publicar en canal, ejecutar análisis, gestionar premium y comparar tu radar con referencias externas.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <span className={`px-2.5 py-1 rounded-full text-xs font-semibold ${authOk ? "bg-green-900/30 text-green-300" : "bg-gray-700 text-gray-300"}`}>
                  {authOk ? "Sesión activa" : "Sesión cerrada"}
                </span>
                {sessionInfo?.session_expires_utc && (
                  <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-gray-800 text-gray-300 border border-gray-700">
                    Expira {fmtUtcTime(sessionInfo.session_expires_utc)} UTC
                  </span>
                )}
                <button
                  type="button"
                  onClick={onClose}
                  className="px-3 py-2 rounded-xl bg-gray-800 hover:bg-gray-700 text-sm text-white"
                >
                  Cerrar
                </button>
              </div>
            </div>
          </div>

          <div className="p-5 space-y-4">
            {stLoading && <Spinner />}

            {!stLoading && !status?.admin_enabled && (
              <div className="bg-amber-900/20 border border-amber-700/40 rounded-xl p-4 space-y-2">
                <p className="text-amber-200 text-sm font-semibold">Consola no disponible</p>
                <p className="text-gray-400 text-xs">
                  Define <code className="text-amber-300">ADMIN_TOKEN</code> y, de preferencia, <code className="text-amber-300">ADMIN_SESSION_SECRET</code> en el servidor para habilitar el acceso seguro.
                </p>
              </div>
            )}

            {!stLoading && status?.admin_enabled && !authOk && (
              <div className="grid xl:grid-cols-[1.1fr,0.9fr] gap-4">
                <div className="rounded-2xl border border-gray-700 bg-gradient-to-br from-gray-800 to-gray-900 p-5">
                  <SectionTitle
                    eyebrow="Ingreso seguro"
                    title="Entrar como operador"
                    subtitle="La clave solo se usa para abrir una sesión segura en cookie. Ya no se guarda ni se reenvía como token en cada petición."
                  />
                  <div className="mt-5 space-y-3">
                    <div>
                      <label className="text-xs text-gray-400">Clave administrativa</label>
                      <input
                        type="password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        placeholder="Ingresa tu clave privada"
                        className="w-full mt-1 bg-gray-900 border border-gray-600 rounded-xl px-3 py-3 text-sm text-white"
                      />
                    </div>
                    <button
                      type="button"
                      onClick={connectAdmin}
                      disabled={!password.trim() || authLoading}
                      className="w-full bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white py-3 rounded-xl text-sm font-semibold"
                    >
                      {authLoading ? "Abriendo sesión…" : "Abrir consola"}
                    </button>
                  </div>
                </div>

                <div className="rounded-2xl border border-gray-700 bg-gray-800/85 p-5">
                  <SectionTitle
                    eyebrow="Seguridad"
                    title="Qué cambió"
                    subtitle="Acceso más estable y menos expuesto para operar desde web."
                  />
                  <div className="space-y-3 mt-5 text-sm">
                    <div className="rounded-2xl border border-gray-700 bg-gray-900/60 p-4">
                      <p className="text-white font-semibold">Sesión por cookie</p>
                      <p className="text-gray-400 text-sm mt-2">La sesión vive en una cookie segura del servidor, no en `sessionStorage` ni en headers manuales.</p>
                    </div>
                    <div className="rounded-2xl border border-gray-700 bg-gray-900/60 p-4">
                      <p className="text-white font-semibold">Acceso secundario</p>
                      <p className="text-gray-400 text-sm mt-2">La consola ya no compite con la navegación pública. Se abre desde el pie como acceso de operadores.</p>
                    </div>
                    <div className="rounded-2xl border border-gray-700 bg-gray-900/60 p-4">
                      <p className="text-white font-semibold">Flujo más limpio</p>
                      <p className="text-gray-400 text-sm mt-2">Menos fricción al entrar y mejor control para publicar, revisar análisis y gestionar usuarios premium.</p>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {authOk && (
              <div className="space-y-4">
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => Promise.all([loadOverview(), loadUsers(), loadBenchmark()])}
                    disabled={ovLoading || busy}
                    className="bg-gray-700 hover:bg-gray-600 disabled:opacity-50 text-white px-4 py-2 rounded-xl text-sm"
                  >
                    Refrescar consola
                  </button>
                  <button
                    type="button"
                    onClick={logoutAdmin}
                    disabled={busy}
                    className="bg-gray-800 hover:bg-gray-700 disabled:opacity-50 text-white px-4 py-2 rounded-xl text-sm border border-gray-700"
                  >
                    Cerrar sesión
                  </button>
                </div>

                {overview && (
                  <div className="space-y-3">
                    <div className="grid md:grid-cols-2 xl:grid-cols-6 gap-3">
                      <QuickInsight label="Usuarios" value={overview.users?.total ?? 0} hint={`${overview.users?.premium ?? 0} premium · ${overview.users?.free ?? 0} free`} />
                      <QuickInsight label="Partidos en caché" value={overview.live?.matches_analyzed ?? 0} hint={`${overview.live?.with_value ?? 0} con valor visible`} />
                      <QuickInsight
                        label="Estado job"
                        value={overview.analysis_job?.status || "idle"}
                        hint={
                          overview.analysis_job?.error
                            || (overview.analysis_job?.runtime_owner
                              ? `Owner ${overview.analysis_job.runtime_owner} · ${fmtUtcTime(overview.analysis_job?.runtime_started_at)} UTC`
                              : `Última ejecución: ${fmtUtcTime(overview.live?.last_run)} UTC`)
                        }
                      />
                      <QuickInsight label="Histórico" value={overview.tracker?.total_bets ?? 0} hint={`ROI ${overview.tracker?.roi_pct ?? "—"}% · P&L ${overview.tracker?.pnl_units ?? "—"}u`} />
                      <QuickInsight
                        label="Canal"
                        value={overview.live?.last_publish_kind || "sin post"}
                        hint={overview.live?.last_publish_utc ? `Último ${fmtUtcDateTime(overview.live?.last_publish_utc)}` : "Aún sin publicaciones"}
                      />
                      <QuickInsight
                        label="Cruce externo"
                        value={overview.benchmark?.total ?? 0}
                        hint={`${overview.benchmark?.aligned ?? 0} alineados · ${overview.benchmark?.different ?? 0} distintos`}
                      />
                    </div>

                    <div className="grid xl:grid-cols-[1.05fr,0.95fr] gap-4">
                      <div className="rounded-2xl border border-gray-700 bg-gray-800/85 p-5">
                        <SectionTitle
                          eyebrow="Servidor"
                          title="Estado operativo"
                          subtitle="Lectura ejecutiva de la instancia, cronogramas y configuración activa."
                        />
                        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3 mt-5 text-sm">
                          <div className="rounded-xl bg-gray-900/70 p-4">
                            <p className="text-gray-500 text-xs">Hora servidor</p>
                            <p className="text-white font-semibold mt-1">{fmtUtcDateTime(overview.server?.time_utc)}</p>
                          </div>
                          <div className="rounded-xl bg-gray-900/70 p-4">
                            <p className="text-gray-500 text-xs">Próxima pasada</p>
                            <p className="text-white font-semibold mt-1">{fmtUtcDateTime(overview.server?.next_run_utc)}</p>
                          </div>
                          <div className="rounded-xl bg-gray-900/70 p-4">
                            <p className="text-gray-500 text-xs">Horarios UTC</p>
                            <p className="text-white font-semibold mt-1">{overview.config?.report_hours_utc?.join(", ") || "—"}</p>
                          </div>
                          <div className="rounded-xl bg-gray-900/70 p-4">
                            <p className="text-gray-500 text-xs">Odds regions</p>
                            <p className="text-white font-semibold mt-1">{overview.config?.odds_regions || "—"}</p>
                          </div>
                          <div className="rounded-xl bg-gray-900/70 p-4">
                            <p className="text-gray-500 text-xs">Warmup al iniciar</p>
                            <p className="text-white font-semibold mt-1">
                              {overview.config?.auto_warmup_on_start ? `Sí · ${overview.config?.startup_analysis_delay_sec ?? 0}s` : "Desactivado"}
                            </p>
                          </div>
                          <div className="rounded-xl bg-gray-900/70 p-4">
                            <p className="text-gray-500 text-xs">Boletín Telegram</p>
                            <p className="text-white font-semibold mt-1">
                              {overview.config?.telegram_publish_match_details
                                ? `Resumen + ${overview.config?.telegram_publish_top_matches ?? 0} detalles`
                                : "Solo resumen"}
                            </p>
                          </div>
                        </div>
                        <div className="mt-4 rounded-2xl border border-gray-700 bg-gray-900/60 p-4">
                          <p className="text-white font-semibold text-sm">Ligas activas</p>
                          <p className="text-gray-400 text-xs mt-2">
                            {overview.config?.target_leagues?.map((league) => league.display_full || league.name).join(" · ")}
                          </p>
                          <p className="text-gray-400 text-xs mt-2">
                            Alertas de cuota cada {Math.round((overview.config?.line_move_poll_interval_sec ?? 0) / 60) || 0} min
                            {" · "}Último publish {overview.live?.last_publish_utc ? fmtUtcDateTime(overview.live?.last_publish_utc) : "sin registro"}
                          </p>
                        </div>
                      </div>

                      <div className="rounded-2xl border border-gray-700 bg-gray-800/85 p-5">
                        <SectionTitle
                          eyebrow="Canal y motor"
                          title="Acciones rápidas"
                          subtitle="Dispara procesos clave y controla la salida editorial del canal desde una sola consola."
                        />
                        <div className="space-y-3 mt-5">
                          <button
                            type="button"
                            onClick={forceAnalysis}
                            disabled={busy}
                            className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white py-3 rounded-xl text-sm font-semibold"
                          >
                            Forzar análisis completo
                          </button>
                          <button
                            type="button"
                            onClick={() => publishTelegram("summary")}
                            disabled={busy}
                            className="w-full bg-sky-700 hover:bg-sky-600 disabled:opacity-50 text-white py-3 rounded-xl text-sm font-semibold"
                          >
                            Publicar boletín editorial
                          </button>
                          <textarea
                            value={customTg}
                            onChange={(e) => setCustomTg(e.target.value)}
                            placeholder="Mensaje manual para el canal (HTML permitido)…"
                            rows={4}
                            className="w-full bg-gray-900 border border-gray-600 rounded-xl px-3 py-3 text-sm text-white"
                          />
                          <button
                            type="button"
                            onClick={() => publishTelegram("custom")}
                            disabled={busy || !customTg.trim()}
                            className="w-full bg-sky-900 hover:bg-sky-800 disabled:opacity-50 text-white py-3 rounded-xl text-sm"
                          >
                            Enviar mensaje manual
                          </button>
                        </div>
                        <div className="mt-4 rounded-2xl border border-gray-700 bg-gray-900/60 p-4">
                          <p className="text-white text-sm font-semibold">Integraciones</p>
                          <p className="text-gray-400 text-xs mt-2">
                            Telegram token: {overview.integrations?.telegram_token_set ? "configurado" : "ausente"}
                          </p>
                          <p className="text-gray-400 text-xs mt-1">
                            Canal destino: {overview.integrations?.telegram_chat_id_set ? "listo para publicar" : "falta TELEGRAM_CHAT_ID"}
                          </p>
                          <p className="text-gray-400 text-xs mt-1">
                            Último destino: {overview.live?.last_publish_target || "sin actividad"}
                          </p>
                        </div>
                      </div>
                    </div>

                    <div className="grid xl:grid-cols-[1fr,1fr] gap-4">
                      <div className="rounded-2xl border border-gray-700 bg-gray-800/85 p-5">
                        <SectionTitle
                          eyebrow="Radar interno"
                          title="Destacados del ciclo"
                          subtitle="Lectura rápida de los partidos que hoy empujan el boletín, la portada y el trabajo del operador."
                        />
                        <div className="grid md:grid-cols-2 gap-3 mt-5">
                          {(overview.highlights_preview || []).length
                            ? overview.highlights_preview.map((item, idx) => (
                                <AdminHighlightMini key={`${item.match_id || idx}-${idx}`} item={item} />
                              ))
                            : <p className="text-gray-500 text-sm">No hay destacados cargados todavía.</p>}
                        </div>
                      </div>

                      <div className="rounded-2xl border border-gray-700 bg-gray-800/85 p-5">
                        <SectionTitle
                          eyebrow="Historial"
                      title="Señales recientes del sistema"
                          subtitle="Último rastro del sistema en producción para revisar continuidad y desempeño."
                        />
                        <div className="space-y-3 mt-5">
                          {(overview.recent_predictions || []).length
                            ? overview.recent_predictions.map((pred, idx) => (
                                <RecentSignalRow key={`${pred.match_id || idx}-recent-admin`} pred={pred} />
                              ))
                            : <p className="text-gray-500 text-sm">Sin señales históricas recientes.</p>}
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                <div className="grid xl:grid-cols-[0.9fr,1.1fr] gap-4">
                  <form onSubmit={activatePremium} className="rounded-2xl border border-gray-700 bg-gray-800/85 p-5 space-y-4">
                    <SectionTitle
                      eyebrow="Usuarios"
                      title="Altas y renovación Premium"
                      subtitle="El identificador fiable sigue siendo el user ID numérico de Telegram. Puedes extender vencimientos ya activos."
                    />
                    <div>
                      <label className="text-xs text-gray-400">User ID</label>
                      <input
                        type="text"
                        inputMode="numeric"
                        value={userId}
                        onChange={(e) => setUserId(e.target.value)}
                        placeholder="ej. 123456789"
                        className="w-full mt-1 bg-gray-900 border border-gray-600 rounded-xl px-3 py-3 text-sm text-white"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-gray-400">@Username (opcional)</label>
                      <input
                        type="text"
                        value={username}
                        onChange={(e) => setUsername(e.target.value.replace(/^@/, ""))}
                        placeholder="sin @"
                        className="w-full mt-1 bg-gray-900 border border-gray-600 rounded-xl px-3 py-3 text-sm text-white"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-gray-400">Días a sumar</label>
                      <input
                        type="number"
                        min={1}
                        max={3650}
                        value={days}
                        onChange={(e) => setDays(e.target.value)}
                        className="w-full mt-1 bg-gray-900 border border-gray-600 rounded-xl px-3 py-3 text-sm text-white"
                      />
                    </div>
                    <div className="flex gap-2">
                      <button
                        type="submit"
                        disabled={busy}
                        className="flex-1 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white py-3 rounded-xl text-sm font-semibold"
                      >
                        Guardar / extender Premium
                      </button>
                      <button
                        type="button"
                        onClick={() => loadUsers()}
                        disabled={busy}
                        className="px-4 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 text-white py-3 rounded-xl text-sm"
                      >
                        Recargar
                      </button>
                    </div>
                  </form>

                  <div className="rounded-2xl border border-gray-700 bg-gray-800/85 p-5">
                    <SectionTitle
                      eyebrow="Base de usuarios"
                      title="Planes, actividad y alertas"
                      subtitle="Vista operativa de usuarios, vencimientos y control de line alerts premium."
                    />
                    <div className="mt-4">
                      <input
                        type="text"
                        value={userFilter}
                        onChange={(e) => setUserFilter(e.target.value)}
                        placeholder="Filtrar por ID o @username…"
                        className="w-full bg-gray-900 border border-gray-600 rounded-xl px-3 py-3 text-sm text-white"
                      />
                    </div>
                    {users && filteredUsers.length > 0 && (
                      <div className="mt-4 overflow-x-auto rounded-2xl border border-gray-700">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="border-b border-gray-700 text-gray-400 text-xs bg-gray-900/60">
                              <th className="p-3 text-left">Usuario</th>
                              <th className="p-3 text-left">Plan</th>
                              <th className="p-3 text-left">Actividad</th>
                              <th className="p-3 text-right">Control</th>
                            </tr>
                          </thead>
                          <tbody>
                            {filteredUsers.map((u) => (
                              <tr key={u.user_id} className="border-b border-gray-700/50 align-top">
                                <td className="p-3">
                                  <p className="text-white font-mono text-xs">{u.user_id}</p>
                                  <p className="text-gray-400 text-xs mt-1">@{u.username || "sin_username"}</p>
                                  <p className="text-gray-500 text-[11px] mt-1">Alta: {u.joined_at ? fmtDateTime(u.joined_at) : "—"}</p>
                                </td>
                                <td className="p-3">
                                  <p className={`text-xs font-semibold ${u.is_premium ? "text-green-400" : "text-gray-400"}`}>
                                    {u.is_premium ? "Premium" : "Free"}
                                  </p>
                                  <p className="text-gray-500 text-[11px] mt-1">
                                    Vence: {u.premium_until ? fmtDateTime(u.premium_until) : "—"}
                                  </p>
                                  <p className="text-gray-500 text-[11px] mt-1">
                                    Line alerts: {u.notify_line_moves ? "activas" : "—"}
                                  </p>
                                </td>
                                <td className="p-3">
                                  <p className="text-gray-300 text-xs">Alertas totales: {u.total_alerts_sent ?? 0}</p>
                                  <p className="text-gray-500 text-[11px] mt-1">Hoy: {u.alerts_today ?? 0}</p>
                                </td>
                                <td className="p-3">
                                  <div className="flex flex-col items-end gap-2">
                                    <button
                                      type="button"
                                      onClick={() => toggleLineAlerts(u.user_id, !u.notify_line_moves)}
                                      disabled={busy}
                                      className="text-xs text-sky-300 hover:text-white"
                                    >
                                      {u.notify_line_moves ? "Desactivar line alerts" : "Activar line alerts"}
                                    </button>
                                    {u.is_premium && (
                                      <button
                                        type="button"
                                        onClick={() => revokePremium(u.user_id)}
                                        disabled={busy}
                                        className="text-xs text-red-400 hover:text-red-300"
                                      >
                                        Quitar Premium
                                      </button>
                                    )}
                                  </div>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                    {users && filteredUsers.length === 0 && (
                      <p className="text-gray-500 text-sm text-center mt-5">No hay usuarios que coincidan con el filtro.</p>
                    )}
                    {users === null && (
                      <p className="text-gray-500 text-sm text-center mt-5">
                        Inicia sesión y recarga usuarios para abrir la base actual.
                      </p>
                    )}
                  </div>
                </div>

                <div className="grid xl:grid-cols-[0.92fr,1.08fr] gap-4">
                  <form onSubmit={saveBenchmark} className="rounded-2xl border border-gray-700 bg-gray-800/85 p-5 space-y-4">
                    <SectionTitle
                      eyebrow="Cruce manual"
                      title="Comparar con tipsters o referentes"
                      subtitle="Carga picks externos autorizados de forma manual y revisa si coinciden con el radar propio, si divergen o si aún no existe cruce."
                    />
                    <div className="grid md:grid-cols-2 gap-3">
                      <div>
                        <label className="text-xs text-gray-400">Fuente</label>
                        <input
                          type="text"
                          value={benchmarkForm.source}
                          onChange={(e) => setBenchmarkForm((prev) => ({ ...prev, source: e.target.value }))}
                          placeholder="ej. Tipster Alpha"
                          className="w-full mt-1 bg-gray-900 border border-gray-600 rounded-xl px-3 py-3 text-sm text-white"
                        />
                      </div>
                      <div>
                        <label className="text-xs text-gray-400">Liga</label>
                        <select
                          value={benchmarkForm.leagueId}
                          onChange={(e) => {
                            const league = overview?.config?.target_leagues?.find((item) => String(item.id) === e.target.value);
                            setBenchmarkForm((prev) => ({
                              ...prev,
                              leagueId: e.target.value,
                              league: league?.display_full || league?.name || "",
                            }));
                          }}
                          className="w-full mt-1 bg-gray-900 border border-gray-600 rounded-xl px-3 py-3 text-sm text-white"
                        >
                          <option value="">Manual / sin liga fija</option>
                          {(overview?.config?.target_leagues || []).map((league) => (
                            <option key={league.id} value={league.id}>{league.display_full || league.name}</option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className="text-xs text-gray-400">Local</label>
                        <input
                          type="text"
                          value={benchmarkForm.home}
                          onChange={(e) => setBenchmarkForm((prev) => ({ ...prev, home: e.target.value }))}
                          className="w-full mt-1 bg-gray-900 border border-gray-600 rounded-xl px-3 py-3 text-sm text-white"
                        />
                      </div>
                      <div>
                        <label className="text-xs text-gray-400">Visita</label>
                        <input
                          type="text"
                          value={benchmarkForm.away}
                          onChange={(e) => setBenchmarkForm((prev) => ({ ...prev, away: e.target.value }))}
                          className="w-full mt-1 bg-gray-900 border border-gray-600 rounded-xl px-3 py-3 text-sm text-white"
                        />
                      </div>
                      <div>
                        <label className="text-xs text-gray-400">Mercado</label>
                        <input
                          type="text"
                          value={benchmarkForm.market}
                          onChange={(e) => setBenchmarkForm((prev) => ({ ...prev, market: e.target.value }))}
                          placeholder="1X2, Totales, BTTS..."
                          className="w-full mt-1 bg-gray-900 border border-gray-600 rounded-xl px-3 py-3 text-sm text-white"
                        />
                      </div>
                      <div>
                        <label className="text-xs text-gray-400">Selección</label>
                        <input
                          type="text"
                          value={benchmarkForm.selection}
                          onChange={(e) => setBenchmarkForm((prev) => ({ ...prev, selection: e.target.value }))}
                          placeholder="Home, Over 2.5, BTTS Sí..."
                          className="w-full mt-1 bg-gray-900 border border-gray-600 rounded-xl px-3 py-3 text-sm text-white"
                        />
                      </div>
                      <div>
                        <label className="text-xs text-gray-400">Cuota</label>
                        <input
                          type="number"
                          step="0.01"
                          min="1.01"
                          value={benchmarkForm.odds}
                          onChange={(e) => setBenchmarkForm((prev) => ({ ...prev, odds: e.target.value }))}
                          className="w-full mt-1 bg-gray-900 border border-gray-600 rounded-xl px-3 py-3 text-sm text-white"
                        />
                      </div>
                      <div>
                        <label className="text-xs text-gray-400">Inicio UTC</label>
                        <input
                          type="datetime-local"
                          value={benchmarkForm.kickoffUtc}
                          onChange={(e) => setBenchmarkForm((prev) => ({ ...prev, kickoffUtc: e.target.value }))}
                          className="w-full mt-1 bg-gray-900 border border-gray-600 rounded-xl px-3 py-3 text-sm text-white"
                        />
                      </div>
                    </div>
                    <div>
                      <label className="text-xs text-gray-400">Nota</label>
                      <textarea
                        value={benchmarkForm.note}
                        onChange={(e) => setBenchmarkForm((prev) => ({ ...prev, note: e.target.value }))}
                        rows={3}
                        placeholder="Ángulo, contexto o por qué quieres seguir esta fuente."
                        className="w-full mt-1 bg-gray-900 border border-gray-600 rounded-xl px-3 py-3 text-sm text-white"
                      />
                    </div>
                    <button
                      type="submit"
                      disabled={busy}
                      className="w-full bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white py-3 rounded-xl text-sm font-semibold"
                    >
                      Guardar referencia externa
                    </button>
                  </form>

                  <div className="rounded-2xl border border-gray-700 bg-gray-800/85 p-5">
                    <SectionTitle
                      eyebrow="Cruce externo"
                      title="Resultado del cruce externo"
                      subtitle="Contrasta picks externos autorizados contra el radar vivo del sistema para detectar coincidencias o divergencias."
                    />
                    {benchmarkSummary && (
                      <div className="grid md:grid-cols-4 gap-3 mt-5">
                        <QuickInsight label="Total" value={benchmarkSummary.total ?? 0} />
                        <QuickInsight label="Alineados" value={benchmarkSummary.aligned ?? 0} />
                        <QuickInsight label="Distintos" value={benchmarkSummary.different ?? 0} />
                        <QuickInsight label="Sin cruce" value={(benchmarkSummary.not_found ?? 0) + (benchmarkSummary.watch ?? 0)} />
                      </div>
                    )}
                    <div className="space-y-3 mt-5 max-h-[560px] overflow-y-auto pr-1">
                      {benchmark.length ? benchmark.map((item) => (
                        <div key={item.id} className="rounded-2xl border border-gray-700 bg-gray-900/70 p-4">
                          <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                            <div>
                              <p className="text-blue-300 text-xs font-semibold">{item.source}</p>
                              <p className="text-white font-semibold mt-1">{item.home} <span className="text-gray-500">vs</span> {item.away}</p>
                              <p className="text-gray-500 text-xs mt-1">{item.league_display || item.league || "Cobertura manual"} · {item.kickoff_utc ? fmtUtcDateTime(item.kickoff_utc) : "sin hora"}</p>
                            </div>
                            <div className="text-right">
                              <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${
                                item.comparison?.status === "aligned"
                                  ? "bg-green-900/30 text-green-300"
                                  : item.comparison?.status === "different"
                                    ? "bg-amber-900/30 text-amber-300"
                                    : "bg-gray-800 text-gray-300"
                              }`}>
                                {item.comparison?.label || "Sin estado"}
                              </span>
                              <p className="text-gray-400 text-xs mt-2">{item.market} · {item.selection} @ {fmtOdds(item.odds)}</p>
                            </div>
                          </div>
                          <div className="mt-3 grid md:grid-cols-2 gap-3 text-sm">
                            <div className="rounded-xl border border-gray-700 bg-gray-800/80 p-3">
                              <p className="text-gray-500 text-xs">Referencia externa</p>
                              <p className="text-white font-medium mt-1">{item.market} · {item.selection}</p>
                              <p className="text-gray-400 text-xs mt-1">Cuota {fmtOdds(item.odds)}</p>
                            </div>
                            <div className="rounded-xl border border-gray-700 bg-gray-800/80 p-3">
                              <p className="text-gray-500 text-xs">Radar propio</p>
                              {item.comparison?.our_pick ? (
                                <>
                                  <p className="text-white font-medium mt-1">{item.comparison.our_pick.market} · {item.comparison.our_pick.selection}</p>
                                  <p className="text-gray-400 text-xs mt-1">
                                    {item.comparison.our_pick.odds ? `Cuota ${fmtOdds(item.comparison.our_pick.odds)}` : "Sin cuota prioritaria"}
                                    {item.comparison.our_pick.value != null ? ` · Edge ${pct(item.comparison.our_pick.value)}` : ""}
                                  </p>
                                </>
                              ) : (
                                <p className="text-gray-500 text-xs mt-1">Sin cruce directo en el análisis vivo.</p>
                              )}
                            </div>
                          </div>
                          {item.note && <p className="text-gray-400 text-xs mt-3">{item.note}</p>}
                          <div className="mt-3 flex justify-end">
                            <button
                              type="button"
                              onClick={() => deleteBenchmark(item.id)}
                              disabled={busy}
                              className="text-xs text-red-400 hover:text-red-300"
                            >
                              Eliminar referencia
                            </button>
                          </div>
                        </div>
                      )) : (
                        <p className="text-gray-500 text-sm">Todavía no hay referencias externas cargadas para comparar.</p>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {err && <ErrorBox msg={err} />}
            {msg && (
              <div className="bg-green-900/30 border border-green-700/40 rounded-xl p-3 text-green-200 text-sm">{msg}</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Tab: Cómo funciona ────────────────────────────────────────────────────────

function TabHowItWorks() {
  const layers = [
    { icon: "📈", title: "Mercado (35%)", desc: "Cuotas de +10 casas. Línea Pinnacle como referencia sharp para eliminar margen." },
    { icon: "🎲", title: "Poisson (25%)", desc: "xG desde stats reales de API-Football. Matriz de resultados para 1X2, O/U, BTTS." },
    { icon: "📊", title: "ELO (15%)", desc: "Rating dinámico pre-cargado desde la tabla de posiciones. Actualizado tras cada partido." },
    { icon: "🔍", title: "Features (15%)", desc: "Forma últimos 5 partidos, tendencia de goles, rachas activas, head-to-head." },
    { icon: "🧠", title: "DeepSeek IA (10%)", desc: "Lesiones, motivación y contexto de temporada. Ajusta ±5% las probabilidades." },
    { icon: "⚖️", title: "Consenso", desc: "Combina las 5 capas con pesos. Detecta señales con EV > 3%." },
  ];

  const premium = [
    { icon: <BarChart2 size={16} />, title: "Backtesting histórico", desc: "ROI real, Sharpe ratio, max drawdown sobre todo el historial." },
    { icon: <Activity size={16} />, title: "Alertas de movimiento", desc: "Steam moves y reverse line movement en tiempo real (+4% Pinnacle)." },
    { icon: <Wallet size={16} />, title: "Bankroll personal", desc: "Kelly fraccionado en €/$ según tu bankroll real. Stakes exactos." },
    { icon: <Target size={16} />, title: "Calibración por liga", desc: "Brier Score y ECE por liga. Penaliza automáticamente ligas débiles." },
    { icon: <Brain size={16} />, title: "XGBoost ML", desc: "Modelo entrenado sobre tu historial acumulado. Supera heurísticas a partir de 500 apuestas." },
    { icon: <BookOpen size={16} />, title: "Mercados extendidos", desc: "BTTS, doble oportunidad, score exacto, resultado al descanso." },
  ];

  return (
    <div className="space-y-4">
      <div className="bg-blue-900/20 border border-blue-700/30 rounded-xl p-4">
        <h3 className="text-blue-400 font-semibold mb-2">¿Qué es una señal con ventaja?</h3>
        <p className="text-gray-300 text-sm">
          Ocurre cuando nuestra probabilidad estimada es <strong>mayor</strong> a la implícita en la cuota.
          A largo plazo, apostar con valor positivo genera beneficio matemático.
        </p>
      </div>

      <div className="space-y-2">
        {layers.map((l, i) => (
          <div key={i} className="bg-gray-800 rounded-xl p-4 border border-gray-700 flex gap-3">
            <span className="text-2xl">{l.icon}</span>
            <div>
              <p className="text-white font-semibold text-sm">Capa {i + 1}: {l.title}</p>
              <p className="text-gray-400 text-xs mt-0.5">{l.desc}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
        <h3 className="text-gray-300 font-semibold mb-3">💎 Features Premium</h3>
        <div className="space-y-2">
          {premium.map((f, i) => (
            <div key={i} className="flex items-start gap-3">
              <span className="text-blue-400 mt-0.5">{f.icon}</span>
              <div>
                <p className="text-white text-sm font-medium">{f.title}</p>
                <p className="text-gray-400 text-xs">{f.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
        <h3 className="text-gray-300 font-semibold mb-2">💰 Costo mensual estimado</h3>
        <div className="space-y-1 text-sm">
          {[
            ["Railway (hosting)", "$5/mes"],
            ["The Odds API", "Gratis (500 req/mes)"],
            ["API-Football", "Gratis (100 req/día)"],
            ["DeepSeek IA", "~$1-2/mes"],
            ["Telegram Bot", "Gratis"],
          ].map(([svc, cost]) => (
            <div key={svc} className="flex justify-between text-gray-400">
              <span>{svc}</span>
              <span className={cost.startsWith("Gratis") ? "text-green-400" : "text-white"}>{cost}</span>
            </div>
          ))}
          <div className="flex justify-between font-bold border-t border-gray-600 pt-2 mt-2">
            <span className="text-white">Total</span>
            <span className="text-green-400">~$6-7/mes</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── App Principal ─────────────────────────────────────────────────────────────

export default function App() {
  const [tab, setTab] = useState("inicio");
  const [adminOpen, setAdminOpen] = useState(false);
  const { data: stats, loading: statsLoading } = useFetch("/api/stats", []);
  const { data: btData } = useFetch("/api/backtest", []);
  const { data: liveOverview } = useFetch("/api/analysis/live", []);

  const tabs = [
    { id: "inicio",    label: "Inicio",      icon: Award },
    { id: "hoy",       label: "Mercados",    icon: Zap },
    { id: "historial", label: "Historial",    icon: BarChart2 },
    { id: "calibracion", label: "Calibración", icon: Target },
    { id: "como",      label: "Cómo funciona", icon: Shield },
  ];

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      {/* Header */}
      <header className="bg-gray-900/90 backdrop-blur border-b border-gray-800 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 py-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-2">
            <div className="bg-blue-600 p-1.5 rounded-lg">
              <Target size={16} className="text-white" />
            </div>
            <div>
              <div>
                <span className="font-bold text-white">ValueX</span>
                <span className="font-bold text-blue-400">Pro</span>
                <span className="ml-2 text-xs bg-blue-900/40 text-blue-400 px-1.5 py-0.5 rounded">V3</span>
              </div>
              <p className="text-[11px] text-gray-500">
                Inteligencia futbolística para leer mercado, priorizar jornadas y publicar con criterio
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className={`text-xs px-2 py-0.5 rounded-full ${stats ? "bg-green-900/40 text-green-400" : "bg-gray-700 text-gray-400"}`}>
              {stats ? "Motor online" : "Cargando stack"}
            </span>
            <span className="text-xs px-2 py-0.5 rounded-full bg-gray-800 text-gray-300 border border-gray-700">
              Última pasada: {fmtUtcTime(liveOverview?.last_run)} UTC
            </span>
            <span className="text-xs px-2 py-0.5 rounded-full bg-gray-800 text-gray-300 border border-gray-700">
              Edge visibles: {liveOverview?.total_value_bets ?? 0}
            </span>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-5 space-y-5">
        {/* Stats */}
        <div className="grid md:grid-cols-2 xl:grid-cols-4 gap-3">
          <StatCard
          icon={TrendingUp} label="ROI histórico"
            value={stats ? `${stats.roi_pct >= 0 ? "+" : ""}${stats.roi_pct}%` : "—"}
            sub={stats ? `${stats.won}✅ ${stats.lost}❌ ${stats.pending || 0}⏳` : ""}
            color="bg-green-600" loading={statsLoading}
          />
          <StatCard
            icon={Target} label="Tasa de acierto"
            value={stats ? pct(stats.hit_rate) : "—"}
            sub={stats ? `P&L: ${stats.pnl_units >= 0 ? "+" : ""}${stats.pnl_units}u` : ""}
            color="bg-blue-600" loading={statsLoading}
          />
          <StatCard
            icon={Zap} label="Señales EV+"
            value={liveOverview ? `${liveOverview.total_value_bets || 0}` : "—"}
            sub={liveOverview ? `${liveOverview.count || 0} partidos analizados` : ""}
            color="bg-indigo-600" loading={!liveOverview}
          />
          <StatCard
            icon={Activity} label="Ventanas del día"
            value={liveOverview ? `${liveOverview.runs_today || 0}` : "—"}
            sub={liveOverview ? `Próxima: ${fmtUtcTime(liveOverview.next_run_utc)} UTC` : ""}
            color="bg-sky-600" loading={!liveOverview}
          />
        </div>

        {/* Gráfico mensual */}
        <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
          <div className="flex justify-between items-center mb-3">
            <p className="text-gray-300 text-sm font-semibold">P&L mensual</p>
            {btData?.pnl_flat != null && (
              <p className={`text-sm font-bold ${btData.pnl_flat >= 0 ? "text-green-400" : "text-red-400"}`}>
                {btData.pnl_flat >= 0 ? "+" : ""}{btData.pnl_flat}u total
              </p>
            )}
          </div>
          <WeeklyChart monthly={btData?.monthly} />
        </div>

        {/* Tabs */}
        <div className="flex bg-gray-800 rounded-xl p-1 border border-gray-700 gap-0.5">
          {tabs.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`flex-1 flex items-center justify-center gap-1 py-2 rounded-lg text-xs transition-all ${
                tab === id ? "bg-blue-600 text-white font-semibold" : "text-gray-400 hover:text-gray-200"
              }`}
            >
              <Icon size={13} />
              <span className="hidden sm:inline truncate">{label}</span>
            </button>
          ))}
        </div>

        {/* Contenido */}
        {tab === "inicio"      && <TabHome />}
        {tab === "hoy"         && <TabToday />}
        {tab === "historial"   && <TabHistory />}
        {tab === "calibracion" && <TabCalibration />}
        {tab === "como"        && <TabHowItWorks />}

        {/* CTA Telegram */}
        <div className="bg-gradient-to-r from-blue-900/50 to-indigo-900/50 border border-blue-700/40 rounded-xl p-4 text-center">
          <p className="text-white font-semibold mb-1">Telegram como sala de decisión</p>
          <p className="text-gray-400 text-sm mb-3">
            Boletines editoriales, picks priorizados, alertas de movimiento y lectura centralizada lista para publicar
          </p>
          <div className="flex gap-2 justify-center">
            <a href="https://t.me/valuexpro_bot" className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-lg text-sm font-semibold transition-colors">
              <Send size={14} /> Bot
            </a>
            <a href="https://t.me/valuexpro" className="flex items-center gap-2 bg-gray-700 hover:bg-gray-600 text-white px-4 py-2 rounded-lg text-sm transition-colors">
              <Globe size={14} /> Canal
            </a>
          </div>
        </div>

        <ProfessionalFooter live={liveOverview} onOpenAdmin={() => setAdminOpen(true)} />
      </main>
      <TabAdmin open={adminOpen} onClose={() => setAdminOpen(false)} />
    </div>
  );
}
