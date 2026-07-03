"""Staking math: Kelly, caps, tiers, paper gate, drawdown stop (spec §5, §10)."""

import pytest

from src import db
from src.engine import staking


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "test.sqlite")
    yield c
    c.close()


def test_kelly_known_values():
    # p=0.55 at even money: f* = (1*0.55 - 0.45)/1 = 0.10
    assert staking.kelly_fraction(0.55, 2.0) == pytest.approx(0.10)
    # p=0.60 at -150 (dec 1.6667): b=.6667 -> (.6667*.6-.4)/.6667 = 0.0
    assert staking.kelly_fraction(0.60, 1.6667) == pytest.approx(0.0, abs=1e-3)
    # negative edge floors at zero
    assert staking.kelly_fraction(0.40, 2.0) == 0.0


def test_stake_fraction_quarter_kelly_and_cap():
    # quarter of 10% = 2.5%, capped at 2%
    assert staking.stake_fraction(0.55, 2.0) == pytest.approx(0.02)
    # small edge: quarter kelly under the cap passes through
    f = staking.stake_fraction(0.52, 2.0)
    assert f == pytest.approx(0.25 * 0.04, abs=1e-6)
    # tier multiplier scales down
    assert staking.stake_fraction(0.52, 2.0, tier_multiplier=0.3) == pytest.approx(0.25 * 0.04 * 0.3)


def test_paper_gate_active_until_200_positive_clv(conn):
    assert staking.paper_gate_active(conn)  # empty ledger -> paper
    # simulate 250 tracked picks with positive CLV
    conn.execute("""INSERT INTO picks (created_at, sport, event_id, market, side,
                    book, odds_american, odds_decimal, model_prob, market_fair_prob,
                    ev_pct, status) VALUES ('2026-01-01','x','e','m','over','b',
                    100, 2.0, 0.5, 0.5, 0.0, 'won')""")
    pick_id = conn.execute("SELECT pick_id FROM picks").fetchone()[0]
    conn.executemany(
        "INSERT INTO clv_log (pick_id, open_odds_american, clv_pct, captured_at) "
        "VALUES (?, 100, 0.02, '2026-01-01')", [(pick_id,)] * 250)
    conn.commit()
    assert not staking.paper_gate_active(conn)


def test_drawdown_stop_triggers_track_only(conn):
    conn.execute("INSERT INTO bankroll_history (recorded_at, bankroll, change, reason) "
                 "VALUES ('2026-01-02', 800, -200, 'losses')")  # -20% off 1000 peak
    conn.commit()
    assert not staking.drawdown_check(conn)
    # and it persists via system_state for the 7-day window
    assert not staking.drawdown_check(conn)


class FakeEdge:
    def __init__(self, **kw):
        self.surface = kw.get("surface", True)
        self.tier = kw.get("tier", "B")
        self.needs_research = kw.get("needs_research", False)
        self.model_prob = kw.get("model_prob", 0.57)
        self.odds_decimal = kw.get("odds_decimal", 1.87)


def test_apply_stakes_by_tier(conn):
    stakes = staking.apply(conn, [FakeEdge(tier="B"), FakeEdge(surface=False, tier=None)])
    assert stakes[0][0] > 0
    assert stakes[0][1] is True          # paper mode
    assert stakes[1][0] == 0.0           # not surfaced -> track only


def test_apply_research_flag_caps_at_c_sizing(conn):
    plain = staking.apply(conn, [FakeEdge(tier="A", model_prob=0.62)])[0][0]
    flagged = staking.apply(conn, [FakeEdge(tier="A", model_prob=0.62,
                                            needs_research=True)])[0][0]
    assert flagged < plain


def test_apply_respects_daily_exposure_cap(conn):
    edges = [FakeEdge(tier="A", model_prob=0.65, odds_decimal=2.1) for _ in range(6)]
    stakes = staking.apply(conn, edges)
    assert sum(s for s, _ in stakes.values()) <= 6.0 + 1e-9   # 6% of bankroll in units
