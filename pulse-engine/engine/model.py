"""Per-asset direction models: logistic baseline + calibrated LightGBM.

Validation is walk-forward only (expanding window, 7-day validation chunks,
rolled forward) — never shuffled, so no temporal leakage. Calibration is an
isotonic fit on the pooled out-of-fold predictions; edge math depends on the
probabilities being honest, so calibration quality matters more than raw
accuracy here. Reality check: walk-forward accuracy on 15-minute crypto
direction is expected to hover near 52% — the dashboard says so.

CLI:  python engine/model.py --train [--asset BTC]
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
import storage
from engine import window as win
from engine.features import FEATURE_COLUMNS, build_features

log = logging.getLogger("pulse.model")


# ------------------------------------------------------- training matrix ----

def build_training_frame(asset: str, days: int | None = None) -> pd.DataFrame:
    """One row per historical 15-min window: features at prediction time + label.

    Live-only inputs (Kalshi quotes, news, F&G) are neutral constants here,
    exactly as build_features defaults them — same code path as live.
    """
    from collectors.history_backfill import resample_15m

    days = days or config.BACKFILL_DAYS
    start = int(time.time()) - days * 86400
    candles = storage.get_candles(asset, start - 6 * 3600)  # warm-up margin
    btc = candles if asset == "BTC" else storage.get_candles("BTC", start - 6 * 3600)
    wins = resample_15m(asset, start)
    if candles.empty or wins.empty:
        return pd.DataFrame()

    rows = []
    for wstart, w in wins.dropna(subset=["direction"]).iterrows():
        at_ts = win.prediction_time(int(wstart))
        feats = build_features(asset, at_ts, candles, btc)
        if feats is None:
            continue
        feats["_window_start"] = int(wstart)
        feats["_label"] = int(w["direction"])
        rows.append(feats)
    df = pd.DataFrame(rows)
    log.info("%s: training frame %d rows x %d features", asset, len(df),
             len(FEATURE_COLUMNS))
    return df


# ---------------------------------------------------------- walk-forward ----

@dataclass
class Metrics:
    logloss: float
    brier: float
    accuracy: float
    n: int

    def row(self) -> dict:
        return {"logloss": round(self.logloss, 4), "brier": round(self.brier, 4),
                "accuracy": round(self.accuracy, 4), "n": self.n}


def _score(y: np.ndarray, p: np.ndarray) -> Metrics:
    from sklearn.metrics import accuracy_score, brier_score_loss, log_loss
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return Metrics(
        logloss=float(log_loss(y, p)),
        brier=float(brier_score_loss(y, p)),
        accuracy=float(accuracy_score(y, (p >= 0.5).astype(int))),
        n=len(y))


def _walk_forward_splits(ts: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
    """Expanding-window index splits on window_start timestamps."""
    t0, t1 = ts.min(), ts.max()
    min_train = config.WALK_FORWARD_MIN_TRAIN_DAYS * 86400
    val_len = config.WALK_FORWARD_VAL_DAYS * 86400
    splits = []
    cursor = t0 + min_train
    while cursor + val_len // 2 <= t1:
        tr = np.where(ts < cursor)[0]
        va = np.where((ts >= cursor) & (ts < cursor + val_len))[0]
        if len(tr) >= 500 and len(va) >= 50:
            splits.append((tr, va))
        cursor += val_len
    return splits


def _make_lgbm():
    import lightgbm as lgb
    return lgb.LGBMClassifier(
        n_estimators=300, learning_rate=0.05, num_leaves=31,
        min_child_samples=50, subsample=0.9, subsample_freq=1,
        colsample_bytree=0.8, reg_lambda=1.0, verbose=-1)


def _make_baseline():
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    return make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, C=0.5))


def walk_forward(df: pd.DataFrame, factory) -> tuple[Metrics, np.ndarray, np.ndarray]:
    """Returns (pooled metrics, OOF probs, OOF labels) across all folds."""
    X = df[FEATURE_COLUMNS].astype(float)
    y = df["_label"].to_numpy(dtype=int)
    ts = df["_window_start"].to_numpy(dtype=int)
    probs, labels = [], []
    for tr, va in _walk_forward_splits(ts):
        m = factory()
        m.fit(X.iloc[tr], y[tr])
        probs.append(m.predict_proba(X.iloc[va])[:, 1])
        labels.append(y[va])
    if not probs:
        raise RuntimeError("not enough data for walk-forward validation")
    p, yy = np.concatenate(probs), np.concatenate(labels)
    return _score(yy, p), p, yy


# ----------------------------------------------------------------- train ----

def train_asset(asset: str, days: int | None = None,
                register: bool = True) -> dict | None:
    from sklearn.isotonic import IsotonicRegression

    df = build_training_frame(asset, days)
    if len(df) < 1500:
        log.warning("%s: only %d usable windows — skipping train", asset, len(df))
        return None

    base_metrics, _, _ = walk_forward(df, _make_baseline)
    log.info("%s baseline (logistic): %s", asset, base_metrics.row())

    lgbm_metrics, oof_p, oof_y = walk_forward(df, _make_lgbm)
    log.info("%s lightgbm raw: %s", asset, lgbm_metrics.row())

    calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.02, y_max=0.98)
    calibrator.fit(oof_p, oof_y)
    cal_metrics = _score(oof_y, calibrator.predict(oof_p))
    log.info("%s lightgbm calibrated (OOF): %s", asset, cal_metrics.row())

    # Reliability curve: predicted-bucket vs realized frequency.
    buckets = np.clip(((calibrator.predict(oof_p)) * 10).astype(int), 0, 9)
    reliability = []
    for b in range(10):
        mask = buckets == b
        if mask.sum() >= 20:
            reliability.append({"bucket": (b + 0.5) / 10,
                                "predicted": float(calibrator.predict(oof_p)[mask].mean()),
                                "actual": float(oof_y[mask].mean()),
                                "n": int(mask.sum())})

    final = _make_lgbm()
    final.fit(df[FEATURE_COLUMNS].astype(float), df["_label"].to_numpy(dtype=int))

    version = f"{asset}-{time.strftime('%Y%m%d%H%M', time.gmtime())}"
    bundle = {
        "version": version, "asset": asset, "model": final,
        "calibrator": calibrator, "feature_columns": FEATURE_COLUMNS,
        "metrics": cal_metrics.row(), "baseline": base_metrics.row(),
        "raw": lgbm_metrics.row(), "reliability": reliability,
        "trained_at": int(time.time()), "train_rows": len(df),
    }
    joblib.dump(bundle, config.MODELS_DIR / f"{asset}.joblib")
    if register:
        storage.register_model({
            "version": version, "asset": asset, "trained_at": bundle["trained_at"],
            "train_rows": len(df), "val_logloss": cal_metrics.logloss,
            "val_brier": cal_metrics.brier, "val_accuracy": cal_metrics.accuracy,
            "notes": f"baseline_acc={base_metrics.accuracy:.4f} "
                     f"raw_brier={lgbm_metrics.brier:.4f}",
        })
    return bundle


def train_all(days: int | None = None) -> dict[str, dict]:
    out = {}
    for asset in config.ASSETS:
        try:
            b = train_asset(asset, days)
            if b:
                out[asset] = b
        except Exception as e:  # noqa: BLE001
            log.error("%s training failed: %s", asset, e)
    return out


# --------------------------------------------------------------- predict ----

class ModelStore:
    """Loads and caches the promoted model bundle per asset."""

    def __init__(self) -> None:
        self._bundles: dict[str, dict] = {}
        self._mtimes: dict[str, float] = {}

    def get(self, asset: str) -> dict | None:
        path = config.MODELS_DIR / f"{asset}.joblib"
        if not path.exists():
            return None
        mtime = path.stat().st_mtime
        if self._mtimes.get(asset) != mtime:
            try:
                self._bundles[asset] = joblib.load(path)
                self._mtimes[asset] = mtime
            except Exception as e:  # noqa: BLE001
                log.error("%s model load failed: %s", asset, e)
                return self._bundles.get(asset)
        return self._bundles.get(asset)

    def predict_prob_up(self, asset: str, feats: dict[str, float]) -> tuple[float, str] | None:
        b = self.get(asset)
        if b is None:
            return None
        x = pd.DataFrame([[feats.get(c, 0.0) for c in b["feature_columns"]]],
                         columns=b["feature_columns"], dtype=float)
        raw = float(b["model"].predict_proba(x)[0, 1])
        cal = float(b["calibrator"].predict([raw])[0])
        return round(min(max(cal, 0.02), 0.98), 4), b["version"]


def metrics_table() -> str:
    lines = [f"{'asset':<6} {'rows':>6} {'base_acc':>9} {'wf_acc':>7} "
             f"{'brier':>7} {'logloss':>8}  version"]
    for asset in config.ASSETS:
        path = config.MODELS_DIR / f"{asset}.joblib"
        if not path.exists():
            lines.append(f"{asset:<6} {'—':>6}  (no model trained)")
            continue
        b = joblib.load(path)
        m, base = b["metrics"], b["baseline"]
        lines.append(
            f"{asset:<6} {b['train_rows']:>6} {base['accuracy']:>9.4f} "
            f"{m['accuracy']:>7.4f} {m['brier']:>7.4f} {m['logloss']:>8.4f}  "
            f"{b['version']}")
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", action="store_true")
    parser.add_argument("--asset", default=None)
    parser.add_argument("--days", type=int, default=None)
    args = parser.parse_args()
    logging.basicConfig(level=config.LOG_LEVEL,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    storage.init_db()
    if args.train:
        if args.asset:
            train_asset(args.asset.upper(), args.days)
        else:
            train_all(args.days)
    print(metrics_table())
    print("\nNote: ~52% walk-forward accuracy is expected — any edge comes from"
          "\ncalibrated disagreement with Kalshi prices on specific windows,"
          "\nnot raw accuracy.")
