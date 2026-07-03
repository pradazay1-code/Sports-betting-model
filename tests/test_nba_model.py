"""NBA minutes model + prop projections + correlated PRA MC (spec §10)."""

import pytest

from src.ingest import nba
from src.models import nba_model


def _games(n=12, minutes=34.0, pts=27, reb=7, ast=8, fg3m=3):
    """Synthetic recent-first game log."""
    return [{"player_id": 115, "player_name": "Star Guard", "minutes": minutes,
             "pts": pts, "reb": reb, "ast": ast, "fg3m": fg3m,
             "game_date": f"2026-01-{28 - i:02d}"} for i in range(n)]


def test_parse_minutes_formats():
    assert nba.parse_minutes("34") == 34.0
    assert nba.parse_minutes("34:30") == pytest.approx(34.5)
    assert nba.parse_minutes(None) is None


def test_parse_stat_rows():
    payload = {"data": [{
        "min": "36:12", "pts": 30, "reb": 8, "ast": 9, "fg3m": 4,
        "fga": 22, "fta": 8, "turnover": 3,
        "player": {"id": 115, "first_name": "Star", "last_name": "Guard"},
        "team": {"abbreviation": "LAL"},
        "game": {"id": 1, "date": "2026-01-15T00:00:00Z"},
    }]}
    rows = nba.parse_stat_rows(payload)
    assert rows[0]["minutes"] == pytest.approx(36.2)
    assert rows[0]["player_name"] == "Star Guard"
    assert rows[0]["game_date"] == "2026-01-15"


def test_minutes_model_blowout_trim():
    games = _games()
    base = nba_model.project_minutes(games)
    blowout = nba_model.project_minutes(games, spread=-14.5)
    b2b = nba_model.project_minutes(games, back_to_back=True)
    assert base == pytest.approx(34.0)
    assert blowout == pytest.approx(34.0 * 0.92)
    assert b2b < base
    # injury-driven usage bump raises minutes
    assert nba_model.project_minutes(games, usage_bump=1.06) > base


def test_points_projection_scales_with_minutes():
    games = _games()
    p36 = nba_model.project_stat(games, "player_points", minutes=36.0)
    p28 = nba_model.project_stat(games, "player_points", minutes=28.0)
    assert p36.mean > p28.mean
    assert p36.mean == pytest.approx(27 / 34 * 36, abs=0.5)
    assert 0 < p36.prob_over(26.5) < 1
    assert p36.prob_over(26.5) + p36.prob_under(26.5) == pytest.approx(1.0)


def test_defense_factor_moves_projection():
    games = _games()
    soft = nba_model.project_stat(games, "player_points", 34.0, defense_factor=1.08)
    tough = nba_model.project_stat(games, "player_points", 34.0, defense_factor=0.92)
    assert soft.mean > tough.mean


def test_threes_use_poisson():
    games = _games()
    proj = nba_model.project_stat(games, "player_threes", 34.0)
    assert proj.mean == pytest.approx(3.0, abs=0.2)
    # Poisson mass check: P(over 2.5) with lam 3 is ~0.577
    assert proj.prob_over(2.5) == pytest.approx(0.577, abs=0.03)


def test_small_sample_refused():
    assert nba_model.project_stat(_games(n=3), "player_points", 34.0) is None


def test_pts_reb_correlation_estimated_from_history():
    correlated = [{"pts": 20 + i, "reb": 5 + i, "minutes": 34,
                   "player_id": 1, "game_date": f"2026-01-{i+1:02d}"} for i in range(10)]
    assert nba_model.pts_reb_correlation(correlated) > 0.8
    assert nba_model.pts_reb_correlation(correlated[:4]) == 0.0  # too few


def test_pra_monte_carlo():
    games = _games()
    p = nba_model.prob_over_pra(games, line=41.5, minutes=34.0)
    # mean PRA = 27+7+8 = 42 -> just over 41.5 should be near 50%
    assert 0.40 < p < 0.62
    assert nba_model.prob_over_pra(games, line=60.5, minutes=34.0) < 0.15
