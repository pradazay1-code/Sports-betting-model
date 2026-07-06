"""The learning system: grading, rolling metrics, error analysis, retraining.

- grade_pending(): fires ~30s after each window closes; resolves direction
  from candles and writes correctness, Brier component and fee-inclusive
  paper P&L.
- error_analysis(): daily; groups losses by regime and writes plain-English
  findings to logs/error_analysis.md (surfaced on the dashboard).
- maybe_retrain(): weekly schedule OR 7-day Brier degrading >10% vs
  validation OR 200 new resolved windows; a new model is promoted only if
  its validation Brier improves.
- adapt_threshold(): raises the edge buffer 1 point (cap 8) when the last
  50 flagged picks are unprofitable on paper.
"""
from __future__ import annotations

import json
import logging
import time

import config
import storage
from engine import edge as edge_mod
from engine import window as win

log = logging.getLogger("pulse.learner")

FINDINGS_PATH = config.LOGS_DIR / "error_analysis.md"


# --------------------------------------------------------------- grading ----

def resolve_direction(asset: str, wstart: int, wclose: int) -> tuple[str, float | None]:
    """(UP|DOWN|FLAT|UNKNOWN, window return) from stored 1m candles."""
    df = storage.get_candles(asset, wstart, wclose)
    if df.empty or len(df) < 10:
        return "UNKNOWN", None
    o, c = float(df.iloc[0]["open"]), float(df.iloc[-1]["close"])
    if o <= 0:
        return "UNKNOWN", None
    ret = c / o - 1.0
    if abs(ret) < 1e-9:
        return "FLAT", ret
    return ("UP" if ret > 0 else "DOWN"), ret


def grade_pending(now_ts: float | None = None) -> int:
    """Grade every prediction whose window has closed. Returns count graded."""
    now_ts = now_ts or time.time()
    graded = 0
    for p in storage.unresolved_predictions(int(now_ts)):
        direction, _ = resolve_direction(p["asset"], p["window_start"], p["window_close"])
        if direction == "UNKNOWN" and now_ts - p["window_close"] < 600:
            continue  # give the collector a few minutes to fill the candles
        y = 1.0 if direction == "UP" else 0.0 if direction == "DOWN" else None
        brier = (p["prob_up"] - y) ** 2 if y is not None else None
        correct = None
        pnl = 0.0
        if p["pick"] in (edge_mod.UP, edge_mod.DOWN) and y is not None:
            correct = 1 if p["pick"] == direction else 0
            entry = p["kalshi_yes_price_at_signal"]
            if entry is not None and 0 < entry < 1:
                pnl = edge_mod.paper_pnl(p["pick"], entry, won=bool(correct))
        storage.insert_outcome({
            "prediction_id": p["id"], "actual_direction": direction,
            "correct": correct, "brier_component": brier, "paper_pnl": pnl,
            "resolved_at": int(now_ts),
        })
        graded += 1
    if graded:
        log.info("graded %d windows", graded)
    return graded


# ------------------------------------------------------------- metrics ------

def rolling_metrics(days: int | None = 7) -> dict:
    since = int(time.time()) - days * 86400 if days else None
    rows = storage.resolved_history(limit=100_000, since_ts=since)
    out: dict = {"overall": _bucket_metrics(rows), "by_asset": {}}
    for asset in config.ASSETS:
        out["by_asset"][asset] = _bucket_metrics([r for r in rows if r["asset"] == asset])
    return out


def _bucket_metrics(rows: list[dict]) -> dict:
    briers = [r["brier_component"] for r in rows if r["brier_component"] is not None]
    picks = [r for r in rows if r["pick"] in (edge_mod.UP, edge_mod.DOWN)]
    graded = [r for r in picks if r["correct"] is not None]
    pnl = sum(r["paper_pnl"] or 0.0 for r in picks)
    return {
        "windows": len(rows),
        "picks": len(picks),
        "no_play_rate": round(1 - len(picks) / len(rows), 3) if rows else None,
        "pick_accuracy": round(sum(r["correct"] for r in graded) / len(graded), 4)
            if graded else None,
        "brier": round(sum(briers) / len(briers), 4) if briers else None,
        "paper_pnl": round(pnl, 2),
    }


