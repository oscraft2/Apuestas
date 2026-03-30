"""
Feature #8 — Modelo ML con XGBoost
Entrena sobre las predicciones acumuladas del tracker.
A partir de ~500 apuestas supera a las heurísticas del consenso.
Features: probs de todos los modelos, ELO diff, form, xG, odds.
"""
import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MODEL_PATH = "data/xgb_model.json"
FEATURE_NAMES = [
    "mkt_home", "mkt_draw", "mkt_away",
    "poi_home", "poi_draw", "poi_away",
    "elo_home", "elo_draw", "elo_away",
    "feat_home", "feat_draw", "feat_away",
    "xg_home", "xg_away", "xg_diff",
    "elo_diff", "form_diff", "ou_over",
    "mkt_margin", "num_bookmakers",
    "consensus_home", "consensus_draw", "consensus_away",
]


def _extract_features(pred: dict) -> Optional[list]:
    """Extrae el vector de features de una predicción del tracker."""
    mkt = pred.get("market", {}).get("h2h", {})
    poi = pred.get("poisson", {})
    elo = pred.get("elo", {})
    feats = pred.get("features", {})
    cons = pred.get("consensus_1x2", {})

    if not (mkt and poi and cons):
        return None

    mkt_p = mkt.get("implied_prob", {})
    poi_p = poi.get("probs_1x2", {})
    elo_p = {k: elo.get(k, 0) for k in ["home", "draw", "away"]}
    feat_p = feats.get("prob_1x2", {}) if feats else {}
    cons_p = cons.get("probs", {})

    return [
        mkt_p.get("home", 0), mkt_p.get("draw", 0), mkt_p.get("away", 0),
        poi_p.get("home", 0), poi_p.get("draw", 0), poi_p.get("away", 0),
        elo_p.get("home", 0), elo_p.get("draw", 0), elo_p.get("away", 0),
        feat_p.get("home", 0), feat_p.get("draw", 0), feat_p.get("away", 0),
        poi.get("xg_home", 0), poi.get("xg_away", 0),
        poi.get("xg_home", 0) - poi.get("xg_away", 0),
        elo.get("home_elo", 1500) - elo.get("away_elo", 1500),
        feats.get("form_diff", 0) if feats else 0,
        poi.get("probs_ou25", {}).get("over", 0),
        mkt.get("market_margin", 0.05),
        mkt.get("num_bookmakers", 5),
        cons_p.get("home", 0), cons_p.get("draw", 0), cons_p.get("away", 0),
    ]


class XGBoostModel:
    """
    Wrapper del modelo XGBoost para predicción de valor.
    Target: 1 si la apuesta ganó, 0 si perdió.
    """

    def __init__(self, model_path: str = MODEL_PATH):
        self.model_path = model_path
        self._model = None
        self._load()

    def _load(self):
        if not os.path.exists(self.model_path):
            return
        try:
            import xgboost as xgb
            self._model = xgb.XGBClassifier()
            self._model.load_model(self.model_path)
            logger.info("Modelo XGBoost cargado desde disco.")
        except ImportError:
            logger.warning("xgboost no instalado. Instala con: pip install xgboost")
        except Exception as e:
            logger.warning(f"No se pudo cargar el modelo XGBoost: {e}")

    @property
    def is_available(self) -> bool:
        return self._model is not None

    def train(self, predictions_file: str) -> dict:
        """
        Entrena el modelo con el historial del tracker.
        Retorna métricas de evaluación.
        """
        try:
            import xgboost as xgb
            from sklearn.model_selection import train_test_split
            from sklearn.metrics import roc_auc_score, accuracy_score
        except ImportError:
            return {"error": "xgboost y scikit-learn requeridos: pip install xgboost scikit-learn"}

        path = Path(predictions_file)
        if not path.exists():
            return {"error": "No hay predicciones para entrenar."}

        X, y = [], []
        lines = [l for l in path.read_text().strip().split("\n") if l.strip()]

        for line in lines:
            pred = json.loads(line)
            if "result" not in pred:
                continue
            for vb in pred.get("value_bets", []):
                if "won" not in vb:
                    continue
                features = _extract_features(pred)
                if features:
                    X.append(features)
                    y.append(1 if vb["won"] else 0)

        if len(X) < 50:
            return {"error": f"Datos insuficientes: {len(X)} ejemplos (mínimo 50)."}

        import numpy as np
        X = np.array(X)
        y = np.array(y)

        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

        model = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            use_label_encoder=False,
            eval_metric="logloss",
            random_state=42,
        )
        model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

        y_pred = model.predict(X_test)
        y_prob = model.predict_proba(X_test)[:, 1]

        auc = roc_auc_score(y_test, y_prob)
        acc = accuracy_score(y_test, y_pred)

        os.makedirs(os.path.dirname(self.model_path) or ".", exist_ok=True)
        model.save_model(self.model_path)
        self._model = model

        importances = dict(zip(FEATURE_NAMES, model.feature_importances_.tolist()))
        top_features = sorted(importances.items(), key=lambda x: x[1], reverse=True)[:5]

        logger.info(f"Modelo entrenado: AUC={auc:.3f}, ACC={acc:.3f}, n={len(X)}")
        return {
            "trained": True,
            "n_samples": len(X),
            "n_train": len(X_train),
            "n_test": len(X_test),
            "auc": round(auc, 4),
            "accuracy": round(acc, 4),
            "top_features": top_features,
        }

    def predict_proba(self, pred: dict) -> Optional[float]:
        """
        Retorna probabilidad de que la apuesta sea ganadora según XGBoost.
        None si el modelo no está disponible o faltan features.
        """
        if not self.is_available:
            return None
        features = _extract_features(pred)
        if not features:
            return None
        import numpy as np
        try:
            prob = self._model.predict_proba(np.array([features]))[0][1]
            return round(float(prob), 4)
        except Exception as e:
            logger.warning(f"XGBoost predict error: {e}")
            return None

    def format_train_result(self, result: dict) -> str:
        if "error" in result:
            return f"❌ {result['error']}"
        lines = [
            "🤖 <b>Modelo XGBoost entrenado</b>",
            f"Muestras: {result['n_samples']} ({result['n_train']} train / {result['n_test']} test)",
            f"AUC-ROC: <b>{result['auc']:.4f}</b>",
            f"Accuracy: <b>{result['accuracy']:.1%}</b>",
            "",
            "<b>Top features:</b>",
        ]
        for feat, imp in result.get("top_features", []):
            lines.append(f"  {feat}: {imp:.3f}")
        lines.append("\nModelo guardado y activo para próximas predicciones.")
        return "\n".join(lines)
