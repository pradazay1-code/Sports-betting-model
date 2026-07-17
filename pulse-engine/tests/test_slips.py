"""Slip detection math and the tick buffer that feeds it."""
import config
from collectors.price_collector import LatestCache
from engine import slips


SIGMA = 0.0001  # per sqrt-second


def test_no_slip_when_spot_unmoved():
    s = slips.assess(100.0, 100.05, 100.05, SIGMA, 600, quote_age_s=8)
    assert s is not None and not s.flagged
    assert abs(s.expected_repricing_pts) < config.SLIP_ALERT_POINTS
    assert s.spot_move_pct == 0.0


def test_flagged_when_stale_quote_lags_big_move():
    # Spot jumped +0.25% since the quote was fetched 8s ago near end of window
    s = slips.assess(100.0, 100.0, 100.25, SIGMA, 200, quote_age_s=8)
    assert s is not None and s.flagged
    assert s.expected_repricing_pts > config.SLIP_ALERT_POINTS
    assert s.spot_move_pct > 0


def test_fresh_quote_not_flagged_even_on_move():
    s = slips.assess(100.0, 100.0, 100.25, SIGMA, 200,
                     quote_age_s=config.SLIP_MIN_QUOTE_AGE - 1)
    assert s is not None and not s.flagged


def test_downward_slip_is_negative():
    s = slips.assess(100.0, 100.1, 99.85, SIGMA, 200, quote_age_s=10)
    assert s is not None and s.expected_repricing_pts < 0


def test_missing_inputs_return_none():
    assert slips.assess(None, 100.0, 100.1, SIGMA, 600, 5) is None
    assert slips.assess(100.0, None, 100.1, SIGMA, 600, 5) is None
    assert slips.assess(100.0, 100.0, None, SIGMA, 600, 5) is None


def test_tick_buffer_price_at_and_prune():
    cache = LatestCache()
    t0 = 1_000_000.0
    for i in range(100):
        cache.update("BTC", 100.0 + i, ts=t0 + i)
    assert cache.get("BTC").price == 199.0
    assert cache.price_at("BTC", t0 + 50.5) == 150.0
    assert cache.price_at("BTC", t0 - 1) is None
    # pruning: ticks older than TICK_BUFFER_SECONDS drop off
    cache.update("BTC", 500.0, ts=t0 + config.TICK_BUFFER_SECONDS + 60)
    assert cache.price_at("BTC", t0 + 5) is None
