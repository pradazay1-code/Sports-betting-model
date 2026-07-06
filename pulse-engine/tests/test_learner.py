"""Grading math against a temp database."""
import time

import pytest

import config


@pytest.fixture()
def db(tmp_path, monkeypatch):
    import storage
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(storage, "_engine", None)
    storage.init_db()
    return storage


def _seed_window(db, asset: str, wstart: int, up: bool):
    rows = []
    px = 100.0
    for i in range(15):
        nxt = px + (0.1 if up else -0.1)
        rows.append({"asset": asset, "ts": wstart + 60 * i, "open": px,
                     "high": max(px, nxt), "low": min(px, nxt), "close": nxt,
                     "volume": 1.0, "source": "test"})
        px = nxt
    db.upsert_candles(rows)


def test_grade_pick_correct_and_pnl(db):
    from engine import learner
    now = int(time.time())
    wstart = (now - now % 900) - 1800
    wclose = wstart + 900
    _seed_window(db, "BTC", wstart, up=True)
    pid = db.insert_prediction({
        "asset": "BTC", "window_start": wstart, "window_close": wclose,
        "prob_up": 0.62, "pick": "UP", "kalshi_yes_price_at_signal": 0.55,
        "edge": 0.07, "model_version": "test", "created_at": wstart + 75})
    assert pid is not None
    assert learner.grade_pending(now) == 1
    rows = db.resolved_history(limit=10)
    assert len(rows) == 1
    r = rows[0]
    assert r["actual_direction"] == "UP" and r["correct"] == 1
    fee = config.kalshi_fee_dollars(config.PAPER_CONTRACTS, 0.55)
    expected = config.PAPER_CONTRACTS * (1 - 0.55) - fee
    assert abs(r["paper_pnl"] - expected) < 0.02
    assert abs(r["brier_component"] - (0.62 - 1) ** 2) < 1e-9


def test_grade_no_play_has_zero_pnl_but_brier(db):
    from engine import learner
    now = int(time.time())
    wstart = (now - now % 900) - 1800
    _seed_window(db, "ETH", wstart, up=False)
    db.insert_prediction({
        "asset": "ETH", "window_start": wstart, "window_close": wstart + 900,
        "prob_up": 0.52, "pick": "NO PLAY", "kalshi_yes_price_at_signal": 0.51,
        "edge": 0.001, "model_version": "test", "created_at": wstart + 75})
    learner.grade_pending(now)
    r = db.resolved_history(limit=10)[0]
    assert r["paper_pnl"] == 0.0 and r["correct"] is None
    assert abs(r["brier_component"] - 0.52 ** 2) < 1e-9


def test_duplicate_prediction_ignored(db):
    now = int(time.time())
    wstart = now - now % 900
    row = {"asset": "SOL", "window_start": wstart, "window_close": wstart + 900,
           "prob_up": 0.6, "pick": "UP", "kalshi_yes_price_at_signal": 0.5,
           "edge": 0.1, "model_version": "t", "created_at": now}
    assert db.insert_prediction(row) is not None
    assert db.insert_prediction(row) is None
