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

    async def analyze(self, match: dict, home_stats: dict = None, away_stats: dict = None) -> dict:
        home = match.get("home_team") or match.get("home_team_name", "?")
        away = match.get("away_team") or match.get("away_team_name", "?")
        bms = match.get("bookmakers", [])

        result = {
            "match_id": match.get("id", ""),
            "home": home,
            "away": away,
            "time": match.get("commence_time", ""),
            "league": match.get("sport_title", ""),
        }

        # CAPA 1: Mercado
        h2h_mkt = self.market.analyze_h2h(bms, home, away)
        ou_mkt = self.market.analyze_totals(bms)
        result["market"] = {"h2h": h2h_mkt, "ou": ou_mkt}

        if not h2h_mkt:
            result["has_value"] = False
            return result

        # Bug #1: usar is not None para no descartar dicts con valores bajos
        sharp = h2h_mkt.get("sharp_prob")
        mkt_prob = sharp if sharp is not None else h2h_mkt.get("implied_prob", {})

        mkt_ou = (
            {"over": ou_mkt["over_prob"], "under": ou_mkt["under_prob"]}
            if ou_mkt else None
        )

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
        poi_ou = poi["probs_ou25"]

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
        if mkt_ou:
            _pre_ou = self.consensus.combine_ou({"market": mkt_ou, "poisson": poi_ou}, None)
            if _pre_ou:
                _pre_ou_vbs = self.consensus.detect_value(
                    _pre_ou.get("probs", {}),
                    {"over": ou_mkt.get("avg_over", 0), "under": ou_mkt.get("avg_under", 0)},
                    "O/U 2.5",
                )
        _has_pre_value = bool(_pre_vbs or _pre_ou_vbs)

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
                "over25": poi_ou["over"],
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

        ou_models = {"market": mkt_ou, "poisson": poi_ou}
        cons_ou = self.consensus.combine_ou(ou_models, ai_adj_ou)
        result["consensus_ou"] = cons_ou

        # Filtro de calidad
        confidence = cons_1x2.get("confidence", 0)
        agreement = cons_1x2.get("agreement", 0)

        quality_ok = (
            confidence >= config.min_confidence
            and agreement >= config.min_model_agreement
            and h2h_mkt.get("num_bookmakers", 0) >= config.min_bookmakers
        )

        all_vbs = []
        if quality_ok:
            if cons_1x2:
                vbs_1x2 = self.consensus.detect_value(
                    cons_1x2["probs"], h2h_mkt.get("best_odds", {}), "1X2"
                )
                all_vbs.extend(vbs_1x2)

            if cons_ou and ou_mkt:
                best_ou = {
                    "over": ou_mkt.get("avg_over", 0),
                    "under": ou_mkt.get("avg_under", 0),
                }
                vbs_ou = self.consensus.detect_value(cons_ou["probs"], best_ou, "O/U 2.5")
                all_vbs.extend(vbs_ou)

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

        if unique_vbs:
            self.tracker.log_prediction({
                "match_id": result["match_id"],
                "home": home,
                "away": away,
                "league": result["league"],
                "date": datetime.now(timezone.utc).date().isoformat(),
                "consensus_1x2": cons_1x2.get("probs", {}),
                "consensus_ou": cons_ou.get("probs", {}),
                "value_bets": unique_vbs,
            })

        return result
