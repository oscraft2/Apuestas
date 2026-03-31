"""
Orquestador V3 — Pipeline completo de análisis para un partido
"""
import logging
from datetime import datetime, timezone

from src.models.market import MarketAnalyzer
from src.models.poisson import PoissonModel
from src.models.elo import EloSystem
from src.models.features import FeatureEngine
from src.models.deepseek import DeepSeekReasoner
from src.models.consensus import ConsensusEngine
from src.tracking.tracker import PredictionTracker
from config import config

logger = logging.getLogger(__name__)

# Instancias globales — ELO y tracker persisten entre análisis (fix bug #11)
_elo = EloSystem()
_tracker = PredictionTracker()


class FootballAnalyzerV3:

    def __init__(self):
        self.market = MarketAnalyzer()
        self.poisson = PoissonModel()
        self.elo = _elo          # referencia global, ELO persiste
        self.features = FeatureEngine()
        self.ai = DeepSeekReasoner()
        self.consensus = ConsensusEngine()
        self.tracker = _tracker  # referencia global

    async def analyze(
        self,
        match: dict,
        home_stats: dict = None,
        away_stats: dict = None,
        league_id: int | None = None,
    ) -> dict:
        home = match.get("home_team") or match.get("home_team_name", "?")
        away = match.get("away_team") or match.get("away_team_name", "?")
        bms = match.get("bookmakers", [])

        result = {
            "match_id": match.get("id", ""),
            "home": home,
            "away": away,
            "time": match.get("commence_time", ""),
            "league": match.get("sport_title", ""),
            "league_id": league_id,
        }

        # CAPA 1: Mercado
        h2h_mkt = self.market.analyze_h2h(bms, home, away)
        ou25_mkt = self.market.analyze_totals(bms)
        ou15_mkt = self.market.analyze_total_line(bms, point=1.5)
        btts_mkt = self.market.analyze_btts(bms)
        result["market"] = {
            "h2h": h2h_mkt,
            "ou25": ou25_mkt,
            "ou15": ou15_mkt,
            "btts": btts_mkt,
        }

        market_available = bool(h2h_mkt)
        if market_available:
            # Bug #1: usar is not None para no descartar dicts con valores bajos
            sharp = h2h_mkt.get("sharp_prob")
            mkt_prob = sharp if sharp is not None else h2h_mkt.get("implied_prob", {})
        else:
            mkt_prob = {}

        mkt_ou25 = {"over": ou25_mkt["over_prob"], "under": ou25_mkt["under_prob"]} if ou25_mkt else None
        mkt_ou15 = {"over": ou15_mkt["over_prob"], "under": ou15_mkt["under_prob"]} if ou15_mkt else None
        mkt_btts = {"yes": btts_mkt["yes_prob"], "no": btts_mkt["no_prob"]} if btts_mkt else None

        # CAPA 2: Poisson
        if home_stats and away_stats:
            poi = self.poisson.from_stats(
                home_stats.get("avg_gf", 1.3),
                home_stats.get("avg_ga", 1.0),
                away_stats.get("avg_gf", 1.1),
                away_stats.get("avg_ga", 1.2),
            )
        else:
            # Fallback: derivar xG desde probabilidades de mercado
            mh = mkt_prob.get("home", 0.40)
            ma = mkt_prob.get("away", 0.30)
            # Inversa aproximada: home_win_prob → xG_local (calibrado en ~5000 partidos)
            xh = max(0.5, min(3.5, 1.35 + (mh - 0.40) * 2.5))
            xa = max(0.3, min(3.0, 1.15 + (ma - 0.30) * 2.5))
            poi = self.poisson.predict(xh, xa)

        result["poisson"] = poi
        poi_1x2 = poi["probs_1x2"]
        poi_ou15 = poi["probs_ou15"]
        poi_ou = poi["probs_ou25"]
        poi_btts = poi["btts"]

        # CAPA 3: ELO
        elo_p = self.elo.predict(home, away)
        result["elo"] = elo_p
        elo_1x2 = {k: elo_p[k] for k in ["home", "draw", "away"]}

        # CAPA 4: Features
        feats = None
        feat_1x2 = None
        if home_stats and away_stats:
            feats = self.features.build(home_stats, away_stats)
            result["features"] = feats
            feat_1x2 = feats.get("prob_1x2")

        # Pre-check: ¿el partido ya parece tener valor antes de llamar a la IA?
        # Esto evita gastar cuota de DeepSeek en partidos sin interés.
        _pre_1x2 = self.consensus.combine_1x2(
            {"market": mkt_prob, "poisson": poi_1x2, "elo": elo_1x2, "features": feat_1x2},
            None,
        )
        _pre_vbs = self.consensus.detect_value(
            _pre_1x2.get("probs", {}), h2h_mkt.get("best_odds", {}), "1X2"
        ) if _pre_1x2 else []
        _pre_ou_vbs = []
        if mkt_ou25:
            _pre_ou = self.consensus.combine_ou({"market": mkt_ou25, "poisson": poi_ou}, None)
            if _pre_ou:
                _pre_ou_vbs = self.consensus.detect_value(
                    _pre_ou.get("probs", {}),
                    {"over": ou25_mkt.get("best_over", 0), "under": ou25_mkt.get("best_under", 0)},
                    "O/U 2.5",
                )
        _pre_ou15_vbs = []
        if mkt_ou15:
            _pre_ou15 = self.consensus.combine_ou({"market": mkt_ou15, "poisson": poi_ou15}, None)
            if _pre_ou15:
                _pre_ou15_vbs = self.consensus.detect_value(
                    _pre_ou15.get("probs", {}),
                    {"over": ou15_mkt.get("best_over", 0), "under": ou15_mkt.get("best_under", 0)},
                    "O/U 1.5",
                )
        _pre_btts_vbs = []
        if mkt_btts:
            _pre_btts = self.consensus.combine_btts({"market": mkt_btts, "poisson": poi_btts})
            if _pre_btts:
                _pre_btts_vbs = self.consensus.detect_value(
                    _pre_btts.get("probs", {}),
                    {"yes": btts_mkt.get("best_yes", 0), "no": btts_mkt.get("best_no", 0)},
                    "BTTS",
                )
        _has_pre_value = bool(_pre_vbs or _pre_ou_vbs or _pre_ou15_vbs or _pre_btts_vbs)

        # CAPA 5: DeepSeek — solo si hay valor potencial en capas 1-4
        ai_adj_1x2 = None
        ai_adj_ou = None
        if self.ai.enabled and _has_pre_value:
            ai_stats = {
                "mkt_h": mkt_prob.get("home", 0),
                "mkt_d": mkt_prob.get("draw", 0),
                "mkt_a": mkt_prob.get("away", 0),
                "poi_h": poi_1x2["home"],
                "poi_d": poi_1x2["draw"],
                "poi_a": poi_1x2["away"],
                "xg_h": poi["xg_home"],
                "xg_a": poi["xg_away"],
                "over15": poi_ou15["over"],
                "over25": poi_ou["over"],
                "btts_yes": poi_btts["yes"],
            }
            ai_result = await self.ai.analyze(home, away, result["league"], ai_stats, feats)
            if ai_result:
                result["ai"] = ai_result
                ai_adj_1x2 = ai_result.get("adj_1x2")
                ai_adj_ou = ai_result.get("adj_ou")

        # CAPA 6: Consenso
        cons_1x2 = self.consensus.combine_1x2(
            {"market": mkt_prob, "poisson": poi_1x2, "elo": elo_1x2, "features": feat_1x2},
            ai_adj_1x2,
        )
        result["consensus_1x2"] = cons_1x2

        ou25_models = {"market": mkt_ou25, "poisson": poi_ou}
        cons_ou = self.consensus.combine_ou(ou25_models, ai_adj_ou)
        result["consensus_ou"] = cons_ou

        ou15_models = {"market": mkt_ou15, "poisson": poi_ou15}
        cons_ou15 = self.consensus.combine_ou(ou15_models)
        result["consensus_ou15"] = cons_ou15

        btts_models = {"market": mkt_btts, "poisson": poi_btts}
        cons_btts = self.consensus.combine_btts(btts_models)
        result["consensus_btts"] = cons_btts

        # Filtro de calidad
        confidence = cons_1x2.get("confidence", 0)
        agreement = cons_1x2.get("agreement", 0)

        if market_available:
            quality_ok = (
                confidence >= config.min_confidence
                and agreement >= config.min_model_agreement
                and h2h_mkt.get("num_bookmakers", 0) >= config.min_bookmakers
            )
        else:
            quality_ok = (
                confidence >= config.min_confidence
                and agreement >= config.min_model_agreement
            )

        all_vbs = []
        if quality_ok:
            if cons_1x2:
                vbs_1x2 = self.consensus.detect_value(
                    cons_1x2["probs"], h2h_mkt.get("best_odds", {}), "1X2"
                )
                all_vbs.extend(vbs_1x2)

            if cons_ou and ou25_mkt:
                best_ou = {
                    "over": ou25_mkt.get("best_over", 0),
                    "under": ou25_mkt.get("best_under", 0),
                }
                vbs_ou = self.consensus.detect_value(cons_ou["probs"], best_ou, "O/U 2.5")
                all_vbs.extend(vbs_ou)

            if cons_ou15 and ou15_mkt:
                best_ou15 = {
                    "over": ou15_mkt.get("best_over", 0),
                    "under": ou15_mkt.get("best_under", 0),
                }
                vbs_ou15 = self.consensus.detect_value(cons_ou15["probs"], best_ou15, "O/U 1.5")
                all_vbs.extend(vbs_ou15)

            if cons_btts and btts_mkt:
                best_btts = {
                    "yes": btts_mkt.get("best_yes", 0),
                    "no": btts_mkt.get("best_no", 0),
                }
                vbs_btts = self.consensus.detect_value(cons_btts["probs"], best_btts, "BTTS")
                all_vbs.extend(vbs_btts)

        # Deduplicar
        seen = set()
        unique_vbs = []
        for vb in sorted(all_vbs, key=lambda x: x.get("value", 0), reverse=True):
            key = f"{vb.get('market')}:{vb.get('outcome')}"
            if key not in seen:
                seen.add(key)
                unique_vbs.append(vb)

        result["value_bets"] = unique_vbs
        result["max_value"] = unique_vbs[0]["value"] if unique_vbs else 0
        result["has_value"] = bool(unique_vbs)
        result["quality_ok"] = quality_ok

        if not unique_vbs:
            fallback_pick = None
            fallback_options = []
            if cons_1x2:
                probs = cons_1x2.get("probs", {})
                if probs:
                    outcome = max(probs, key=lambda key: probs.get(key, 0))
                    fallback_options.append({
                        "market": "1X2",
                        "outcome": outcome,
                        "label": self.consensus._label_for_market("1X2", outcome),
                        "prob": round(float(probs.get(outcome) or 0), 4),
                        "odds": round(float((cons_1x2.get("fair_odds") or {}).get(outcome) or 0), 2),
                        "fair_odds": round(float((cons_1x2.get("fair_odds") or {}).get(outcome) or 0), 2),
                        "value": 0.0,
                        "kelly": 0.0,
                        "source": "statistical",
                    })
            for consensus_obj, label in ((cons_ou, "O/U 2.5"), (cons_ou15, "O/U 1.5"), (cons_btts, "BTTS")):
                probs = (consensus_obj or {}).get("probs", {})
                if probs:
                    outcome = max(probs, key=lambda key: probs.get(key, 0))
                    fallback_options.append({
                        "market": label,
                        "outcome": outcome,
                        "label": self.consensus._label_for_market(label, outcome),
                        "prob": round(float(probs.get(outcome) or 0), 4),
                        "odds": round(float((consensus_obj.get("fair_odds") or {}).get(outcome) or 0), 2),
                        "fair_odds": round(float((consensus_obj.get("fair_odds") or {}).get(outcome) or 0), 2),
                        "value": 0.0,
                        "kelly": 0.0,
                        "source": "statistical",
                    })
            if fallback_options:
                fallback_pick = max(fallback_options, key=lambda item: float(item.get("prob") or 0))
            if fallback_pick:
                result["official_pick"] = fallback_pick

        if unique_vbs:
            self.tracker.log_prediction({
                "match_id": result["match_id"],
                "home": home,
                "away": away,
                "league": result["league"],
                "league_id": result.get("league_id"),
                "time": result["time"],
                "date": datetime.now(timezone.utc).date().isoformat(),
                "consensus_1x2": cons_1x2.get("probs", {}),
                "consensus_ou": cons_ou.get("probs", {}),
                "consensus_ou15": cons_ou15.get("probs", {}) if cons_ou15 else {},
                "consensus_btts": cons_btts.get("probs", {}) if cons_btts else {},
                "official_pick": dict(unique_vbs[0]),
                "value_bets": unique_vbs,
            })

        return result
