"""
Tests for the board -> fair price -> edge pipeline, the cache, and the bet log.

These use fixtures rather than the network, so they run offline and don't burn
API quota.
"""

import pytest

from lib import cache, db
from lib.fetch_odds import (
    confidence_for,
    fair_probabilities,
    find_edges,
    normalize,
    resolve_sport,
)
from lib.fetch_news import compass, wind_relative_to_field


def make_board():
    """Pinnacle sharp on both sides; soft books offering longer prices."""
    return [
        {
            "away_team": "Kansas City Chiefs",
            "home_team": "Buffalo Bills",
            "commence_time": "2026-09-07T20:25:00Z",
            "bookmakers": [
                {
                    "key": "pinnacle",
                    "markets": [
                        {"key": "h2h", "outcomes": [
                            {"name": "Kansas City Chiefs", "price": 118},
                            {"name": "Buffalo Bills", "price": -128}]},
                        {"key": "spreads", "outcomes": [
                            {"name": "Kansas City Chiefs", "price": -104, "point": 2.5},
                            {"name": "Buffalo Bills", "price": -108, "point": -2.5}]},
                        {"key": "totals", "outcomes": [
                            {"name": "Over", "price": -103, "point": 48.5},
                            {"name": "Under", "price": -107, "point": 48.5}]},
                    ],
                },
                {
                    "key": "draftkings",
                    "markets": [
                        {"key": "h2h", "outcomes": [
                            {"name": "Kansas City Chiefs", "price": 132},
                            {"name": "Buffalo Bills", "price": -155}]},
                        {"key": "spreads", "outcomes": [
                            {"name": "Kansas City Chiefs", "price": 100, "point": 2.5},
                            {"name": "Buffalo Bills", "price": -120, "point": -2.5}]},
                    ],
                },
                {
                    "key": "fanduel",
                    "markets": [{"key": "h2h", "outcomes": [
                        {"name": "Kansas City Chiefs", "price": 115},
                        {"name": "Buffalo Bills", "price": -136}]}],
                },
                {
                    "key": "betmgm",
                    "markets": [{"key": "h2h", "outcomes": [
                        {"name": "Kansas City Chiefs", "price": 120},
                        {"name": "Buffalo Bills", "price": -140}]}],
                },
            ],
        }
    ]


# --- normalization ---------------------------------------------------------


def test_sport_aliases_resolve():
    assert resolve_sport("nfl") == "americanfootball_nfl"
    assert resolve_sport("MLB") == "baseball_mlb"
    assert resolve_sport("americanfootball_nfl") == "americanfootball_nfl"


def test_spread_sides_stay_in_one_market():
    """Both sides of a spread carry opposite points but are ONE market.

    Keying on the signed point splits every spread into two one-sided markets
    that can never be devigged — the bug this test exists to prevent.
    """
    views = normalize(make_board(), "americanfootball_nfl")
    keys = sorted(v.key for v in views)
    assert keys == ["h2h", "spreads 2.5", "totals 48.5"]
    spread = next(v for v in views if v.key == "spreads 2.5")
    assert len(spread.quotes) == 2


def test_alternate_numbers_stay_separate():
    """-2.5 and -3 are different markets. Devigging across them buys a key number."""
    board = make_board()
    board[0]["bookmakers"].append(
        {"key": "betrivers", "markets": [{"key": "spreads", "outcomes": [
            {"name": "Kansas City Chiefs", "price": -115, "point": 3.0},
            {"name": "Buffalo Bills", "price": -105, "point": -3.0}]}]}
    )
    views = normalize(board, "americanfootball_nfl")
    assert {"spreads 2.5", "spreads 3"} <= {v.key for v in views}


def test_outcome_names_carry_their_number():
    views = normalize(make_board(), "americanfootball_nfl")
    totals = next(v for v in views if v.key.startswith("totals"))
    assert set(totals.quotes) == {"Over 48.5", "Under 48.5"}


# --- anchoring and fair prices ---------------------------------------------


def test_anchors_on_pinnacle_not_a_soft_book():
    views = normalize(make_board(), "americanfootball_nfl")
    h2h = next(v for v in views if v.key == "h2h")
    fp = fair_probabilities(h2h)
    assert fp["anchor"] == "pinnacle"
    assert fp["anchor_tier"] == "sharp"
    assert fp["method"] == "power"
    assert sum(fp["fair"].values()) == pytest.approx(1.0, abs=1e-9)