def calibration_buckets(days: int = 30) -> list[dict]:
    since = int(time.time()) - days * 86400
    rows = storage.resolved_history(limit=100_000, since_ts=since)
    rows = [r for r in rows if r["actual_direction"] in ("UP", "DOWN")]
    buckets = []
    for lo in (0.0, 0.4, 0.45, 0.5, 0.55, 0.6):
        hi = {0.0: 0.4, 0.4: 0.45, 0.45: 0.5, 0.5: 0.55, 0.55: 0.6, 0.6: 1.0}[lo]
        rs = [r for r in rows if lo <= r["prob_up"] < hi]
        if len(rs) >= 10:
            buckets.append({
                "range": f"{lo:.2f}-{hi:.2f}",
                "predicted": round(sum(r["prob_up"] for r in rs) / len(rs), 3),
                "actual": round(sum(1 for r in rs if r["actual_direction"] == "UP") / len(rs), 3),
                "n": len(rs)})
    return buckets


# -------------------------------------------------------- error analysis ----

def _regime(r: dict) -> dict[str, str]:
    f = json.loads(r["feature_json"]) if r.get("feature_json") else {}
    hour = win.et_datetime(r["window_start"]).hour
    tod = ("overnight(0-6am)" if hour < 6 else "morning(6-12)" if hour < 12
           else "afternoon(12-6pm)" if hour < 18 else "evening(6pm-12)")
    return {
        "volatility": "high-vol" if f.get("vol_regime", 0) > 0.5 else "normal-vol",
        "time_of_day": tod,
        "news": "news-present" if f.get("news_hi_count_60m", 0) > 0 else "quiet",
        "btc_alignment": (
            "with-BTC" if (f.get("btc_ret_5m", 0) > 0) == (r["pick"] == "UP")
            else "against-BTC") if r["pick"] in ("UP", "DOWN") else "n/a",
    }


def error_analysis(days: int = 14) -> list[str]:
    since = int(time.time()) - days * 86400
    rows = [r for r in storage.resolved_history(limit=100_000, since_ts=since)
            if r["correct"] is not None]
    findings: list[str] = []
    if len(rows) < 30:
        findings.append(f"Only {len(rows)} graded picks in the last {days}d — "
                        "not enough for regime analysis yet.")
    else:
        for asset in ["ALL", *config.ASSETS]:
            sub = rows if asset == "ALL" else [r for r in rows if r["asset"] == asset]
            if len(sub) < 20:
                continue
            base = sum(r["correct"] for r in sub) / len(sub)
            groups: dict[str, list[int]] = {}
            for r in sub:
                for dim, val in _regime(r).items():
                    groups.setdefault(f"{dim}={val}", []).append(r["correct"])
            for key, vals in sorted(groups.items()):
                if len(vals) < 15:
                    continue
                acc = sum(vals) / len(vals)
                if acc < base - 0.06 and acc < 0.5:
                    findings.append(
                        f"{asset}: picks in regime [{key}] are {acc:.0%} accurate "
                        f"over {len(vals)} picks (vs {base:.0%} baseline) — "
                        f"consider suppressing.")
    m = rolling_metrics(7)["overall"]
    findings.append(
        f"7-day: {m['picks']} picks / {m['windows']} windows "
        f"(NO PLAY rate {m['no_play_rate']}), accuracy {m['pick_accuracy']}, "
        f"Brier {m['brier']}, paper P&L ${m['paper_pnl']}.")
    stamp = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    FINDINGS_PATH.write_text(
        f"# Pulse Engine — error analysis ({stamp})\n\n"
        + "\n".join(f"- {f}" for f in findings) + "\n")
    storage.set_setting("last_error_analysis", str(int(time.time())))
    return findings


