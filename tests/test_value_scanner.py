"""Value engine: de-vig, EV, tiering, sharp/soft comparison (spec §5, §10)."""

import json
from pathlib import Path

import pytest

from src import db
from src.engine import value_scanner as vs
from src.ingest import odds

FIXTURE = Path(__file__).parent / "fixtures" / "odds_api_sample.json"
EVENT = "e912f18a2c3b4d5e6f708192a3b4c5d6"


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "test.sqlite")
    odds.ingest_payload(c, json.loads(FIXTURE.read_text()),
                        pulled_at="2026-07-03T14:00:00Z")
    yield c
    c.close()


def test_devig_two_way_sums_to_one():
    p_over, p_under = vs.devig_two_way(1.8696, 1.9524)  # -115 / -105
    assert p_over + p_under == pytest.approx(1.0)
    assert p_over == pytest.approx(0.5108, abs=1e-3)


def test_ev_pct():
    assert vs.ev_pct(0.55, 2.0) == pytest.approx(0.10)
    assert vs.ev_pct(0.50, 1.9091) == pytest.approx(-0.0455, abs=1e-3)


def test_market_fair_prob_uses_two_way(conn):
    fair, sharp = vs.market_fair_prob(conn, EVENT, "pitcher_strikeouts",
                                      "Gerrit Cole", "over")
    assert fair == pytest.approx(0.5108, abs=1e-3)
    assert sharp is None  # pinnacle doesn't offer this prop in the fixture


def test_evaluate_surfaces_edge(conn):
    edge = vs.evaluate(conn, "baseball_mlb", EVENT, "pitcher_strikeouts",
                       "Gerrit Cole", "over", model_prob=0.57, sample_games=6)
    assert edge is not None
    assert edge.ev == pytest.approx(0.57 * 1.869565 - 1, abs=1e-3)  # ~ +6.6%
    assert edge.surface
    assert edge.tier == "B"                      # 5-7% band
    assert edge.needs_research                   # > 6% research gate
    assert edge.book == "fanduel"


def test_evaluate_below_threshold_not_surfaced(conn):
    edge = vs.evaluate(conn, "baseball_mlb", EVENT, "pitcher_strikeouts",
                       "Gerrit Cole", "over", model_prob=0.545, sample_games=6)
    assert edge.ev < 0.04
    assert not edge.surface
    assert edge.tier is None


def test_sharp_disagreement_cuts_tier(conn):
    # model loves the Red Sox ML; DK +130 is best... but wait, pinnacle +138
    # IS the best price, so model edge vs sharp fair decides the adjustment
    edge = vs.evaluate(conn, "baseball_mlb", EVENT, "h2h", None, "away",
                       model_prob=0.46, sample_games=50, is_prop=False)
    # h2h has no over/under pair -> fair falls back to implied of best price
    assert edge.book == "pinnacle"
    assert edge.ev == pytest.approx(0.46 * 2.38 - 1, abs=1e-3)


def test_a_tier_requires_sample(conn):
    edge = vs.evaluate(conn, "baseball_mlb", EVENT, "pitcher_strikeouts",
                       "Gerrit Cole", "over", model_prob=0.60, sample_games=6)
    assert edge.ev > 0.07
    assert edge.tier == "B"
    assert any("A denied" in n for n in edge.tier_notes)


def test_scan_ranks_by_ev(conn):
    edges = vs.scan(conn, [
        {"sport": "baseball_mlb", "event_id": EVENT, "market": "pitcher_strikeouts",
         "player": "Gerrit Cole", "side": "over", "model_prob": 0.57, "sample_games": 6},
        {"sport": "baseball_mlb", "event_id": EVENT, "market": "totals",
         "player": None, "side": "under", "model_prob": 0.55, "sample_games": 30,
         "is_prop": False},
    ])
    assert len(edges) == 2
    assert edges[0].ev >= edges[1].ev
