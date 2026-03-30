"""
Tracking de predicciones — guarda JSON Lines, evita duplicados por partido
y permite medir por separado sugerencias generales vs picks líderes.
"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import config

MARKET_KEY = "O/U 2.5"
MARKET_KEY_15 = "O/U 1.5"
MARKET_KEY_BTTS = "BTTS"
MARKET_KEY_DC = "Doble oportunidad"


class PredictionTracker:

    def __init__(self, filepath: str = None):
        self.filepath = Path(filepath or os.path.join(config.predictions_dir, "predictions.jsonl"))
        self.filepath.parent.mkdir(parents=True, exist_ok=True)

    def _read_predictions(self) -> list[dict]:
        if not self.filepath.exists():
            return []
        text = self.filepath.read_text().strip()
        if not text:
            return []
        return [json.loads(line) for line in text.splitlines() if line.strip()]

    def _write_predictions(self, predictions: list[dict]):
        if not predictions:
            self.filepath.write_text("")
            return
        payload = "\n".join(json.dumps(pred, ensure_ascii=False) for pred in predictions) + "\n"
        self.filepath.write_text(payload)

    @staticmethod
    def _same_slot(existing: dict, incoming: dict) -> bool:
        if existing.get("match_id") and incoming.get("match_id"):
            return (
                existing.get("match_id") == incoming.get("match_id")
                and existing.get("date") == incoming.get("date")
            )
        return (
            existing.get("date") == incoming.get("date")
            and existing.get("home") == incoming.get("home")
            and existing.get("away") == incoming.get("away")
            and existing.get("time") == incoming.get("time")
        )

    @staticmethod
    def _extract_line(market: str) -> float | None:
        if not market.startswith("O/U "):
            return None
        try:
            return float(market.split(" ", 1)[1])
        except (IndexError, ValueError):
            return None

    def _settle_pick(self, pick: dict, home_goals: int, away_goals: int) -> tuple[bool, float] | None:
        outcome = pick.get("outcome")
        market = pick.get("market", "")
        total_goals = home_goals + away_goals
        won = None

        if market == "1X2":
            won = (
                (outcome == "home" and home_goals > away_goals)
                or (outcome == "draw" and home_goals == away_goals)
                or (outcome == "away" and away_goals > home_goals)
            )
        elif market in {MARKET_KEY, MARKET_KEY_15} or market.startswith("O/U "):
            line = self._extract_line(market)
            if line is None:
                return None
            won = (
                (outcome == "over" and total_goals > line)
                or (outcome == "under" and total_goals < line)
            )
        elif market == MARKET_KEY_BTTS:
            won = (
                (outcome == "yes" and home_goals > 0 and away_goals > 0)
                or (outcome == "no" and (home_goals == 0 or away_goals == 0))
            )
        elif market == MARKET_KEY_DC:
            won = (
                (outcome == "1X" and home_goals >= away_goals)
                or (outcome == "X2" and away_goals >= home_goals)
                or (outcome == "12" and home_goals != away_goals)
            )

        if won is None:
            return None

        odds = pick.get("odds", pick.get("best_odds", 1))
        pnl = round(odds - 1 if won else -1.0, 2)
        return bool(won), pnl

    def log_prediction(self, prediction: dict):
        predictions = self._read_predictions()
        incoming = dict(prediction)
        incoming["timestamp"] = datetime.now(timezone.utc).isoformat()
        incoming.setdefault("official_pick", (incoming.get("value_bets") or [None])[0])
        incoming.setdefault("is_highlight", False)
        incoming.setdefault("highlight_rank", None)
        incoming.setdefault("is_leader", False)
        incoming.setdefault("leader_rank", None)
        incoming.setdefault("leader_name", "")
        incoming.setdefault("leader_score", 0.0)

        for idx, existing in enumerate(predictions):
            if self._same_slot(existing, incoming) and "result" not in existing:
                preserved = {
                    "result": existing.get("result"),
                    "official_pick": incoming.get("official_pick") or existing.get("official_pick"),
                    "is_highlight": existing.get("is_highlight", False),
                    "highlight_rank": existing.get("highlight_rank"),
                    "is_leader": existing.get("is_leader", False),
                    "leader_rank": existing.get("leader_rank"),
                    "leader_name": existing.get("leader_name", ""),
                    "leader_score": existing.get("leader_score", 0.0),
                }
                predictions[idx] = {**existing, **incoming, **preserved}
                self._write_predictions(predictions)
                return

        predictions.append(incoming)
        self._write_predictions(predictions)

    def tag_cycle(self, date_str: str, highlights: list[dict], leaders: list[dict]):
        predictions = self._read_predictions()
        if not predictions:
            return

        highlight_map = {
            item.get("match_id"): {
                "rank": idx + 1,
                "score": float(item.get("interest_score") or 0),
            }
            for idx, item in enumerate(highlights or [])
            if item.get("match_id")
        }
        leader_map = {
            item.get("match_id"): {
                "rank": idx + 1,
                "name": item.get("leader_name", f"ValueX Prime #{idx + 1}"),
                "score": float(item.get("leader_score") or item.get("interest_score") or 0),
                "official_pick": item.get("official_pick"),
            }
            for idx, item in enumerate(leaders or [])
            if item.get("match_id")
        }

        changed = False
        for pred in predictions:
            if pred.get("date") != date_str:
                continue
            match_id = pred.get("match_id")
            highlight = highlight_map.get(match_id)
            leader = leader_map.get(match_id)

            pred["is_highlight"] = bool(highlight)
            pred["highlight_rank"] = highlight.get("rank") if highlight else None
            pred["highlight_score"] = round(highlight.get("score", 0.0), 4) if highlight else 0.0
            pred["is_leader"] = bool(leader)
            pred["leader_rank"] = leader.get("rank") if leader else None
            pred["leader_name"] = leader.get("name", "") if leader else ""
            pred["leader_score"] = round(leader.get("score", 0.0), 4) if leader else 0.0
            if leader and leader.get("official_pick"):
                pred["official_pick"] = dict(leader["official_pick"])
            changed = True

        if changed:
            self._write_predictions(predictions)

    def log_result(self, match_id: str, home_goals: int, away_goals: int):
        predictions = self._read_predictions()
        if not predictions:
            return

        changed = False
        for pred in predictions:
            if pred.get("match_id") != match_id or "result" in pred:
                continue
            pred["result"] = {"home": home_goals, "away": away_goals}
            for vb in pred.get("value_bets", []):
                settled = self._settle_pick(vb, home_goals, away_goals)
                if settled is None:
                    continue
                won, pnl = settled
                vb["won"] = won
                vb["pnl"] = pnl

            official = pred.get("official_pick")
            if official:
                settled = self._settle_pick(official, home_goals, away_goals)
                if settled is not None:
                    won, pnl = settled
                    official["won"] = won
                    official["pnl"] = pnl
            changed = True

        if changed:
            self._write_predictions(predictions)

    def _collect_entries(self, leaders_only: bool = False, date_str: str | None = None) -> list[dict]:
        entries = []
        for pred in self._read_predictions():
            if date_str and pred.get("date") != date_str:
                continue

            picks = []
            if leaders_only:
                if not pred.get("is_leader"):
                    continue
                official = pred.get("official_pick") or ((pred.get("value_bets") or [None])[0])
                if official:
                    picks = [official]
            else:
                picks = pred.get("value_bets", [])

            for pick in picks:
                entries.append({
                    "match_id": pred.get("match_id", ""),
                    "date": pred.get("date", ""),
                    "time": pred.get("time", ""),
                    "league": pred.get("league", "?"),
                    "league_id": pred.get("league_id"),
                    "home": pred.get("home", ""),
                    "away": pred.get("away", ""),
                    "market": pick.get("market", "?"),
                    "outcome": pick.get("outcome", "?"),
                    "label": pick.get("label") or pick.get("outcome", "?"),
                    "odds": pick.get("odds", pick.get("best_odds", 1)),
                    "value": pick.get("value", 0),
                    "kelly": pick.get("kelly", 0),
                    "won": pick.get("won"),
                    "pnl": pick.get("pnl", 0.0),
                    "is_leader": bool(pred.get("is_leader")),
                    "leader_rank": pred.get("leader_rank"),
                    "leader_name": pred.get("leader_name", ""),
                })
        return entries

    def get_stats(self, leaders_only: bool = False, date_str: str | None = None) -> dict:
        entries = self._collect_entries(leaders_only=leaders_only, date_str=date_str)
        if not entries:
            return {"total_bets": 0}

        total = len(entries)
        won = lost = pending = 0
        pnl = 0.0
        by_market: dict = {}
        by_league: dict = {}

        for entry in entries:
            market = entry.get("market", "?")
            league = entry.get("league", "?")
            by_market.setdefault(market, {"won": 0, "lost": 0, "pnl": 0.0})
            by_league.setdefault(league, {"won": 0, "lost": 0, "pnl": 0.0})
            if entry.get("won") is True:
                won += 1
                pnl += entry.get("pnl", 0.0)
                by_market[market]["won"] += 1
                by_market[market]["pnl"] = round(by_market[market]["pnl"] + entry.get("pnl", 0.0), 2)
                by_league[league]["won"] += 1
                by_league[league]["pnl"] = round(by_league[league]["pnl"] + entry.get("pnl", 0.0), 2)
            elif entry.get("won") is False:
                lost += 1
                pnl += entry.get("pnl", 0.0)
                by_market[market]["lost"] += 1
                by_market[market]["pnl"] = round(by_market[market]["pnl"] + entry.get("pnl", 0.0), 2)
                by_league[league]["lost"] += 1
                by_league[league]["pnl"] = round(by_league[league]["pnl"] + entry.get("pnl", 0.0), 2)
            else:
                pending += 1

        settled = won + lost
        return {
            "total_bets": total,
            "won": won,
            "lost": lost,
            "pending": pending,
            "settled": settled,
            "leaders_only": leaders_only,
            "hit_rate": round(won / settled, 3) if settled > 0 else 0,
            "pnl_units": round(pnl, 2),
            "roi_pct": round(pnl / settled * 100, 1) if settled > 0 else 0,
            "by_market": by_market,
            "by_league": by_league,
        }

    def get_daily_report(self, date_str: str | None = None, leaders_only: bool = False) -> dict:
        target = date_str or datetime.now(timezone.utc).date().isoformat()
        entries = self._collect_entries(leaders_only=leaders_only, date_str=target)
        if not entries:
            return {
                "date": target,
                "leaders_only": leaders_only,
                "title": "ValueX Prime" if leaders_only else "Radar del día",
                "basis": "1u flat por pick oficial" if leaders_only else "1u flat por sugerencia",
                "total": 0,
                "won": 0,
                "lost": 0,
                "pending": 0,
                "settled": 0,
                "hit_rate": 0,
                "pnl_units": 0,
                "roi_pct": 0,
                "by_market": {},
                "by_league": {},
                "top_hits": [],
                "top_misses": [],
            }

        summary = self.get_stats(leaders_only=leaders_only, date_str=target)
        settled_entries = [entry for entry in entries if entry.get("won") is not None]
        top_hits = sorted(
            [entry for entry in settled_entries if entry.get("won") is True],
            key=lambda entry: entry.get("pnl", 0.0),
            reverse=True,
        )[:3]
        top_misses = sorted(
            [entry for entry in settled_entries if entry.get("won") is False],
            key=lambda entry: entry.get("pnl", 0.0),
        )[:3]

        return {
            "date": target,
            "leaders_only": leaders_only,
            "title": "ValueX Prime" if leaders_only else "Radar del día",
            "basis": "1u flat por pick oficial" if leaders_only else "1u flat por sugerencia",
            "total": summary.get("total_bets", 0),
            "won": summary.get("won", 0),
            "lost": summary.get("lost", 0),
            "pending": summary.get("pending", 0),
            "settled": summary.get("settled", 0),
            "hit_rate": summary.get("hit_rate", 0),
            "pnl_units": summary.get("pnl_units", 0),
            "roi_pct": summary.get("roi_pct", 0),
            "by_market": summary.get("by_market", {}),
            "by_league": summary.get("by_league", {}),
            "top_hits": top_hits,
            "top_misses": top_misses,
        }

    def get_pending_predictions(self, max_days_back: int = 4) -> list[dict]:
        predictions = self._read_predictions()
        if not predictions:
            return []

        now = datetime.now(timezone.utc)
        min_date = (now - timedelta(days=max_days_back)).date().isoformat()
        pending_map = {}

        for pred in predictions:
            if "result" in pred:
                continue
            kickoff = pred.get("time")
            if kickoff:
                try:
                    kickoff_dt = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
                except ValueError:
                    kickoff_dt = None
                if kickoff_dt and kickoff_dt > now:
                    continue
            if pred.get("date", "") < min_date:
                continue
            key = pred.get("match_id") or f"{pred.get('home')}::{pred.get('away')}::{pred.get('date')}"
            pending_map[key] = pred

        return list(pending_map.values())

    def get_recent(self, n: int = 10) -> list:
        predictions = self._read_predictions()
        return predictions[-n:]