def latest_findings() -> list[str]:
    if not FINDINGS_PATH.exists():
        return []
    return [l[2:] for l in FINDINGS_PATH.read_text().splitlines()
            if l.startswith("- ")]


# ------------------------------------------------------------- retraining ---

def _should_retrain(asset: str) -> str | None:
    reg = storage.registry_rows(asset)
    if not reg:
        return "no model registered"
    newest = reg[0]
    if time.time() - newest["trained_at"] > config.RETRAIN_EVERY_DAYS * 86400:
        return f"weekly schedule ({config.RETRAIN_EVERY_DAYS}d)"
    last_count = int(storage.get_setting(f"resolved_at_train_{asset}", "0") or 0)
    new_outcomes = storage.resolved_count() - last_count
    if new_outcomes >= config.RETRAIN_NEW_OUTCOMES:
        return f"{new_outcomes} new resolved windows"
    live = rolling_metrics(7)["by_asset"].get(asset, {})
    vb = newest.get("val_brier")
    if vb and live.get("brier") and live["brier"] > vb * (1 + config.RETRAIN_BRIER_DEGRADATION):
        return f"7d Brier {live['brier']} degraded >10% vs validation {vb:.4f}"
    return None


def maybe_retrain() -> dict[str, str]:
    """Check triggers per asset; retrain and promote only on improvement."""
    from engine.model import train_asset
    import joblib

    actions: dict[str, str] = {}
    for asset in config.ASSETS:
        reason = _should_retrain(asset)
        if not reason:
            continue
        log.info("%s: retraining (%s)", asset, reason)
        path = config.MODELS_DIR / f"{asset}.joblib"
        old = joblib.load(path) if path.exists() else None
        old_brier = old["metrics"]["brier"] if old else float("inf")
        try:
            new = train_asset(asset)
        except Exception as e:  # noqa: BLE001
            actions[asset] = f"retrain failed: {e}"
            log.error("%s retrain failed: %s", asset, e)
            continue
        if new is None:
            actions[asset] = "retrain skipped: insufficient data"
            continue
        if new["metrics"]["brier"] <= old_brier:
            actions[asset] = (f"promoted {new['version']} "
                              f"(Brier {new['metrics']['brier']:.4f} <= {old_brier:.4f}); {reason}")
            storage.set_setting(f"resolved_at_train_{asset}", str(storage.resolved_count()))
        else:
            if old is not None:
                joblib.dump(old, path)  # restore the better old bundle
            actions[asset] = (f"kept old model: new Brier {new['metrics']['brier']:.4f} "
                              f"worse than {old_brier:.4f}")
        log.info("%s: %s", asset, actions[asset])
        storage.set_setting("last_retrain_check", str(int(time.time())))
    return actions


# ---------------------------------------------------- adaptive threshold ----

def adapt_threshold() -> float:
    """Raise the edge buffer 1pt (cap 8) if the last N flagged picks lose money."""
    rows = [r for r in storage.resolved_history(limit=2000)
            if r["pick"] in (edge_mod.UP, edge_mod.DOWN)]
    recent = rows[:config.ADAPTIVE_LOOKBACK_PICKS]
    buffer = storage.current_edge_buffer()
    if len(recent) >= config.ADAPTIVE_LOOKBACK_PICKS:
        pnl = sum(r["paper_pnl"] or 0.0 for r in recent)
        if pnl < 0 and buffer < config.MAX_EDGE_BUFFER:
            marker = recent[0]["id"]
            if storage.get_setting("buffer_bump_marker") != str(marker):
                buffer = round(min(buffer + 0.01, config.MAX_EDGE_BUFFER), 3)
                storage.set_setting("edge_buffer", str(buffer))
                storage.set_setting("buffer_bump_marker", str(marker))
                log.warning("last %d picks lost $%.2f on paper — edge buffer "
                            "raised to %.2f", len(recent), pnl, buffer)
    return buffer
