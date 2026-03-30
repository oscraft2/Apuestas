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

function fmtDateTime(iso, withDate = true) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("es-CL", {
      day: withDate ? "2-digit" : undefined,
      month: withDate ? "short" : undefined,
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function fmtTimeOnly(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleTimeString("es-CL", {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
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

function normalizeAdminTokenInput(raw) {
  let s = String(raw || "").replace(/\u200B/g, "").replace(/\uFEFF/g, "").trim();
  const pairs = [
    ['"', '"'],
    ["'", "'"],
    ["“", "”"],
    ["‘", "’"],
  ];
  let changed = true;
  while (changed && s.length >= 2) {
    changed = false;
    for (const [left, right] of pairs) {
      if (s.startsWith(left) && s.endsWith(right)) {
        s = s.slice(left.length, s.length - right.length).trim();
        changed = true;
        break;
      }
    }
  }
  return s;
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
  const top = match?.value_bets?.[0];
  const c1 = match?.consensus_1x2?.probs || {};
  const confidence = match?.consensus_1x2?.confidence || 0;
  const agreement = match?.consensus_1x2?.agreement || 0;

  return (
    <div className={`rounded-2xl border border-gray-700 bg-gray-800/85 p-4 ${compact ? "" : "h-full"}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-blue-400 text-xs font-semibold">{match?.league || "Partido"}</p>
          <h3 className="text-white font-semibold text-lg leading-tight mt-1">
            {match?.home} <span className="text-gray-500">vs</span> {match?.away}
          </h3>
          <p className="text-gray-500 text-xs mt-1">
            {fmtDateTime(match?.time)} UTC
          </p>
        </div>
        {top ? <ValueBadge value={top.value} /> : <span className="text-xs text-blue-300 bg-blue-900/30 px-2 py-1 rounded-full">Seguimiento</span>}
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
            <p className="text-white font-semibold mt-1">Partido con lectura fuerte pero sin EV+ claro</p>
            <p className="text-gray-300 text-sm mt-1">
              Útil para monitorizar movimiento de cuota y nueva pasada automática.
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
          <p className="text-white font-semibold">{league?.name}</p>
          <p className="text-gray-500 text-xs mt-1">{league?.sport_key || "Sin sport_key visible"}</p>
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
          Liga priorizada en el ranking de destacados por decisión operativa.
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
          <p className="text-blue-400 text-xs font-semibold">{item?.league || "Análisis"}</p>
          <p className="text-white font-semibold mt-1">{item?.home} <span className="text-gray-500">vs</span> {item?.away}</p>
          <p className="text-gray-500 text-xs mt-1">{fmtDateTime(item?.time)}</p>
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
              Plataforma profesional de inteligencia futbolística
            </div>

            <h1 className="mt-4 text-3xl md:text-5xl font-bold leading-tight text-white">
              Centro de lectura táctica, mercado y valor para el fútbol del día.
            </h1>
            <p className="mt-4 text-sm md:text-base text-slate-300 max-w-2xl">
              ValueXPro centraliza el análisis, prioriza las ligas más relevantes, filtra el ruido del mercado
              y presenta partidos destacados con una capa visual mucho más ejecutiva para operar, revisar y publicar.
            </p>

            <div className="mt-5 flex flex-wrap gap-2 text-xs">
              <span className="rounded-full bg-white/5 px-3 py-1 text-slate-300 border border-white/10">
                Próxima pasada: {fmtDateTime(live.next_run_utc)}
              </span>
              <span className="rounded-full bg-white/5 px-3 py-1 text-slate-300 border border-white/10">
                Horarios UTC: {(live.report_hours_utc || []).join(", ") || "—"}
              </span>
              <span className="rounded-full bg-white/5 px-3 py-1 text-slate-300 border border-white/10">
                Liga protagonista: {heroLeague}
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
                hint={`Última: ${fmtTimeOnly(live.last_run)} UTC`}
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
        title="Partidos importantes y relevantes"
        subtitle="Selección priorizada por valor esperado, confianza del consenso y acuerdo entre modelos. Es la primera lectura ejecutiva del sistema antes de entrar al detalle."
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
            title="Lectura operativa del sistema"
            subtitle="Resumen profesional de la jornada para saber dónde mirar primero."
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
            title="Historial reciente en producción"
            subtitle="Muestra abreviada del tracker para añadir contexto operativo al día."
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
            title="Información futbolística y marco metodológico"
            subtitle="La portada ya no solo muestra apuestas: también comunica cobertura, ritmo del motor y foco deportivo."
          />
          <div className="grid sm:grid-cols-2 gap-3 mt-5">
            <div className="rounded-2xl border border-gray-700 bg-gray-900/70 p-4">
              <p className="text-white font-semibold">Cobertura principal</p>
              <p className="text-gray-400 text-sm mt-2">
                En esta fase el sistema prioriza ligas americanas con Chile como protagonista, seguido por Brasil,
                Liga MX, MLS, Argentina y Colombia.
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

function ProfessionalFooter({ live }) {
  return (
    <footer className="mt-8 rounded-[28px] border border-gray-700 bg-gray-900/90 overflow-hidden">
      <div className="grid xl:grid-cols-[1.1fr,0.9fr] gap-0">
        <div className="p-6 lg:p-8">
          <p className="text-blue-400 text-xs font-semibold tracking-[0.18em] uppercase">Infraestructura y confianza</p>
          <h3 className="text-white text-2xl font-bold mt-2">Pie de plataforma con protección operativa y enfoque profesional.</h3>
          <p className="text-gray-400 text-sm mt-3 max-w-2xl">
            El frontend no expone claves privadas. Las integraciones sensibles viven en backend, el panel administrativo
            está protegido por token y la lógica de análisis se concentra en el servidor para mantener consistencia operacional.
          </p>

          <div className="grid md:grid-cols-3 gap-3 mt-6">
            <div className="rounded-2xl border border-gray-700 bg-gray-800/85 p-4">
              <p className="text-white font-semibold">Protección de datos</p>
              <p className="text-gray-400 text-sm mt-2">
                Tokens, claves y controles de publicación no se envían al cliente final ni se muestran en la UI pública.
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
                Horarios UTC: {(live?.report_hours_utc || []).join(", ") || "—"} · próxima pasada {fmtDateTime(live?.next_run_utc)}.
              </p>
            </div>
          </div>

          <div className="mt-6 flex flex-wrap gap-2 text-xs text-gray-400">
            <span className="rounded-full border border-gray-700 px-3 py-1 bg-gray-800/80">Backend protegido</span>
            <span className="rounded-full border border-gray-700 px-3 py-1 bg-gray-800/80">Panel admin por token</span>
            <span className="rounded-full border border-gray-700 px-3 py-1 bg-gray-800/80">Análisis centralizado</span>
            <span className="rounded-full border border-gray-700 px-3 py-1 bg-gray-800/80">Foco fútbol profesional</span>
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
              Plataforma de análisis estadístico para fútbol, diseñada para lectura profesional, control operativo y publicación ordenada.
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
  const top = bet.value_bets?.[0];
  const c1 = bet.consensus_1x2?.probs || {};
  const cou = bet.consensus_ou?.probs || {};

  return (
    <div
      className="bg-gray-800 border border-gray-700 rounded-xl p-4 cursor-pointer hover:border-blue-500 transition-all"
      onClick={() => onSelect(bet)}
    >
      <div className="flex justify-between items-start mb-2">
        <div>
          <p className="text-xs text-gray-400">{bet.league} · {bet.date}</p>
          <p className="text-white font-bold">{bet.home} <span className="text-gray-400">vs</span> {bet.away}</p>
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

      {top && (
        <div className="border-t border-gray-700 pt-3 flex items-center justify-between">
          <div>
            <p className="text-xs text-gray-400">{top.market} · {top.label || top.outcome}</p>
            <p className="text-white font-semibold">@ {top.odds || top.best_odds}</p>
          </div>
          <div className="flex items-center gap-2">
            <ValueBadge value={top.value} />
            {bet.value_bets.length > 1 && (
              <span className="text-xs text-gray-500">+{bet.value_bets.length - 1}</span>
            )}
            <ChevronRight size={16} className="text-gray-500" />
          </div>
        </div>
      )}

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
        <p className="text-xs text-gray-400">{bet.league}</p>
        <h2 className="text-xl font-bold text-white">{bet.home} vs {bet.away}</h2>
        <p className="text-gray-400 text-sm">{bet.date} · {bet.time}</p>
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
          <h3 className="text-gray-300 font-semibold mb-3">🔥 Value Bets</h3>
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
        ⚠️ Análisis estadístico. No es consejo financiero.
      </p>
    </div>
  );
}

function TabToday() {
  const { data, loading, error, reload } = useFetch("/api/bets/today", []);
  const [selected, setSelected] = useState(null);

  // Auto-refresh cada 5 minutos
  useEffect(() => {
    const id = setInterval(reload, 5 * 60 * 1000);
    return () => clearInterval(id);
  }, [reload]);

  if (selected) return <BetDetail bet={selected} onBack={() => setSelected(null)} />;
  if (loading) return <Spinner />;
  if (error) return <ErrorBox msg={error} onRetry={reload} />;

  const bets = data?.bets || [];
  const withValue = bets.filter(b => b.value_bets?.length > 0);
  const lastRun = data?.last_run;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-gray-400 text-sm">{withValue.length} partidos con valor hoy</p>
          {lastRun && (
            <p className="text-gray-600 text-xs">
              Actualizado: {new Date(lastRun).toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" })}
              {data?.source === "live" && <span className="ml-1 text-green-500">● en vivo</span>}
            </p>
          )}
        </div>
        <button onClick={reload} className="text-gray-400 hover:text-white p-1">
          <RefreshCw size={14} />
        </button>
      </div>
      {withValue.length === 0
        ? <div className="bg-gray-800 rounded-xl p-6 text-center border border-gray-700">
            <p className="text-gray-400">No hay value bets registradas hoy.</p>
            <p className="text-gray-500 text-sm mt-1">El mercado está eficiente hoy o el bot aún no ha corrido.</p>
          </div>
        : <div className="grid xl:grid-cols-2 gap-3">
            {withValue.map((b, i) => <BetCard key={i} bet={b} onSelect={setSelected} />)}
          </div>
      }
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
          ["Hit rate", ls ? "—" : `${((stats?.hit_rate || 0) * 100).toFixed(0)}%`],
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

function TabAdmin() {
  const { data: status, loading: stLoading } = useFetch("/api/admin/status", []);
  const [token, setToken] = useState(() => normalizeAdminTokenInput(sessionStorage.getItem("valuex_admin_token") || ""));
  const [authOk, setAuthOk] = useState(false);
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

  const persistToken = (t) => {
    const v = normalizeAdminTokenInput(t);
    setToken(v);
    sessionStorage.setItem("valuex_admin_token", v);
  };

  const authHeaders = () => ({
    "X-Admin-Token": normalizeAdminTokenInput(token || ""),
    "Content-Type": "application/json",
  });

  const loadOverview = async ({ silent = false, rethrow = false } = {}) => {
    if (!token.trim()) return;
    if (!silent) setOvLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/admin/overview`, { headers: authHeaders() });
      const j = await res.json();
      if (!res.ok) throw new Error(typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail));
      setOverview(j);
      setAuthOk(true);
      return j;
    } catch (e) {
      if (!silent) {
        setErr(e.message);
        setOverview(null);
      }
      if (rethrow) throw e;
    } finally {
      if (!silent) setOvLoading(false);
    }
  };

  const loadUsers = async ({ silent = false, rethrow = false } = {}) => {
    if (!token.trim()) return;
    if (!silent) setBusy(true);
    try {
      const res = await fetch(`${API_BASE}/api/admin/users`, { headers: authHeaders() });
      const j = await res.json();
      if (!res.ok) throw new Error(typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail));
      setUsers(j.users || []);
      setAuthOk(true);
      return j.users || [];
    } catch (e) {
      if (!silent) {
        setErr(e.message);
        setUsers(null);
      }
      if (rethrow) throw e;
    } finally {
      if (!silent) setBusy(false);
    }
  };

  const connectAdmin = async () => {
    if (!token.trim()) {
      setErr("Introduce el token admin. Si lo pegaste desde Railway, las comillas externas se limpian automáticamente.");
      return;
    }
    setAuthLoading(true);
    setErr(null);
    setMsg(null);
    try {
      const res = await fetch(`${API_BASE}/api/admin/auth/check`, {
        method: "POST",
        headers: authHeaders(),
      });
      const j = await res.json();
      if (!res.ok) throw new Error(typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail));
      setAuthOk(true);
      setMsg(j.message || "Conexión admin verificada.");
      await Promise.all([
        loadOverview({ silent: true, rethrow: true }),
        loadUsers({ silent: true, rethrow: true }),
      ]);
    } catch (e) {
      setAuthOk(false);
      setOverview(null);
      setUsers(null);
      setErr(e.message);
    } finally {
      setAuthLoading(false);
    }
  };

  useEffect(() => {
    if (!authOk || !overview?.analysis_job_busy) return undefined;
    const id = setInterval(() => {
      loadOverview({ silent: true });
    }, 4000);
    return () => clearInterval(id);
  }, [authOk, overview?.analysis_job_busy, token]);

  const forceAnalysis = async () => {
    if (!window.confirm("¿Ejecutar análisis completo ahora? Puede tardar varios minutos y consumir cuota de APIs externas.")) return;
    setBusy(true);
    setErr(null);
    try {
      const res = await fetch(`${API_BASE}/api/admin/analysis/run`, { method: "POST", headers: authHeaders() });
      const j = await res.json();
      if (!res.ok) throw new Error(typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail));
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
      const res = await fetch(`${API_BASE}/api/admin/telegram/publish`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify(
          mode === "custom"
            ? { mode: "custom", text: customTg }
            : { mode: "summary", text: "" }
        ),
      });
      const j = await res.json();
      if (!res.ok) throw new Error(typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail));
      setMsg(`Telegram: enviado (${j.parts_sent || 1} parte(s)).`);
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
      const res = await fetch(`${API_BASE}/api/admin/premium`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({
          user_id: uid,
          days: Math.min(3650, Math.max(1, Number(days) || 30)),
          username: username.trim(),
        }),
      });
      const j = await res.json();
      if (!res.ok) throw new Error(typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail));
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
      const res = await fetch(`${API_BASE}/api/admin/premium/revoke`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ user_id: uid }),
      });
      const j = await res.json();
      if (!res.ok) throw new Error(typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail));
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
      const res = await fetch(`${API_BASE}/api/admin/users/line-alerts`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ user_id: uid, enabled }),
      });
      const j = await res.json();
      if (!res.ok) throw new Error(typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail));
      setMsg(`Alertas de cuota ${enabled ? "activadas" : "desactivadas"} para ${j.user_id}.`);
      await loadUsers({ silent: true });
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

  if (stLoading) return <Spinner />;
  if (!status?.admin_enabled) {
    return (
      <div className="bg-amber-900/20 border border-amber-700/40 rounded-xl p-4 space-y-2">
        <p className="text-amber-200 text-sm font-semibold">Panel admin desactivado</p>
        <p className="text-gray-400 text-xs">
          En el servidor (Railway o local), define la variable de entorno{" "}
          <code className="text-amber-300">ADMIN_TOKEN</code> con una contraseña larga y secreta. Reinicia el servicio y vuelve aquí.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-gray-700 bg-gradient-to-br from-gray-800 to-gray-900 p-5">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-blue-400 text-xs font-semibold tracking-[0.18em] uppercase">Control Center</p>
            <h2 className="text-white text-2xl font-bold mt-1">Dashboard administrativo</h2>
            <p className="text-gray-400 text-sm mt-2 max-w-3xl">
              Centro operativo para autenticación, control del motor, automatización editorial de Telegram/canal y gestión de usuarios premium.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className={`px-2.5 py-1 rounded-full text-xs font-semibold ${authOk ? "bg-green-900/30 text-green-300" : "bg-gray-700 text-gray-300"}`}>
              {authOk ? "Token validado" : "Sin validar"}
            </span>
            {overview?.analysis_job_busy && (
              <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-900/30 text-amber-300">
                Job en curso
              </span>
            )}
          </div>
        </div>

        <div className="grid lg:grid-cols-[1fr,auto] gap-3 mt-5">
          <div>
            <label className="text-xs text-gray-400">Token admin</label>
            <input
              type="password"
              value={token}
              onChange={(e) => persistToken(e.target.value)}
              placeholder='Pega el token. Si viene como "1234" o “1234”, lo limpiamos.'
              className="w-full mt-1 bg-gray-900 border border-gray-600 rounded-xl px-3 py-3 text-sm text-white"
            />
            <p className="text-gray-500 text-xs mt-2">
              El cliente limpia espacios, saltos de línea y comillas externas automáticamente antes de enviar el header.
            </p>
          </div>
          <div className="flex lg:flex-col gap-2 lg:w-56">
            <button
              type="button"
              onClick={connectAdmin}
              disabled={!token || authLoading}
              className="flex-1 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white py-3 rounded-xl text-sm font-semibold"
            >
              {authLoading ? "Validando…" : "Conectar panel"}
            </button>
            <button
              type="button"
              onClick={() => Promise.all([loadOverview(), loadUsers()])}
              disabled={!token || ovLoading || busy}
              className="flex-1 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 text-white py-3 rounded-xl text-sm"
            >
              Refrescar datos
            </button>
          </div>
        </div>
      </div>

      {overview && (
        <div className="space-y-3">
          <div className="grid md:grid-cols-2 xl:grid-cols-5 gap-3">
            <QuickInsight label="Usuarios" value={overview.users?.total ?? 0} hint={`${overview.users?.premium ?? 0} premium · ${overview.users?.free ?? 0} free`} />
            <QuickInsight label="Partidos en caché" value={overview.live?.matches_analyzed ?? 0} hint={`${overview.live?.with_value ?? 0} con valor EV+`} />
            <QuickInsight
              label="Estado job"
              value={overview.analysis_job?.status || "idle"}
              hint={
                overview.analysis_job?.error
                  || (overview.analysis_job?.runtime_owner
                    ? `Owner ${overview.analysis_job.runtime_owner} · inicio ${fmtTimeOnly(overview.analysis_job?.runtime_started_at)}`
                    : `Última ejecución: ${fmtTimeOnly(overview.live?.last_run)}`)
              }
            />
            <QuickInsight label="Tracker" value={overview.tracker?.total_bets ?? 0} hint={`ROI ${overview.tracker?.roi_pct ?? "—"}% · P&L ${overview.tracker?.pnl_units ?? "—"}u`} />
            <QuickInsight
              label="Canal"
              value={overview.live?.last_publish_kind || "sin post"}
              hint={overview.live?.last_publish_utc ? `Último ${fmtDateTime(overview.live?.last_publish_utc)}` : "Aún no hay publicaciones registradas"}
            />
          </div>

          <div className="grid xl:grid-cols-[1.05fr,0.95fr] gap-4">
            <div className="rounded-2xl border border-gray-700 bg-gray-800/85 p-5">
              <SectionTitle
                eyebrow="Servidor"
                title="Estado operativo"
                subtitle="Lo que está corriendo ahora mismo en la instancia y la configuración efectiva cargada desde Railway/.env."
              />
              <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3 mt-5 text-sm">
                <div className="rounded-xl bg-gray-900/70 p-4">
                  <p className="text-gray-500 text-xs">Hora servidor</p>
                  <p className="text-white font-semibold mt-1">{fmtDateTime(overview.server?.time_utc)}</p>
                </div>
                <div className="rounded-xl bg-gray-900/70 p-4">
                  <p className="text-gray-500 text-xs">Próxima pasada</p>
                  <p className="text-white font-semibold mt-1">{fmtDateTime(overview.server?.next_run_utc)}</p>
                </div>
                <div className="rounded-xl bg-gray-900/70 p-4">
                  <p className="text-gray-500 text-xs">Horarios UTC</p>
                  <p className="text-white font-semibold mt-1">{overview.config?.report_hours_utc?.join(", ") || "—"}</p>
                </div>
                <div className="rounded-xl bg-gray-900/70 p-4">
                  <p className="text-gray-500 text-xs">Odds API regions</p>
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
                <p className="text-white font-semibold text-sm">Configuración activa</p>
                <p className="text-gray-400 text-xs mt-2">
                  Hero liga ID: <span className="text-gray-200">{overview.config?.hero_league_id}</span>
                  {" · "}Top destacados: <span className="text-gray-200">{overview.config?.highlight_top_n}</span>
                </p>
                <p className="text-gray-400 text-xs mt-2">
                  Ligas: {overview.config?.target_leagues?.map((l) => `${l.name} (${l.id})`).join(" · ")}
                </p>
                <p className="text-gray-400 text-xs mt-2">
                  Alertas de cuota: cada {Math.round((overview.config?.line_move_poll_interval_sec ?? 0) / 60) || 0} min
                  {" · "}Último publish: {overview.live?.last_publish_utc ? fmtDateTime(overview.live?.last_publish_utc) : "sin registro"}
                </p>
                <p className="text-amber-300 text-xs mt-3">
                  Cambiar ligas, horarios o regiones sigue siendo una tarea de Railway/.env + redeploy.
                </p>
              </div>
            </div>

            <div className="rounded-2xl border border-gray-700 bg-gray-800/85 p-5">
              <SectionTitle
                eyebrow="Acciones"
                title="Control del motor y publicación"
                subtitle="Acciones operativas inmediatas sobre el pipeline y los canales de salida."
              />
              <div className="space-y-3 mt-5">
                <button
                  type="button"
                  onClick={forceAnalysis}
                  disabled={busy || !token}
                  className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white py-3 rounded-xl text-sm font-semibold"
                >
                  Forzar análisis completo ahora
                </button>
                <button
                  type="button"
                  onClick={() => publishTelegram("summary")}
                  disabled={busy || !token}
                  className="w-full bg-sky-700 hover:bg-sky-600 disabled:opacity-50 text-white py-3 rounded-xl text-sm font-semibold"
                >
                  Publicar boletín actual en Telegram
                </button>
                <textarea
                  value={customTg}
                  onChange={(e) => setCustomTg(e.target.value)}
                  placeholder="Mensaje custom para Telegram (HTML permitido)…"
                  rows={4}
                  className="w-full bg-gray-900 border border-gray-600 rounded-xl px-3 py-3 text-sm text-white"
                />
                <button
                  type="button"
                  onClick={() => publishTelegram("custom")}
                  disabled={busy || !token || !customTg.trim()}
                  className="w-full bg-sky-900 hover:bg-sky-800 disabled:opacity-50 text-white py-3 rounded-xl text-sm"
                >
                  Enviar mensaje custom
                </button>
              </div>
              <div className="mt-4 rounded-2xl border border-gray-700 bg-gray-900/60 p-4">
                <p className="text-white text-sm font-semibold">Integraciones</p>
                <p className="text-gray-400 text-xs mt-2">
                  Telegram token: {overview.integrations?.telegram_token_set ? "✅ configurado" : "❌ ausente"}
                </p>
                <p className="text-gray-400 text-xs mt-1">
                  Chat/canal destino: {overview.integrations?.telegram_chat_id_set ? "✅ TELEGRAM_CHAT_ID listo" : "❌ falta TELEGRAM_CHAT_ID"}
                </p>
                <p className="text-gray-400 text-xs mt-1">
                  Último destino publicado: {overview.live?.last_publish_target || "sin actividad"}
                </p>
              </div>
            </div>
          </div>

          <div className="grid xl:grid-cols-[1fr,1fr] gap-4">
            <div className="rounded-2xl border border-gray-700 bg-gray-800/85 p-5">
              <SectionTitle
                eyebrow="Radar admin"
                title="Destacados en memoria"
                subtitle="Partidos más importantes del ciclo actual, útiles para revisión rápida y publicación."
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
                title="Señales recientes del tracker"
                subtitle="Últimos partidos registrados por la capa histórica."
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
            subtitle="El identificador fiable es el user ID numérico de Telegram. Puedes añadir días y extender vencimientos existentes."
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
              disabled={busy || !token}
              className="flex-1 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white py-3 rounded-xl text-sm font-semibold"
            >
              Guardar / extender Premium
            </button>
            <button
              type="button"
              onClick={() => loadUsers()}
              disabled={busy || !token}
              className="px-4 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 text-white py-3 rounded-xl text-sm"
            >
              Recargar
            </button>
          </div>
        </form>

        <div className="rounded-2xl border border-gray-700 bg-gray-800/85 p-5">
          <SectionTitle
            eyebrow="Base de usuarios"
            title="Gestión de planes y alertas"
            subtitle="Vista operativa de usuarios, vencimientos, actividad y control de alertas premium."
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
                          {u.is_premium ? "💎 Premium" : "🆓 Free"}
                        </p>
                        <p className="text-gray-500 text-[11px] mt-1">
                          Vence: {u.premium_until ? fmtDateTime(u.premium_until) : "—"}
                        </p>
                        <p className="text-gray-500 text-[11px] mt-1">
                          Line alerts: {u.notify_line_moves ? "✅ activas" : "—"}
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
                            disabled={busy || !token}
                            className="text-xs text-sky-300 hover:text-white"
                          >
                            {u.notify_line_moves ? "Desactivar line alerts" : "Activar line alerts"}
                          </button>
                          {u.is_premium && (
                            <button
                              type="button"
                              onClick={() => revokePremium(u.user_id)}
                              disabled={busy || !token}
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
              Conecta el panel y recarga usuarios para ver la base actual.
            </p>
          )}
        </div>
      </div>

      {err && <ErrorBox msg={err} />}
      {msg && (
        <div className="bg-green-900/30 border border-green-700/40 rounded-xl p-3 text-green-200 text-sm">{msg}</div>
      )}
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
    { icon: "⚖️", title: "Consenso", desc: "Combina las 5 capas con pesos. Detecta value bets donde EV > 3%." },
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
        <h3 className="text-blue-400 font-semibold mb-2">¿Qué es un value bet?</h3>
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
  const { data: stats, loading: statsLoading } = useFetch("/api/stats", []);
  const { data: btData } = useFetch("/api/backtest", []);
  const { data: liveOverview } = useFetch("/api/analysis/live", []);

  const tabs = [
    { id: "inicio",    label: "Inicio",      icon: Award },
    { id: "hoy",       label: "Hoy",         icon: Zap },
    { id: "historial", label: "Historial",    icon: BarChart2 },
    { id: "calibracion", label: "Calibración", icon: Target },
    { id: "admin",     label: "Admin",       icon: Settings },
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
                Plataforma de inteligencia futbolística · análisis centralizado · portada ejecutiva
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className={`text-xs px-2 py-0.5 rounded-full ${stats ? "bg-green-900/40 text-green-400" : "bg-gray-700 text-gray-400"}`}>
              {stats ? "🟢 API conectada" : "⚪ Cargando…"}
            </span>
            <span className="text-xs px-2 py-0.5 rounded-full bg-gray-800 text-gray-300 border border-gray-700">
              Última pasada: {fmtTimeOnly(liveOverview?.last_run)} UTC
            </span>
            <span className="text-xs px-2 py-0.5 rounded-full bg-gray-800 text-gray-300 border border-gray-700">
              EV+ hoy: {liveOverview?.total_value_bets ?? 0}
            </span>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-5 space-y-5">
        {/* Stats */}
        <div className="grid md:grid-cols-2 xl:grid-cols-4 gap-3">
          <StatCard
            icon={TrendingUp} label="ROI acumulado"
            value={stats ? `${stats.roi_pct >= 0 ? "+" : ""}${stats.roi_pct}%` : "—"}
            sub={stats ? `${stats.won}✅ ${stats.lost}❌ ${stats.pending || 0}⏳` : ""}
            color="bg-green-600" loading={statsLoading}
          />
          <StatCard
            icon={Target} label="Win rate"
            value={stats ? pct(stats.hit_rate) : "—"}
            sub={stats ? `P&L: ${stats.pnl_units >= 0 ? "+" : ""}${stats.pnl_units}u` : ""}
            color="bg-blue-600" loading={statsLoading}
          />
          <StatCard
            icon={Zap} label="Señales EV+"
            value={liveOverview ? `${liveOverview.total_value_bets || 0}` : "—"}
            sub={liveOverview ? `${liveOverview.count || 0} partidos monitorizados` : ""}
            color="bg-indigo-600" loading={!liveOverview}
          />
          <StatCard
            icon={Activity} label="Pasadas hoy"
            value={liveOverview ? `${liveOverview.runs_today || 0}` : "—"}
            sub={liveOverview ? `Próxima: ${fmtTimeOnly(liveOverview.next_run_utc)} UTC` : ""}
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
        {tab === "admin"       && <TabAdmin />}
        {tab === "como"        && <TabHowItWorks />}

        {/* CTA Telegram */}
        <div className="bg-gradient-to-r from-blue-900/50 to-indigo-900/50 border border-blue-700/40 rounded-xl p-4 text-center">
          <p className="text-white font-semibold mb-1">📱 Recibe alertas en Telegram</p>
          <p className="text-gray-400 text-sm mb-3">
            Value bets automáticas · alertas steam/reverse · bankroll personal · publicación operativa
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

        <ProfessionalFooter live={liveOverview} />
      </main>
    </div>
  );
}
