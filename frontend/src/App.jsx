import React, { useState } from "react";
import {
  TrendingUp, TrendingDown, Target, Zap, ChevronRight,
  BarChart2, Clock, Star, Shield, Activity, ChevronDown,
  Twitter, Send, Globe
} from "lucide-react";

// ── Datos demo ──────────────────────────────────────────────────────────────
const DEMO_STATS = {
  roi: "+14.2%",
  winRate: "58%",
  pnl: "+42.8u",
  signals: 7,
  weeklyPnl: [1.2, -0.5, 2.1, 0.8, -0.3, 1.9, 1.4],
};

const DEMO_MATCHES = [
  {
    id: 1,
    home: "Arsenal",
    away: "Liverpool",
    league: "🏴 Premier League",
    time: "21:00",
    date: "Hoy",
    consensus: { home: 0.46, draw: 0.27, away: 0.27 },
    ou: { over: 0.64, under: 0.36 },
    valueBets: [
      { market: "O/U 2.5", label: "Over 2.5", odds: 1.82, value: 0.072, bookmaker: "Pinnacle" },
      { market: "1X2", label: "✈️ Liverpool", odds: 3.40, value: 0.041, bookmaker: "Bet365" },
    ],
    poisson: { xg_home: 1.62, xg_away: 1.41, top_score: "2-1" },
    confidence: 0.74,
    agreement: 0.80,
    ai: "Arsenal en casa con buena racha pero Liverpool llega con 5 victorias. Derbi abierto con alta intensidad esperada.",
  },
  {
    id: 2,
    home: "Barcelona",
    away: "Atlético Madrid",
    league: "🇪🇸 La Liga",
    time: "20:00",
    date: "Hoy",
    consensus: { home: 0.50, draw: 0.25, away: 0.25 },
    ou: { over: 0.58, under: 0.42 },
    valueBets: [
      { market: "1X2", label: "🏠 Barcelona", odds: 2.10, value: 0.051, bookmaker: "Pinnacle" },
    ],
    poisson: { xg_home: 1.78, xg_away: 1.12, top_score: "2-0" },
    confidence: 0.71,
    agreement: 0.75,
    ai: "Barça dominante en casa. Atlético potente en defensa pero le cuesta fuera. Partido táctico.",
  },
  {
    id: 3,
    home: "Bayern Munich",
    away: "Dortmund",
    league: "🇩🇪 Bundesliga",
    time: "18:30",
    date: "Hoy",
    consensus: { home: 0.52, draw: 0.23, away: 0.25 },
    ou: { over: 0.71, under: 0.29 },
    valueBets: [
      { market: "O/U 2.5", label: "Over 2.5", odds: 1.65, value: 0.038, bookmaker: "Betfair" },
      { market: "O/U 2.5", label: "Over 2.5 @3.5", odds: 2.10, value: 0.062, bookmaker: "Pinnacle" },
    ],
    poisson: { xg_home: 2.10, xg_away: 1.65, top_score: "2-1" },
    confidence: 0.78,
    agreement: 0.85,
    ai: "Der Klassiker. Ambos equipos con ataque top. Historial reciente apunta a partidos con más de 3 goles.",
  },
];

const HISTORY = [
  { date: "28/03", match: "Man City vs Chelsea", bet: "Over 2.5", odds: 1.72, result: "✅ Won", pnl: "+0.72" },
  { date: "27/03", match: "Real Madrid vs Sevilla", bet: "Local 1X2", odds: 1.55, result: "✅ Won", pnl: "+0.55" },
  { date: "26/03", match: "PSG vs Monaco", bet: "Over 2.5", odds: 1.88, result: "❌ Lost", pnl: "-1.00" },
  { date: "25/03", match: "Inter vs Napoli", bet: "Under 2.5", odds: 2.05, result: "✅ Won", pnl: "+1.05" },
  { date: "24/03", match: "Juventus vs Roma", bet: "Over 2.5", odds: 1.78, result: "✅ Won", pnl: "+0.78" },
];

// ── Componentes ──────────────────────────────────────────────────────────────