def test_fair_price_matches_hand_calculation():
    views = normalize(make_board(), "americanfootball_nfl")
    h2h = next(v for v in views if v.key == "h2h")
    fp = fair_probabilities(h2h)
    assert fp["fair"]["Kansas City Chiefs"] == pytest.approx(0.4482, abs=1e-3)
    assert fp["fair_american"]["Kansas City Chiefs"] == pytest.approx(123.1, abs=0.5)


def test_incomplete_market_is_not_devigged():
    """Half a market cannot be devigged; estimating the missing side is fabrication."""
    board = [{
        "away_team": "A", "home_team": "B", "commence_time": "",
        "bookmakers": [{"key": "draftkings", "markets": [
            {"key": "h2h", "outcomes": [{"name": "A", "price": -110}]}]}],
    }]
    views = normalize(board, "x")
    assert fair_probabilities(views[0]) is None


def test_median_fallback_when_no_sharp_book():
    board = make_board()
    board[0]["bookmakers"] = [b for b in board[0]["bookmakers"] if b["key"] != "pinnacle"]
    views = normalize(board, "americanfootball_nfl")
    fp = fair_probabilities(next(v for v in views if v.key == "h2h"))
    assert fp["anchor"] == "market_median"
    assert fp["anchor_tier"] == "median"


# --- edges -----------------------------------------------------------------


def test_finds_the_real_edge():
    views = normalize(make_board(), "americanfootball_nfl")
    edges = find_edges(views)
    assert edges, "expected at least one edge on this board"
    top = edges[0]
    assert top["side"] == "Kansas City Chiefs"
    assert top["book"] == "draftkings"
    assert top["offered"] == 132
    assert top["ev"] == pytest.approx(0.0399, abs=2e-3)
    assert 0 < top["stake_units"] <= 2.0


def test_anchor_book_is_never_its_own_edge():
    """An 'edge' against the book you anchored on is arithmetic, not a bet."""
    views = normalize(make_board(), "americanfootball_nfl")
    assert all(e["book"] != e["anchor"] for e in find_edges(views))


def test_edges_are_sorted_by_ev():
    views = normalize(make_board(), "americanfootball_nfl")
    evs = [e["ev"] for e in find_edges(views, min_ev=-1.0)]
    assert evs == sorted(evs, reverse=True)


def test_min_ev_threshold_is_enforced():
    views = normalize(make_board(), "americanfootball_nfl")
    assert all(e["ev"] >= 0.02 for e in find_edges(views, min_ev=0.02))
    assert not find_edges(views, min_ev=0.99)


def test_confidence_downgrades_on_median_anchor():
    views = normalize(make_board(), "americanfootball_nfl")
    edge = dict(find_edges(views)[0])
    edge["anchor_tier"] = "median"
    level, why = confidence_for(edge)
    assert level == "low"
    assert "no sharp book" in why


def test_confidence_downgrades_on_implausible_ev():
    views = normalize(make_board(), "americanfootball_nfl")
    edge = dict(find_edges(views)[0])
    edge["ev"] = 0.35
    level, why = confidence_for(edge)
    assert level == "low"
    assert "implausibly large" in why


# --- weather ---------------------------------------------------------------


def test_wind_from_center_field_blows_in():
    assert wind_relative_to_field(40, 40)["effect"] == "in"


def test_wind_from_behind_home_blows_out():
    assert wind_relative_to_field(220, 40)["effect"] == "out"


def test_crosswind_names_where_it_blows_to_not_from():
    r = wind_relative_to_field(130, 40)  # from the right-field side
    assert r["effect"] == "across"
    assert "toward left field" in r["note"]
    r2 = wind_relative_to_field(310, 40)  # from the left-field side
    assert "toward right field" in r2["note"]


def test_compass_points():
    assert (compass(0), compass(90), compass(180), compass(270)) == ("N", "E", "S", "W")
    assert compass(359) == "N"


# --- cache -----------------------------------------------------------------


