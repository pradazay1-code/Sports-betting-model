"""Fee math and fee-aware edge decisions."""
import math

import config
from engine import edge


def test_fee_formula_matches_kalshi_schedule():
    # ceil(0.07 * C * P * (1-P)) to the cent
    assert config.kalshi_fee_dollars(1, 0.50) == 0.02      # 0.0175 -> 0.02
    assert config.kalshi_fee_dollars(100, 0.50) == 1.75
    assert config.kalshi_fee_dollars(100, 0.30) == 1.47
    assert config.kalshi_fee_dollars(100, 0.99) == 0.07    # 0.0693 -> 0.07
    assert config.kalshi_fee_dollars(0, 0.5) == 0.0


def test_fee_per_contract_symmetry():
    assert math.isclose(config.kalshi_fee_per_contract(0.4, 100),
                        config.kalshi_fee_per_contract(0.6, 100))


def test_no_play_when_edge_below_fee_plus_buffer():
    # model 56% vs 52/54 quotes: shrunk prob 54.5% -> no edge over the ask
    d = edge.decide(0.56, yes_bid=52, yes_ask=54, buffer=0.03)
    assert d.pick == edge.NO_PLAY
    assert d.implied_up == 0.53


def test_up_pick_when_edge_clears():
    # raw 70% shrinks to 0.53 + 0.5*(0.70-0.53) = 61.5% vs 54c ask
    d = edge.decide(0.70, yes_bid=52, yes_ask=54, buffer=0.03)
    assert d.pick == edge.UP
    assert d.entry_price == 0.54
    assert d.edge > 0.03 + d.fee
    assert math.isclose(d.prob_up, 0.615)
    assert d.raw_prob_up == 0.70
    assert math.isclose(d.edge, 0.615 - 0.54)


def test_down_pick_uses_no_side_pricing():
    # raw P(up)=0.25 shrinks to 0.3575 -> P(down)=0.6425; NO costs 55c
    d = edge.decide(0.25, yes_bid=45, yes_ask=48, buffer=0.03)
    assert d.pick == edge.DOWN
    assert math.isclose(d.entry_price, 0.55)
    assert math.isclose(d.edge, 0.6425 - 0.55)


def test_shrink_kills_marginal_disagreement():
    # Unshrunk this would be a pick (0.62 vs 54c ask); the winner's-curse
    # correction (0.575 decision prob) correctly rejects it.
    d = edge.decide(0.62, yes_bid=52, yes_ask=54, buffer=0.03)
    assert d.pick == edge.NO_PLAY
    assert math.isclose(d.prob_up, 0.575)


def test_confidence_band_forces_no_play():
    # big edge, but the shrunk prob (0.41 + 0.5*0.19 = 0.505) is inside
    # the 45-55 band -> NO PLAY
    d = edge.decide(0.60, yes_bid=40, yes_ask=42, buffer=0.03)
    assert d.pick == edge.NO_PLAY
    assert any("band" in r for r in d.reasons)


def test_no_market_is_no_play():
    d = edge.decide(0.70, yes_bid=None, yes_ask=None)
    assert d.pick == edge.NO_PLAY and d.implied_up is None


def test_paper_pnl_includes_fees():
    n = config.PAPER_CONTRACTS
    win_pnl = edge.paper_pnl(edge.UP, 0.54, won=True)
    lose_pnl = edge.paper_pnl(edge.UP, 0.54, won=False)
    fee = config.kalshi_fee_dollars(n, 0.54)
    assert math.isclose(win_pnl, n * (1 - 0.54) - fee, abs_tol=0.011)
    assert math.isclose(lose_pnl, -n * 0.54 - fee, abs_tol=0.011)
    assert edge.paper_pnl(edge.NO_PLAY, 0.5, won=True) == 0.0
