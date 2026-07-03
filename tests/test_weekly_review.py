"""Weekly review: CLV suspension, calibration shrinkage, variance math (spec §8)."""

import pytest

from src import db
from src.engine import value_scanner as vs
from src.report import weekly_review as wr


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "test.sqlite")
    yield c
    c.close()


def _seed_settled(conn, sport, market, n, win_rate, model_prob=0.58, clv=0.01):
    for i in range(n):
        status = "won" if i < n * win_rate else "lost"
        conn.execute(
            """INSERT INTO picks (created_at, sport, event_id, market, side, book,
               odds_american, odds_decimal, model_prob, market_fair_prob, ev_pct,
               tier, stake_units, status)
               VALUES ('2026-06-01', ?, 'e', ?, 'over', 'dk', -110, 1.909, ?, 0.52,
                       0.05, 'B', 0.6, ?)""", (sport, market, model_prob, status))
        pick_id = conn.execute("SELECT MAX(pick_id) FROM picks").fetchone()[0]
        conn.execute(
            "INSERT INTO clv_log (pick_id, open_odds_american, clv_pct, captured_at) "
            "VALUES (?, -110, ?, '2026-06-02')", (pick_id, clv))
    conn.commit()


def test_clv_audit_suspends_bleeding_category(conn):
    _seed_settled(conn, "basketball_nba", "player_assists", 60, 0.45, clv=-0.02)
    actions = wr.clv_audit(conn)
    assert actions[0]["action"] == "suspended"
    row = conn.execute("SELECT status FROM category_status WHERE market='player_assists'"
                       ).fetchone()
    assert row["status"] == "suspended"


def test_clv_audit_needs_sample_before_suspending(conn):
    _seed_settled(conn, "baseball_mlb", "pitcher_strikeouts", 20, 0.45, clv=-0.02)
    assert wr.clv_audit(conn) == []      # only 20 picks — not enough evidence


def test_suspended_category_blocks_surfacing(conn, tmp_path):
    import json
    from pathlib import Path
    from src.ingest import odds
    payload = json.loads((Path(__file__).parent / "fixtures" / "odds_api_sample.json").read_text())
    odds.ingest_payload(conn, payload, pulled_at="2026-07-03T14:00:00Z")
    conn.execute("INSERT OR REPLACE INTO category_status VALUES "
                 "('baseball_mlb', 'pitcher_strikeouts', 'suspended', 'test', '2026-07-01')")
    conn.commit()
    edge = vs.evaluate(conn, "baseball_mlb", "e912f18a2c3b4d5e6f708192a3b4c5d6",
                       "pitcher_strikeouts", "Gerrit Cole", "over",
                       model_prob=0.60, sample_games=20)
    assert not edge.surface
    assert any("suspended" in n for n in edge.tier_notes)


def test_calibration_factor_shrinks_overconfident_model(conn):
    # model said 58% everywhere; reality 52% -> factor = .02/.08 = 0.25
    _seed_settled(conn, "baseball_mlb", "pitcher_strikeouts", 50, 0.52)
    updated = wr.update_calibration(conn)
    assert updated[0]["factor"] == pytest.approx(0.25, abs=0.03)
    # and the scanner now shrinks incoming probabilities toward 0.5
    assert vs._calibration_factor(conn, "baseball_mlb", "pitcher_strikeouts") < 0.3


def test_calibration_buckets(conn):
    _seed_settled(conn, "baseball_mlb", "pitcher_strikeouts", 40, 0.55)
    buckets = wr.calibration_buckets(conn)
    assert buckets[0]["n"] == 40
    assert buckets[0]["actual"] == pytest.approx(0.55, abs=0.01)


def test_roi_by_segment(conn):
    _seed_settled(conn, "baseball_mlb", "pitcher_strikeouts", 10, 0.6)
    seg = wr.roi_by_segment(conn)
    assert seg[0]["n"] == 10
    # 6 wins x .6u x .909 - 4 losses x .6u = +0.87u
    assert seg[0]["profit_units"] == pytest.approx(0.87, abs=0.05)


def test_losing_week_probability_variance_context():
    p = wr.losing_week_probability(0.55, 20, 1.91)
    assert 0.35 < p < 0.45      # exact normal-approx value ~40.6%
    # a coin-flip bettor loses way more often
    assert wr.losing_week_probability(0.50, 20, 1.91) > p


def test_run_review_writes_report(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(wr.config, "REPO_ROOT", tmp_path)
    _seed_settled(conn, "baseball_mlb", "pitcher_strikeouts", 35, 0.57)
    path = wr.run_review(conn)
    text = open(path).read()
    assert "CLV by segment" in text
    assert "Variance context" in text
    assert "55% bettor" in text
