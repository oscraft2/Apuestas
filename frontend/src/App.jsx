import React, { useState, useEffect, useCallback } from "react";
import {
  TrendingUp, Target, Zap, BarChart2, Shield,
  Activity, RefreshCw, AlertTriangle, ChevronRight,
  Send, Globe, Award, BookOpen, Brain, Wallet,
} from "lucide-react";

const API_BASE = process.env.REACT_APP_API_URL || "http://localhost:8000";

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
  const { data, loading, error, reload } = useFetch("/bets/today", []);
  const [selected, setSelected] = useState(null);

  if (selected) return <BetDetail bet={selected} onBack={() => setSelected(null)} />;
  if (loading) return <Spinner />;
  if (error) return <ErrorBox msg={error} onRetry={reload} />;

  const bets = data?.bets || [];
  const withValue = bets.filter(b => b.value_bets?.length > 0);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-gray-400 text-sm">{withValue.length} partidos con valor hoy</p>
        <button onClick={reload} className="text-gray-400 hover:text-white">
          <RefreshCw size={14} />
        </button>
      </div>
      {withValue.length === 0
        ? <div className="bg-gray-800 rounded-xl p-6 text-center border border-gray-700">
            <p className="text-gray-400">No hay value bets registradas hoy.</p>
            <p className="text-gray-500 text-sm mt-1">El mercado está eficiente hoy o el bot aún no ha corrido.</p>
          </div>
        : withValue.map((b, i) => <BetCard key={i} bet={b} onSelect={setSelected} />)
      }
    </div>
  );
}

// ── Tab: Historial ────────────────────────────────────────────────────────────

function TabHistory() {
  const { data: stats, loading: ls } = useFetch("/stats", []);
  const { data: recent, loading: lr } = useFetch("/bets/recent?n=30", []);
  const { data: bt } = useFetch("/backtest", []);

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
  const { data, loading, error, reload } = useFetch("/calibration", []);

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
  const [tab, setTab] = useState("hoy");
  const { data: stats, loading: statsLoading } = useFetch("/stats", []);
  const { data: btData } = useFetch("/backtest", []);

  const tabs = [
    { id: "hoy",       label: "Hoy",         icon: Zap },
    { id: "historial", label: "Historial",    icon: BarChart2 },
    { id: "calibracion", label: "Calibración", icon: Target },
    { id: "como",      label: "Cómo funciona", icon: Shield },
  ];

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      {/* Header */}
      <header className="bg-gray-800 border-b border-gray-700 sticky top-0 z-10">
        <div className="max-w-lg mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="bg-blue-600 p-1.5 rounded-lg">
              <Target size={16} className="text-white" />
            </div>
            <div>
              <span className="font-bold text-white">ValueX</span>
              <span className="font-bold text-blue-400">Pro</span>
              <span className="ml-2 text-xs bg-blue-900/40 text-blue-400 px-1.5 py-0.5 rounded">V3</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className={`text-xs px-2 py-0.5 rounded-full ${stats ? "bg-green-900/40 text-green-400" : "bg-gray-700 text-gray-400"}`}>
              {stats ? "🟢 API conectada" : "⚪ Cargando…"}
            </span>
          </div>
        </div>
      </header>

      <main className="max-w-lg mx-auto px-4 py-4 space-y-4">
        {/* Stats */}
        <div className="grid grid-cols-2 gap-3">
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
        {tab === "hoy"         && <TabToday />}
        {tab === "historial"   && <TabHistory />}
        {tab === "calibracion" && <TabCalibration />}
        {tab === "como"        && <TabHowItWorks />}

        {/* CTA Telegram */}
        <div className="bg-gradient-to-r from-blue-900/50 to-indigo-900/50 border border-blue-700/40 rounded-xl p-4 text-center">
          <p className="text-white font-semibold mb-1">📱 Recibe alertas en Telegram</p>
          <p className="text-gray-400 text-sm mb-3">Value bets automáticas · Alertas steam/reverse · Bankroll personal</p>
          <div className="flex gap-2 justify-center">
            <a href="https://t.me/valuexpro_bot" className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-lg text-sm font-semibold transition-colors">
              <Send size={14} /> Bot
            </a>
            <a href="https://t.me/valuexpro" className="flex items-center gap-2 bg-gray-700 hover:bg-gray-600 text-white px-4 py-2 rounded-lg text-sm transition-colors">
              <Globe size={14} /> Canal
            </a>
          </div>
        </div>

        <p className="text-center text-gray-600 text-xs pb-4">
          Football Value Bot V3 · Análisis estadístico · No es consejo financiero
        </p>
      </main>
    </div>
  );
}
