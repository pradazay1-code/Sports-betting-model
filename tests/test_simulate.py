"""Tests for the drive-level game simulator.

The point of simulating drives instead of drawing a margin from a normal is
that points arrive in 3s and 7s. If that structure ever stops showing up in
the output, the sim has quietly become a normal draw and every key-number
number it produces is fiction.
"""

import pytest

from lib.simulate import GameSim, TeamModel, first_half


# --- drive probabilities ---------------------------------------------------


@pytest.mark.parametrize("ppd", [1.4, 1.8, 2.05, 2.6, 3.0])
@pytest.mark.parametrize("share", [0.5, 0.6, 0.7])
def test_drive_probs_reproduce_target_points_per_drive(ppd, share):
    p_td, p_fg = TeamModel("X", ppd, td_share=share).drive_probs()
    assert p_td * 6.95 + p_fg * 3.0 == pytest.approx(ppd, abs=1e-9)


def test_drive_probs_respect_td_share():
    p_td, p_fg = TeamModel("X", 2.2, td_share=0.64).drive_probs()
    assert p_td / (p_td + p_fg) == pytest.approx(0.64, abs=1e-9)


def test_drive_probs_clamp_absurd_efficiency():
    """A team cannot score on more than every drive."""
    p_td, p_fg = TeamModel("X", 99.0).drive_probs()
    assert p_td + p_fg <= 0.95


# --- the simulation itself -------------------------------------------------


def test_seed_makes_it_reproducible():
    a = GameSim(TeamModel("H", 2.1), TeamModel("A", 2.1), seed=11).run(2000)
    b = GameSim(TeamModel("H", 2.1), TeamModel("A", 2.1), seed=11).run(2000)
    assert a.results == b.results


def test_mean_score_tracks_points_per_drive():
    g = GameSim(TeamModel("H", 2.4), TeamModel("A", 1.9), base_drives=11.0, seed=3).run(30000)
    s = g.summary()
    assert s["home_mean"] == pytest.approx(2.4 * 11.0, rel=0.06)
    assert s["away_mean"] == pytest.approx(1.9 * 11.0, rel=0.06)


def test_better_team_is_favored():
    g = GameSim(TeamModel("H", 2.6), TeamModel("A", 1.8), seed=5).run(20000)
    s = g.summary()
    assert s["home_win_prob"] > 0.5
    assert s["fair_spread"] < 0          # negative = home laying points


def test_scores_are_built_from_threes_and_sevens():
    """No score should be reachable only by a continuous draw."""
    g = GameSim(TeamModel("H", 2.1), TeamModel("A", 2.1), seed=9).run(3000)
    for home, away in g.results:
        for pts in (home, away):
            assert pts % 1 == 0
            assert pts not in (1, 2, 4, 5)   # unreachable from 3s, 6s and 7s


def test_key_numbers_beat_their_neighbours():
    """3 and 7 must carry more margin mass than the dead numbers around them."""
    g = GameSim(TeamModel("H", 2.05), TeamModel("A", 2.05), seed=17).run(60000)
    k = g.key_numbers([2, 3, 5, 7, 8, 9])
    assert k[3] > k[2] and k[3] > k[5]
    assert k[7] > k[8] and k[7] > k[9]


# --- push handling ---------------------------------------------------------


def test_pushes_are_excluded_from_cover_probability():
    g = GameSim(TeamModel("H", 2.3), TeamModel("A", 2.0), seed=21).run(20000)
    c = g.p_cover(-3.0)
    assert c["push"] > 0                                     # 3 is reachable
    assert c["home_cover"] + (1 - c["home_cover"]) == pytest.approx(1.0)
    assert c["home_cover"] > c["raw_home"]                   # push shrank the denominator


def test_half_point_line_cannot_push():
    g = GameSim(TeamModel("H", 2.3), TeamModel("A", 2.0), seed=21).run(10000)
    assert g.p_cover(-3.5)["push"] == 0.0
    assert g.p_over(47.5)["push"] == 0.0


def test_cover_probability_falls_as_the_favourite_lays_more():
    g = GameSim(TeamModel("H", 2.4), TeamModel("A", 1.9), seed=31).run(30000)
    probs = [g.p_cover(x)["home_cover"] for x in (-1.5, -3.5, -6.5, -9.5, -13.5)]
    assert probs == sorted(probs, reverse=True)


def test_over_probability_falls_as_the_total_rises():
    g = GameSim(TeamModel("H", 2.2), TeamModel("A", 2.0), seed=33).run(30000)
    probs = [g.p_over(x)["over"] for x in (38.5, 44.5, 50.5, 56.5)]
    assert probs == sorted(probs, reverse=True)


def test_team_total_is_monotonic():
    g = GameSim(TeamModel("H", 2.4), TeamModel("A", 1.9), seed=41).run(20000)
    probs = [g.team_total("home", x) for x in (17.5, 23.5, 29.5, 35.5)]
    assert probs == sorted(probs, reverse=True)


# --- first half ------------------------------------------------------------


def test_first_half_scores_about_half_the_game():
    full = GameSim(TeamModel("H", 2.4), TeamModel("A", 2.0), base_drives=11.0, seed=51)
    half = first_half(full, share=0.49)
    f = full.run(40000).summary()
    h = half.run(40000).summary()
    assert h["total_mean"] / f["total_mean"] == pytest.approx(0.49, abs=0.03)