function StatCard({ icon: Icon, label, value, sub, color }) {
  return (
    <div className="bg-gray-800 rounded-xl p-4 flex items-center gap-4 border border-gray-700">
      <div className={`p-3 rounded-lg ${color}`}>
        <Icon size={20} className="text-white" />
      </div>
      <div>
        <p className="text-gray-400 text-xs">{label}</p>
        <p className="text-white text-xl font-bold">{value}</p>
        {sub && <p className="text-gray-500 text-xs">{sub}</p>}
      </div>
    </div>
  );
}

function ValueBadge({ value }) {
  const pct = (value * 100).toFixed(1);
  const color = value >= 0.07 ? "bg-green-500" : value >= 0.04 ? "bg-yellow-500" : "bg-blue-500";
  return (
    <span className={`${color} text-white text-xs font-bold px-2 py-0.5 rounded-full`}>
      +{pct}%
    </span>
  );
}

function WeeklyChart({ data }) {
  const max = Math.max(...data.map(Math.abs));
  return (
    <div className="flex items-end gap-1 h-12">
      {data.map((v, i) => {
        const h = Math.round((Math.abs(v) / max) * 40) + 4;
        return (
          <div
            key={i}
            className={`flex-1 rounded-sm ${v >= 0 ? "bg-green-500" : "bg-red-500"}`}
            style={{ height: h }}
            title={`${v >= 0 ? "+" : ""}${v}u`}
          />
        );
      })}
    </div>
  );
}

function MatchCard({ match, onSelect }) {
  const topVb = match.valueBets[0];
  return (
    <div
      className="bg-gray-800 border border-gray-700 rounded-xl p-4 cursor-pointer hover:border-blue-500 transition-all"
      onClick={() => onSelect(match)}
    >
      <div className="flex justify-between items-start mb-2">
        <div>
          <p className="text-xs text-gray-400">{match.league} · {match.date} {match.time}</p>
          <p className="text-white font-bold">{match.home} <span className="text-gray-400">vs</span> {match.away}</p>
        </div>
        <div className="text-right">
          <p className="text-xs text-gray-400">Confianza</p>
          <p className="text-green-400 font-bold">{(match.confidence * 100).toFixed(0)}%</p>
        </div>
      </div>

      {/* Barras de probabilidad 1X2 */}
      <div className="flex gap-1 h-2 rounded-full overflow-hidden my-3">
        <div className="bg-blue-500 rounded-l-full" style={{ width: `${match.consensus.home * 100}%` }} />
        <div className="bg-gray-500" style={{ width: `${match.consensus.draw * 100}%` }} />
        <div className="bg-red-500 rounded-r-full" style={{ width: `${match.consensus.away * 100}%` }} />
      </div>
      <div className="flex justify-between text-xs text-gray-400 mb-3">
        <span>🏠 {(match.consensus.home * 100).toFixed(0)}%</span>
        <span>🤝 {(match.consensus.draw * 100).toFixed(0)}%</span>
        <span>✈️ {(match.consensus.away * 100).toFixed(0)}%</span>
      </div>

      {/* Value bets */}
      {match.valueBets.length > 0 && (
        <div className="border-t border-gray-700 pt-3 flex items-center justify-between">
          <div>
            <p className="text-xs text-gray-400">{topVb.market} · {topVb.label}</p>
            <p className="text-white font-semibold">@ {topVb.odds} <span className="text-gray-400 text-xs">({topVb.bookmaker})</span></p>
          </div>
          <div className="flex items-center gap-2">
            <ValueBadge value={topVb.value} />
            {match.valueBets.length > 1 && (
              <span className="text-xs text-gray-500">+{match.valueBets.length - 1} más</span>
            )}
            <ChevronRight size={16} className="text-gray-500" />
          </div>
        </div>
      )}
    </div>
  );
}