def test_cache_serves_then_expires(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    calls = []

    def fetch():
        calls.append(1)
        return {"n": len(calls)}

    v1, m1 = cache.get_or_fetch("odds", "k", fetch, ttl=60)
    assert m1["source"] == "live"
    v2, m2 = cache.get_or_fetch("odds", "k", fetch, ttl=60)
    assert m2["source"] == "cache" and v2 == v1 and len(calls) == 1

    v3, m3 = cache.get_or_fetch("odds", "k", fetch, ttl=0)  # forced stale
    assert m3["source"] == "live" and len(calls) == 2


def test_cache_serves_stale_and_labels_it_on_fetch_failure(tmp_path, monkeypatch):
    """Stale-and-labeled beats nothing. Both beat a fabricated number."""
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    cache.get_or_fetch("odds", "k", lambda: {"price": -110}, ttl=60)

    def boom():
        raise RuntimeError("api down")

    value, meta = cache.get_or_fetch("odds", "k", boom, ttl=0)
    assert value == {"price": -110}
    assert meta["degraded"] and meta["stale"]
    assert "live fetch failed" in meta["warning"]


def test_cache_raises_when_there_is_no_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    with pytest.raises(RuntimeError):
        cache.get_or_fetch("odds", "missing", lambda: (_ for _ in ()).throw(RuntimeError("x")))


# --- bet log ---------------------------------------------------------------


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "test.db")
    yield c
    c.close()


def test_schema_creates_cleanly(conn):
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"bets", "parlay_legs", "line_snapshots"} <= tables


def test_log_computes_ev_rather_than_trusting_it(conn):
    bet_id = db.log_bet(
        conn, sport="nfl", event="KC @ BUF", market="h2h", side="KC",
        price_taken=132, book="draftkings", stake_units=0.76, fair_prob=0.4482,
    )
    row = conn.execute("SELECT * FROM bets WHERE id=?", (bet_id,)).fetchone()
    assert row["ev_at_bet"] == pytest.approx(0.0399, abs=1e-3)
    assert row["decimal_taken"] == pytest.approx(2.32, abs=1e-4)
    assert row["result"] == "pending"


def test_grading_derives_profit_from_price(conn):
    bet_id = db.log_bet(conn, sport="nfl", event="e", market="h2h", side="s",
                        price_taken=100, book="dk", stake_units=2.0)
    assert db.grade_bet(conn, bet_id, "win") == pytest.approx(2.0)

    b2 = db.log_bet(conn, sport="nfl", event="e", market="h2h", side="s",
                    price_taken=-110, book="dk", stake_units=1.0)
    assert db.grade_bet(conn, b2, "loss") == pytest.approx(-1.0)

    b3 = db.log_bet(conn, sport="nfl", event="e", market="spread", side="s",
                    price_taken=-110, book="dk", stake_units=1.0)
    assert db.grade_bet(conn, b3, "push") == 0.0


def test_closing_line_records_clv(conn):
    bet_id = db.log_bet(conn, sport="nfl", event="e", market="h2h", side="s",
                        price_taken=-105, book="dk", stake_units=1.0)
    c = db.set_closing_line(conn, bet_id, -125)
    assert c["beat_close"]
    row = conn.execute("SELECT clv_pct FROM bets WHERE id=?", (bet_id,)).fetchone()
    assert row["clv_pct"] > 0


def test_report_leads_with_clv_and_flags_missing_closes(conn):
    a = db.log_bet(conn, sport="nfl", event="a", market="h2h", side="s",
                   price_taken=-110, book="dk", stake_units=1.0, fair_prob=0.55)
    b = db.log_bet(conn, sport="nfl", event="b", market="h2h", side="s",
                   price_taken=-110, book="dk", stake_units=1.0, fair_prob=0.55)
    db.set_closing_line(conn, a, -130)
    db.grade_bet(conn, a, "win")
    db.grade_bet(conn, b, "loss")

    perf = db.performance(conn)
    assert perf["settled_bets"] == 2
    assert perf["record"] == "1-1-0"
    assert perf["clv_sample"] == 1
    assert perf["missing_closing_lines"] == 1
    assert perf["expected_units"] is not None


