"""Regressions found on the first live run (2026-07-04): doubleheader
duplicates, misattributed model inputs after EV sorting, and same-player
slip legs."""

import json
from pathlib import Path

import pytest

from src import db
from src.engine import correlation as corr
from src.engine import value_scanner as vs
from src.engine.correlation import Leg
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


def test_scan_dedupes_doubleheader_candidates(conn):
    cand = {"sport": "baseball_mlb", "event_id": EVENT,
            "market": "pitcher_strikeouts", "player": "Gerrit Cole",
            "side": "over", "model_prob": 0.57, "sample_games": 6}
    edges = vs.scan(conn, [cand, dict(cand)])       # same market twice
    assert len(edges) == 1


def test_scan_attaches_inputs_to_the_right_edge(conn):
    # two candidates whose EV order REVERSES their input order
    weak = {"sport": "baseball_mlb", "event_id": EVENT,
            "market": "pitcher_strikeouts", "player": "Gerrit Cole",
            "side": "under", "model_prob": 0.50, "sample_games": 6,
            "_inputs": {"who": "under-inputs"}}
    strong = {"sport": "baseball_mlb", "event_id": EVENT,
              "market": "pitcher_strikeouts", "player": "Gerrit Cole",
              "side": "over", "model_prob": 0.60, "sample_games": 6,
              "_inputs": {"who": "over-inputs"}}
    edges = vs.scan(conn, [weak, strong])           # scan sorts by EV desc
    by_side = {e.side: e for e in edges}
    assert by_side["over"].inputs["_inputs"]["who"] == "over-inputs"
    assert by_side["under"].inputs["_inputs"]["who"] == "under-inputs"


def test_slip_rejects_same_player_same_market_twice():
    leg = Leg(event_id="g1", market="pitcher_strikeouts", player="Hunter Brown",
              side="under", line=5.5, model_prob=0.8)
    ok, notes = corr.validate_slip([leg, Leg(**{**leg.__dict__})])
    assert not ok
    assert "duplicate leg" in notes[0]


def test_build_slips_dedupes_edge_list():
    class E:
        def __init__(self, player, market, prob, event="g1", side="over"):
            self.event_id, self.market, self.player = event, market, player
            self.side, self.line, self.model_prob = side, 5.5, prob
            self.surface = True

    edges = [E("Hunter Brown", "pitcher_strikeouts", 0.8),
             E("Hunter Brown", "pitcher_strikeouts", 0.7),   # duplicate market
             E("Other Guy", "player_points", 0.62, event="g2")]
    slips = corr.build_slips(edges)
    for s in slips:
        players = [(l.player, l.market) for l in s["legs"]]
        assert len(players) == len(set(players)), "same player+market paired with itself"


def test_unsupported_market_401_does_not_crash(conn, monkeypatch):
    """Run #2 died on a 401 for WC player props (not in the free plan)."""
    monkeypatch.setenv("ODDS_API_KEY", "test-key")

    class FakeResp:
        status_code = 401
        headers = {}

        def json(self):
            return {}

    from src.ingest.odds import OddsAPIClient
    client = OddsAPIClient.__new__(OddsAPIClient)
    client.base_url, client.timeout = "https://x", 1
    client.max_retries, client.backoff = 1, 0
    client.api_key = "test-key"

    class FakeSession:
        def get(self, *a, **k):
            return FakeResp()

    client.session = FakeSession()
    assert client._get(conn, "/sports/soccer/events/e1/odds") is None  # no raise