function MatchDetail({ match, onBack }) {
  return (
    <div className="space-y-4">
      <button
        onClick={onBack}
        className="flex items-center gap-1 text-blue-400 text-sm hover:text-blue-300"
      >
        ← Volver
      </button>

      <div className="bg-gray-800 rounded-xl p-5 border border-gray-700">
        <p className="text-xs text-gray-400 mb-1">{match.league}</p>
        <h2 className="text-xl font-bold text-white mb-1">
          {match.home} vs {match.away}
        </h2>
        <p className="text-gray-400 text-sm">{match.date} · {match.time}</p>
      </div>

      {/* Probabilidades */}
      <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
        <h3 className="text-gray-300 font-semibold mb-3">📊 Resultado (1X2)</h3>
        <div className="grid grid-cols-3 gap-3 text-center">
          {[
            { label: "🏠 " + match.home, key: "home" },
            { label: "🤝 Empate", key: "draw" },
            { label: "✈️ " + match.away, key: "away" },
          ].map(({ label, key }) => (
            <div key={key} className="bg-gray-700 rounded-lg p-3">
              <p className="text-xs text-gray-400">{label}</p>
              <p className="text-white text-lg font-bold">{(match.consensus[key] * 100).toFixed(1)}%</p>
              <p className="text-gray-400 text-xs">
                cuota justa: {(1 / match.consensus[key]).toFixed(2)}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* Over/Under */}
      <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
        <h3 className="text-gray-300 font-semibold mb-3">⚽ Goles (O/U 2.5)</h3>
        <div className="flex gap-3">
          <div className="flex-1 bg-gray-700 rounded-lg p-3 text-center">
            <p className="text-xs text-gray-400">⬆️ Over</p>
            <p className="text-white text-lg font-bold">{(match.ou.over * 100).toFixed(1)}%</p>
          </div>
          <div className="flex-1 bg-gray-700 rounded-lg p-3 text-center">
            <p className="text-xs text-gray-400">⬇️ Under</p>
            <p className="text-white text-lg font-bold">{(match.ou.under * 100).toFixed(1)}%</p>
          </div>
        </div>
        <p className="text-xs text-gray-500 mt-2">
          🎯 Score más probable: <strong className="text-white">{match.poisson.top_score}</strong>
          &nbsp;· xG: {match.poisson.xg_home} – {match.poisson.xg_away}
        </p>
      </div>

      {/* Value Bets */}
      <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
        <h3 className="text-gray-300 font-semibold mb-3">🔥 Value Bets</h3>
        <div className="space-y-3">
          {match.valueBets.map((vb, i) => (
            <div key={i} className="bg-gray-700 rounded-lg p-3 flex items-center justify-between">
              <div>
                <p className="text-xs text-gray-400">{vb.market}</p>
                <p className="text-white font-semibold">{vb.label}</p>
                <p className="text-gray-400 text-xs">@ {vb.odds} · {vb.bookmaker}</p>
              </div>
              <ValueBadge value={vb.value} />
            </div>
          ))}
        </div>
      </div>

      {/* AI */}
      {match.ai && (
        <div className="bg-blue-900/30 border border-blue-700/40 rounded-xl p-4">
          <p className="text-xs text-blue-400 mb-1">🧠 Análisis IA (DeepSeek)</p>
          <p className="text-gray-300 text-sm italic">{match.ai}</p>
        </div>
      )}

      {/* Confianza */}
      <div className="bg-gray-800 rounded-xl p-3 border border-gray-700 flex justify-around text-center">
        <div>
          <p className="text-xs text-gray-400">Confianza</p>
          <p className="text-green-400 font-bold">{(match.confidence * 100).toFixed(0)}%</p>
        </div>
        <div>
          <p className="text-xs text-gray-400">Acuerdo modelos</p>
          <p className="text-blue-400 font-bold">{(match.agreement * 100).toFixed(0)}%</p>
        </div>
        <div>
          <p className="text-xs text-gray-400">Value bets</p>
          <p className="text-yellow-400 font-bold">{match.valueBets.length}</p>
        </div>
      </div>

      <p className="text-center text-gray-500 text-xs">
        ⚠️ Análisis estadístico. No es consejo financiero.
      </p>
    </div>
  );
}

function TabToday({ matches }) {
  const [selected, setSelected] = useState(null);

  if (selected) {
    return <MatchDetail match={selected} onBack={() => setSelected(null)} />;
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between mb-1">
        <p className="text-gray-400 text-sm">{matches.length} partidos con valor hoy</p>
        <span className="text-xs bg-green-900/40 text-green-400 px-2 py-0.5 rounded-full">
          🟢 En vivo
        </span>
      </div>
      {matches.map((m) => (
        <MatchCard key={m.id} match={m} onSelect={setSelected} />
      ))}
    </div>
  );
}

function TabHistory() {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-3 mb-2">
        <div className="bg-gray-800 rounded-lg p-3 text-center border border-gray-700">
          <p className="text-xs text-gray-400">Hit rate</p>
          <p className="text-green-400 font-bold text-lg">58%</p>
        </div>
        <div className="bg-gray-800 rounded-lg p-3 text-center border border-gray-700">
          <p className="text-xs text-gray-400">ROI</p>
          <p className="text-green-400 font-bold text-lg">+14.2%</p>
        </div>
        <div className="bg-gray-800 rounded-lg p-3 text-center border border-gray-700">
          <p className="text-xs text-gray-400">P&L</p>
          <p className="text-green-400 font-bold text-lg">+42.8u</p>
        </div>
      </div>
      <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-700 text-gray-400 text-xs">
              <th className="p-3 text-left">Partido</th>
              <th className="p-2 text-center">Apuesta</th>
              <th className="p-2 text-center">P&L</th>
            </tr>
          </thead>
          <tbody>
            {HISTORY.map((h, i) => (
              <tr key={i} className="border-b border-gray-700/50 hover:bg-gray-700/30">
                <td className="p-3">
                  <p className="text-white text-xs font-medium">{h.match}</p>
                  <p className="text-gray-500 text-xs">{h.date}</p>
                </td>
                <td className="p-2 text-center">
                  <p className="text-gray-300 text-xs">{h.bet}</p>
                  <p className="text-gray-400 text-xs">@ {h.odds}</p>
                </td>
                <td className="p-2 text-center">
                  <p className={`font-bold text-xs ${h.pnl.startsWith("+") ? "text-green-400" : "text-red-400"}`}>
                    {h.result}
                  </p>
                  <p className={`text-xs ${h.pnl.startsWith("+") ? "text-green-400" : "text-red-400"}`}>
                    {h.pnl}u
                  </p>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TabHowItWorks() {
  const layers = [
    { n: "1", icon: "📈", title: "Mercado (35%)", desc: "Analiza cuotas de +10 casas. Usa Pinnacle como línea sharp para eliminar el margen y obtener probabilidades reales." },
    { n: "2", icon: "🎲", title: "Poisson (25%)", desc: "Calcula xG desde estadísticas reales de la temporada. Genera matriz de resultados para 1X2, O/U 2.5 y BTTS." },
    { n: "3", icon: "📊", title: "ELO (15%)", desc: "Rating dinámico pre-cargado desde la tabla de posiciones actual. Se actualiza con cada resultado." },
    { n: "4", icon: "🔍", title: "Features (15%)", desc: "Forma de los últimos 5 partidos, tendencia de goles, rachas activas y head-to-head reciente." },
    { n: "5", icon: "🧠", title: "DeepSeek IA (10%)", desc: "Analiza lesiones, motivación y contexto. Ajusta ±5% las probabilidades del consenso. ~$0.01/partido." },
    { n: "6", icon: "⚖️", title: "Consenso", desc: "Combina las 5 capas con pesos. Detecta value bets donde nuestra probabilidad > cuota ofrecida (en valor esperado)." },
  ];

  const filters = [
    "Valor esperado > 3%",
    "Mínimo 5 bookmakers en el mercado",
    "Confianza del consenso > 60%",
    "Acuerdo entre modelos > 66%",
    "Cuota entre 1.30 y 8.00",
  ];

  return (
    <div className="space-y-4">
      <div className="bg-blue-900/20 border border-blue-700/30 rounded-xl p-4">
        <h3 className="text-blue-400 font-semibold mb-2">¿Qué es un value bet?</h3>
        <p className="text-gray-300 text-sm">
          Una apuesta con <strong>valor positivo</strong> ocurre cuando la probabilidad real del evento
          es mayor a la implícita en la cuota. A largo plazo, apostar con valor positivo genera beneficio.
        </p>
      </div>

      <div className="space-y-2">
        {layers.map((l) => (
          <div key={l.n} className="bg-gray-800 rounded-xl p-4 border border-gray-700 flex gap-3">
            <div className="text-2xl">{l.icon}</div>
            <div>
              <p className="text-white font-semibold text-sm">Capa {l.n}: {l.title}</p>
              <p className="text-gray-400 text-xs mt-0.5">{l.desc}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
        <h3 className="text-gray-300 font-semibold mb-2">✅ Filtros de calidad</h3>
        <ul className="space-y-1">
          {filters.map((f, i) => (
            <li key={i} className="text-gray-400 text-sm flex items-center gap-2">
              <span className="text-green-500">✓</span> {f}
            </li>
          ))}
        </ul>
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

  const tabs = [
    { id: "hoy", label: "Hoy", icon: Zap },
    { id: "historial", label: "Historial", icon: BarChart2 },
    { id: "como", label: "Cómo funciona", icon: Shield },
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
          <div className="flex items-center gap-1 text-xs text-gray-400">
            <Activity size={12} className="text-green-400" />
            <span>6 capas · DeepSeek IA</span>
          </div>
        </div>
      </header>

      <main className="max-w-lg mx-auto px-4 py-4 space-y-4">
        {/* Stats rápidos */}
        <div className="grid grid-cols-2 gap-3">
          <StatCard icon={TrendingUp} label="ROI acumulado" value={DEMO_STATS.roi} sub="últimos 30 días" color="bg-green-600" />
          <StatCard icon={Target} label="Win rate" value={DEMO_STATS.winRate} sub={`P&L: ${DEMO_STATS.pnl}`} color="bg-blue-600" />
        </div>

        {/* Gráfico semanal */}
        <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
          <div className="flex justify-between items-center mb-3">
            <p className="text-gray-300 text-sm font-semibold">P&L esta semana</p>
            <p className="text-green-400 text-sm font-bold">+6.6u</p>
          </div>
          <WeeklyChart data={DEMO_STATS.weeklyPnl} />
          <div className="flex justify-between text-xs text-gray-500 mt-1">
            {["L", "M", "X", "J", "V", "S", "D"].map((d) => (
              <span key={d}>{d}</span>
            ))}
          </div>
        </div>

        {/* Tabs */}
        <div className="flex bg-gray-800 rounded-xl p-1 border border-gray-700">
          {tabs.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-sm transition-all ${
                tab === id
                  ? "bg-blue-600 text-white font-semibold"
                  : "text-gray-400 hover:text-gray-200"
              }`}
            >
              <Icon size={14} />
              <span className="hidden sm:inline">{label}</span>
            </button>
          ))}
        </div>

        {/* Contenido del tab */}
        {tab === "hoy" && <TabToday matches={DEMO_MATCHES} />}
        {tab === "historial" && <TabHistory />}
        {tab === "como" && <TabHowItWorks />}

        {/* CTA Telegram */}
        <div className="bg-gradient-to-r from-blue-900/50 to-indigo-900/50 border border-blue-700/40 rounded-xl p-4 text-center">
          <p className="text-white font-semibold mb-1">📱 Recibe alertas en Telegram</p>
          <p className="text-gray-400 text-sm mb-3">
            Value bets automáticas 2 veces al día. Bot gratuito.
          </p>
          <div className="flex gap-2 justify-center">
            <a
              href="https://t.me/valuexpro_bot"
              className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-lg text-sm font-semibold transition-colors"
            >
              <Send size={14} /> Abrir Bot
            </a>
            <a
              href="https://t.me/valuexpro"
              className="flex items-center gap-2 bg-gray-700 hover:bg-gray-600 text-white px-4 py-2 rounded-lg text-sm transition-colors"
            >
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
