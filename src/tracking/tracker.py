"""
Tracking de predicciones — guarda JSON Lines y calcula ROI acumulado
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from config import config


class PredictionTracker:

    def __init__(self, filepath: str = None):
        self.filepath = Path(filepath or os.path.join(config.predictions_dir, "predictions.jsonl"))
        self.filepath.parent.mkdir(parents=True, exist_ok=True)

    def log_prediction(self, prediction: dict):
        prediction["timestamp"] = datetime.now(timezone.utc).isoformat()
        with open(self.filepath, "a") as f:
            f.write(json.dumps(prediction, ensure_ascii=False) + "\n")

    def log_result(self, match_id: str, home_goals: int, away_goals: int):
        if not self.filepath.exists():
            return
        lines = self.filepath.read_text().strip().split("\n")
        updated = []
        for line in lines:
            if not line.strip():
                continue
            pred = json.loads(line)
            if pred.get("match_id") == match_id and "result" not in pred:
                pred["result"] = {"home": home_goals, "away": away_goals}
                for vb in pred.get("value_bets", []):
                    outcome = vb["outcome"]
                    won = False
                    total_goals = home_goals + away_goals
                    if vb["market"] == "1X2":
                        won = (
                            (outcome == "home" and home_goals > away_goals)
                            or (outcome == "draw" and home_goals == away_goals)
                            or (outcome == "away" and away_goals > home_goals)
                        )
                    elif vb["market"] in ("O/U 2.5", "totals"):
                        won = (
                            (outcome == "over" and total_goals > 2.5)
                            or (outcome == "under" and total_goals < 2.5)
                        )
                    vb["won"] = won
                    vb["pnl"] = round((vb.get("odds", vb.get("best_odds", 1)) - 1) if won else -1, 2)
            updated.append(json.dumps(pred, ensure_ascii=False))
        self.filepath.write_text("\n".join(updated) + "\n")

    def get_stats(self) -> dict:
        if not self.filepath.exists():
            return {"total_bets": 0}
        lines = [l for l in self.filepath.read_text().strip().split("\n") if l.strip()]
        total = won = lost = pending = 0
        pnl = 0.0
        by_market = {}
        for line in lines:
            pred = json.loads(line)
            for vb in pred.get("value_bets", []):
                market = vb.get("market", "?")
                total += 1
                if "won" in vb:
                    if vb["won"]:
                        won += 1
                    else:
                        lost += 1
                    pnl += vb.get("pnl", 0)
                    by_market.setdefault(market, {"won": 0, "lost": 0, "pnl": 0.0})
                    if vb["won"]:
                        by_market[market]["won"] += 1
                    else:
                        by_market[market]["lost"] += 1
                    by_market[market]["pnl"] += vb.get("pnl", 0)
                else:
                    pending += 1

        settled = won + lost
        return {
            "total_bets": total,
            "won": won,
            "lost": lost,
            "pending": pending,
            "hit_rate": round(won / settled, 3) if settled > 0 else 0,
            "pnl_units": round(pnl, 2),
            "roi_pct": round(pnl / settled * 100, 1) if settled > 0 else 0,
            "by_market": by_market,
        }

    def get_recent(self, n: int = 10) -> list:
        if not self.filepath.exists():
            return []
        lines = [l for l in self.filepath.read_text().strip().split("\n") if l.strip()]
        return [json.loads(l) for l in lines[-n:]]
