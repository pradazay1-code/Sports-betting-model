"""Scanner semantics: one pick per window, entry cutoffs, NO PLAY finalize."""
import time

import numpy as np
import pytest

import config


@pytest.fixture()
def db(tmp_path, monkeypatch):
    import storage
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "scan.db")
    monkeypatch.setattr(storage, "_engine", None)
    storage.init_db()
    return storage


def _seed_candles(db, asset: str, end_ts: int, hours: int = 40):
    rng = np.random.default_rng(hash(asset) % 2**31)
    n = hours * 60
    closes = 1000 * np.cumprod(1 + rng.normal(0, 0.0004, n))
    rows = [{"asset": asset, "ts": end_ts - 60 * (n - i), "open": float(closes[i - 1] if i else closes[0]),
             "high": float(closes[i] * 1.0002), "low": float(closes[i] * 0.9998),
             "close": float(closes[i]), "volume": 10.0, "source": "test"}
            for i in range(n)]
    db.upsert_candles(rows)


@pytest.fixture()
def predictor(db, monkeypatch):
    from engine.model import ModelStore
    from engine.predictor import Predictor
    # No trained models -> scanner must fall back to GBM fair value.
    monkeypatch.setattr(ModelStore, "predict_prob_up", lambda self, a, f: None)
    return Predictor()


WSTART = (int(time.time()) // 900) * 900 - 86400  # an aligned past window


def _prep(db):
    for a in config.ASSETS:
        _seed_candles(db, a, WSTART + 900)


def test_no_entries_before_scan_start(db, predictor):
    _prep(db)
    assert predictor.scan(now_ts=WSTART + 30) == []


def test_mid_window_no_edge_writes_nothing(db, predictor):
    _prep(db)
    res = predictor.scan(now_ts=WSTART + 300)
    assert len(res) == len(config.ASSETS)
    # GBM fallback vs no Kalshi quotes -> NO PLAY, but not yet persisted
    assert all(r["pick"] == "NO PLAY" and not r["decided"] for r in res)
    assert db.prediction_for("BTC", WSTART) is None


def test_finalize_writes_no_play_rows(db, predictor):
    _prep(db)
    predictor.scan(now_ts=WSTART + 300)
    predictor.scan(now_ts=WSTART + 900 - config.SCAN_STOP_SECONDS - 5)
    for a in config.ASSETS:
        row = db.prediction_for(a, WSTART)
        assert row is not None and row["pick"] == "NO PLAY"
        assert row["model_version"] == "gbm-fallback"


def test_one_pick_per_window(db, predictor, monkeypatch):
    _prep(db)
    from engine import edge as edge_mod
    # Force a decisive model and a lagging market so edge triggers.
    monkeypatch.setattr(predictor.models, "predict_prob_up",
                        lambda a, f: (0.70, "test-v1"))

    class Q:  # minimal Kalshi cache stand-in
        def __init__(self, wclose):
            self.quotes = {a: type("MQ", (), {
                "yes_bid": 49, "yes_ask": 51, "no_bid": 47, "no_ask": 49,
                "window_close": wclose, "fetched_at": time.time(),
                "implied_up": 0.50, "ticker": "TEST"})() for a in config.ASSETS}
            self.no_market = set()
        def implied_at(self, a, ts): return 0.50

    predictor.kalshi_cache = Q(WSTART + 900)

    # First scan: edge present but unconfirmed -> no row yet.
    r0 = predictor.scan(now_ts=WSTART + 200)
    assert all(not r["decided"] for r in r0)
    assert any("confirmation" in "".join(r["reasons"]) for r in r0)
    assert db.prediction_for("BTC", WSTART) is None

    # Second consecutive scan confirms and commits the pick.
    r1 = predictor.scan(now_ts=WSTART + 220)
    assert all(r["pick"] == edge_mod.UP and r["decided"] for r in r1)
    assert all(r["kelly"]["contracts"] > 0 for r in r1)
    row1 = db.prediction_for("BTC", WSTART)
    assert row1["pick"] == edge_mod.UP and row1["created_at"] == WSTART + 220

    # Further scans in the same window must not create/replace anything.
    predictor.scan(now_ts=WSTART + 400)
    row2 = db.prediction_for("BTC", WSTART)
    assert row2["created_at"] == WSTART + 220


def test_no_entries_after_cutoff(db, predictor, monkeypatch):
    _prep(db)
    monkeypatch.setattr(predictor.models, "predict_prob_up",
                        lambda a, f: (0.70, "test-v1"))
    # Inside the finalize band: even a huge edge must land as NO PLAY.
    res = predictor.scan(now_ts=WSTART + 900 - config.SCAN_STOP_SECONDS - 5)
    row = db.prediction_for("BTC", WSTART)
    assert row is not None and row["pick"] == "NO PLAY"


def test_interrupted_streak_resets(db, predictor, monkeypatch):
    _prep(db)
    probs = iter([(0.70, "v"), (0.50, "v"), (0.70, "v")])
    monkeypatch.setattr(predictor.models, "predict_prob_up",
                        lambda a, f: next(probs) if a == "BTC" else (0.5, "v"))

    class Q:
        def __init__(self, wclose):
            self.quotes = {a: type("MQ", (), {
                "yes_bid": 49, "yes_ask": 51, "no_bid": 47, "no_ask": 49,
                "window_close": wclose, "fetched_at": time.time(),
                "implied_up": 0.50, "ticker": "TEST"})() for a in config.ASSETS}
            self.no_market = set()
        def implied_at(self, a, ts): return 0.50

    predictor.kalshi_cache = Q(WSTART + 900)
    predictor.scan(now_ts=WSTART + 200)   # BTC edge (streak 1)
    predictor.scan(now_ts=WSTART + 220)   # BTC no edge -> streak resets
    predictor.scan(now_ts=WSTART + 240)   # BTC edge again (streak 1, not 2)
    assert db.prediction_for("BTC", WSTART) is None
