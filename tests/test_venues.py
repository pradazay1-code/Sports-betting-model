"""Tests for the CFB venue / home-field-advantage database."""

from lib import venues as V


def test_every_venue_has_sane_fields():
    for v in V.VENUES:
        assert v.name and v.team
        assert -90 <= v.lat <= 90 and -180 <= v.lon <= 180
        assert 0 <= v.altitude_ft <= 8000
        assert v.surface in ("grass", "turf")
        assert v.roof in ("open", "dome", "retractable")
        assert 0.0 <= v.hfa <= 5.0, f"{v.team} HFA out of range"


def test_lookup_by_team_and_name_and_substring():
    assert V.find("LSU").team == "LSU"
    assert V.find("lsu").team == "LSU"
    assert V.find("Autzen").team == "Oregon"
    assert V.find("Death Valley") is not None
    assert V.find("Nonexistent Tech") is None


def test_wyoming_is_the_highest_stadium():
    assert V.altitude_venues()[0].team == "Wyoming"
    assert V.find("Wyoming").altitude_ft == 7220


def test_neutral_sites_carry_no_home_edge():
    for v in V.VENUES:
        if v.team == "Neutral":
            assert v.hfa == 0.0


# --- altitude --------------------------------------------------------------


def test_altitude_edge_scales_with_differential():
    assert V.altitude_edge(1000, 500)["points"] == 0.0
    assert V.altitude_edge(3000, 0)["points"] == 0.5
    assert V.altitude_edge(5000, 0)["points"] == 1.0
    assert V.altitude_edge(7220, 20)["points"] == 1.5


def test_altitude_differential_not_raw_elevation():
    """A Colorado team playing at Wyoming is far less disadvantaged than a Florida team."""
    florida = V.altitude_edge(7220, 82)["points"]
    colorado = V.altitude_edge(7220, 5360)["points"]
    assert florida > colorado


def test_altitude_edge_is_monotonic():
    pts = [V.altitude_edge(ft, 0)["points"] for ft in (0, 2500, 4500, 6500)]
    assert pts == sorted(pts)


def test_altitude_flagged_as_a_late_game_effect():
    assert "2nd-half" in V.altitude_edge(7000, 0)["timing"]


# --- combined home edge ----------------------------------------------------


def test_home_edge_separates_crowd_from_altitude():
    e = V.home_edge("Wyoming", "Hawaii")
    assert e["crowd_points"] == 3.0
    assert e["altitude"]["points"] == 1.5
    assert e["total_points"] == 4.5
    assert e["vs_baseline"] == 2.0


def test_home_edge_beats_a_flat_baseline_where_it_should():
    """The whole point: a flat 2.5 is wrong at both ends."""
    tough = V.home_edge("LSU", "Hawaii")["total_points"]
    soft = V.home_edge("UCLA", "USC")["total_points"]
    assert tough > V.FBS_BASELINE_HFA
    assert soft < V.FBS_BASELINE_HFA


def test_unknown_team_falls_back_to_baseline_and_says_so():
    e = V.home_edge("Some Directional State")
    assert e["venue"] is None
    assert e["total_points"] == V.FBS_BASELINE_HFA
    assert e["confidence"] == "low"
    assert "not treat this as a researched number" in e["note"]


def test_fcs_baseline_is_higher_than_fbs():
    assert V.FCS_BASELINE_HFA > V.FBS_BASELINE_HFA
    e = V.home_edge("Unknown FCS School", fcs=True)
    assert e["total_points"] == V.FCS_BASELINE_HFA


def test_confidence_drops_without_an_away_team():
    assert V.home_edge("LSU", "Oregon")["confidence"] == "medium"
    assert V.home_edge("LSU")["confidence"] == "low"


def test_outdoor_venues_excludes_domes():
    outdoor = list(V.outdoor_venues())
    assert all(v.roof == "open" for v in outdoor)
    assert V.find("Carrier Dome") not in outdoor


def test_home_edge_exposes_coords_for_weather():
    lat, lon = V.home_edge("Wyoming", "Hawaii")["coords"]
    assert 41 < lat < 42 and -106 < lon < -105