def test_first_half_keeps_the_favourite_favoured_but_by_less():
    full = GameSim(TeamModel("H", 2.5, td_share=0.62), TeamModel("A", 1.9), base_drives=11.0, seed=53)
    half = first_half(full)
    f = full.run(30000).summary()
    h = half.run(30000).summary()
    assert h["fair_spread"] < 0
    assert abs(h["fair_spread"]) < abs(f["fair_spread"])


def test_drive_floor_scales_with_base_drives():
    """Regression: a fixed floor of 7 handed a half-game sim a full game's drives."""
    half = GameSim(TeamModel("H", 1.0), TeamModel("A", 1.0), base_drives=5.5, seed=61).run(4000)
    assert max(h + a for h, a in half.results) < 60      # impossible on 11 drives at 1.0 ppd
    quarter = GameSim(TeamModel("H", 2.0), TeamModel("A", 2.0), base_drives=2.75, seed=63).run(4000)
    full = GameSim(TeamModel("H", 2.0), TeamModel("A", 2.0), base_drives=11.0, seed=63).run(4000)
    assert quarter.summary()["total_mean"] < 0.45 * full.summary()["total_mean"]


def test_explicit_min_drives_is_respected():
    g = GameSim(TeamModel("H", 2.0), TeamModel("A", 2.0), base_drives=11.0,
                pace_sd=0.5, min_drives=10, seed=71).run(5000)
    # with a floor of 10 drives at ~0.42 scoring rate, a shutout is very rare
    shutouts = sum(1 for h, a in g.results if h == 0)
    assert shutouts / len(g.results) < 0.02


# --- correlation -----------------------------------------------------------


def test_shared_environment_makes_the_total_wider_than_independent_teams():
    """If the two scores were independent, total SD would be sqrt(2)x a team's SD."""
    shared = GameSim(TeamModel("H", 2.1), TeamModel("A", 2.1), env_sd=0.20, seed=81).run(30000)
    solo = GameSim(TeamModel("H", 2.1), TeamModel("A", 2.1), env_sd=0.0, seed=81).run(30000)
    assert shared.summary()["total_sd"] > solo.summary()["total_sd"]


# --- CLI -------------------------------------------------------------------


def test_cli_prints_a_priced_game(capsys):
    from lib.simulate import main

    assert main(["--home", "BUF", "--away", "DET", "--home-points", "28.8",
                 "--away-points", "22.2", "--spread", "-4.5", "--total", "53.5",
                 "--half", "-n", "4000", "--seed", "1"]) == 0
    out = capsys.readouterr().out
    for fragment in ("fair spread", "BUF -4.5", "over 53.5", "key-number mass", "1H:"):
        assert fragment in out


# --- path-dependent sim ----------------------------------------------------


def _paths(home_ppd=2.6, away_ppd=2.0, n=20000, seed=91):
    from lib.simulate import GameSim, TeamModel

    return GameSim(TeamModel("H", home_ppd), TeamModel("A", away_ppd),
                   base_drives=11.0, seed=seed).run_paths(n)


def test_leading_by_k_is_monotonically_decreasing_in_k():
    ps = _paths()
    probs = [ps.p_leads_by("home", k) for k in (3, 7, 10, 14, 21, 28)]
    assert probs == sorted(probs, reverse=True)


def test_leading_at_some_point_beats_winning_outright():
    """The whole point of a live-lead promo: leading by 7 is easier than winning."""
    from lib.simulate import GameSim, TeamModel

    g = GameSim(TeamModel("H", 2.6), TeamModel("A", 2.0), base_drives=11.0, seed=91)
    win = g.run(20000).summary()
    ps = g.run_paths(20000)
    assert ps.p_leads_by("away", 7) > 1 - win["home_win_prob"]
    assert ps.p_leads_by("home", 7) > win["home_win_prob"]


def test_the_underdog_gains_more_from_a_live_lead_trigger():
    """A favourite that goes up 7 was probably winning anyway; a dog was not."""
    from lib.simulate import GameSim, TeamModel

    g = GameSim(TeamModel("H", 2.7), TeamModel("A", 1.9), base_drives=11.0, seed=93)
    win = g.run(30000).summary()
    ps = g.run_paths(30000)
    fav_gain = ps.p_leads_by("home", 7) - win["home_win_prob"]
    dog_gain = ps.p_leads_by("away", 7) - (1 - win["home_win_prob"])
    assert dog_gain > fav_gain


def test_either_team_leading_is_at_least_each_team_alone():
    ps = _paths()
    both = ps.p_either_leads_by(7)
    assert both >= ps.p_leads_by("home", 7)
    assert both >= ps.p_leads_by("away", 7)
    assert both <= 1.0


def test_a_lead_of_zero_is_certain():
    ps = _paths(n=3000)
    assert ps.p_leads_by("home", 0) == 1.0


def test_path_sim_final_scores_match_the_score_model():
    """run_paths must not drift from run() -- same scoring engine, same means."""
    from lib.simulate import GameSim, TeamModel
    import statistics

    g = GameSim(TeamModel("H", 2.4), TeamModel("A", 2.0), base_drives=11.0, seed=95)
    flat = g.run(30000).summary()
    ps = g.run_paths(30000)
    assert statistics.fmean(h for h, _, _, _ in ps.results) == pytest.approx(
        flat["home_mean"], rel=0.05)
    assert statistics.fmean(a for _, a, _, _ in ps.results) == pytest.approx(
        flat["away_mean"], rel=0.05)


def test_lead_curve_returns_every_requested_threshold():
    ps = _paths(n=5000)
    curve = ps.lead_curve("home", [3, 7, 14])
    assert sorted(curve) == [3, 7, 14]