def test_invalid_result_rejected(conn):
    bet_id = db.log_bet(conn, sport="nfl", event="e", market="h2h", side="s",
                        price_taken=-110, book="dk", stake_units=1.0)
    with pytest.raises(ValueError):
        db.grade_bet(conn, bet_id, "kinda won")


def test_calibration_buckets_and_ignores_pushes(conn):
    for _ in range(3):
        i = db.log_bet(conn, sport="nfl", event="e", market="h2h", side="s",
                       price_taken=-110, book="dk", stake_units=1.0, fair_prob=0.55)
        db.grade_bet(conn, i, "win")
    j = db.log_bet(conn, sport="nfl", event="e", market="h2h", side="s",
                   price_taken=-110, book="dk", stake_units=1.0, fair_prob=0.55)
    db.grade_bet(conn, j, "push")

    rows = db.calibration(conn, bins=5)
    bucket = next(r for r in rows if r["bucket"] == "40%-60%")
    assert bucket["n"] == 3  # the push is excluded — it never resolved
    assert bucket["actual"] == pytest.approx(1.0)


def test_parlay_legs_are_stored_with_the_bet(conn):
    bet_id = db.log_bet(
        conn, sport="nfl", event="parlay", market="parlay", side="2-leg",
        price_taken=264, book="dk", stake_units=0.5,
        legs=[
            {"event": "KC @ BUF", "market": "h2h", "side": "KC", "price": 118, "fair_prob": 0.45},
            {"event": "SF @ SEA", "market": "spreads", "side": "SF -3", "price": -110},
        ],
    )
    legs = conn.execute("SELECT * FROM parlay_legs WHERE bet_id=? ORDER BY leg_index", (bet_id,)).fetchall()
    assert len(legs) == 2
    assert legs[0]["side"] == "KC"


def test_open_bets_excludes_graded(conn):
    a = db.log_bet(conn, sport="nfl", event="a", market="h2h", side="s",
                   price_taken=-110, book="dk", stake_units=1.0)
    db.log_bet(conn, sport="nfl", event="b", market="h2h", side="s",
               price_taken=-110, book="dk", stake_units=1.0)
    db.grade_bet(conn, a, "win")
    assert len(db.open_bets(conn)) == 1


def test_tilt_needs_a_baseline_before_it_accuses(conn):
    assert db.tilt_signals(conn)["enough_data"] is False


# --- ranked plays: win probability vs. edge --------------------------------


def test_rank_plays_reports_both_axes():
    from lib.fetch_odds import rank_plays

    plays = rank_plays(normalize(make_board(), "americanfootball_nfl"))
    assert plays
    p = plays[0]
    assert p["win_prob"] == p["fair_prob"]
    assert "ev" in p and "confidence" in p and "confidence_reason" in p


def test_min_win_prob_filters_to_high_hit_rate_plays():
    """Someone asking for 'high probability' wants this axis, not the EV one."""
    from lib.fetch_odds import rank_plays

    views = normalize(make_board(), "americanfootball_nfl")
    all_plays = rank_plays(views)
    filtered = rank_plays(views, min_win_prob=0.60)
    assert len(filtered) <= len(all_plays)
    assert all(p["win_prob"] >= 0.60 for p in filtered)


def test_ranking_puts_confidence_ahead_of_raw_ev():
    """A 6% edge off a median anchor is worse than a 3% edge off Pinnacle."""
    from lib.fetch_odds import rank_plays

    views = normalize(make_board(), "americanfootball_nfl")
    plays = rank_plays(views, min_ev=-1.0)
    tiers = [p["tier_rank"] for p in plays]
    assert tiers == sorted(tiers), "confidence tier must sort before EV"
    for lo, hi in zip(plays, plays[1:]):
        if lo["tier_rank"] == hi["tier_rank"]:
            assert lo["ev"] >= hi["ev"], "within a tier, EV descends"


def test_empty_board_summary_says_no_plays_plainly():
    from lib.fetch_odds import summarize_board

    s = summarize_board([])
    assert "No plays" in s
    assert "complete answer" in s


def test_summary_warns_when_every_play_is_low_confidence():
    from lib.fetch_odds import summarize_board

    s = summarize_board([{"confidence": "low"}, {"confidence": "low"}])
    assert "low confidence" in s
    assert "unconfirmed" in s
