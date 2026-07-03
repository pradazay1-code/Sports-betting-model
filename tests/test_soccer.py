"""Soccer/WC ingest blending + prop models (spec §10)."""

import pytest

from src import db
from src.ingest import soccer
from src.models import soccer_model as sm


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "test.sqlite")
    yield c
    c.close()


CLUB = {"player": "Kylian Mbappe", "team": "Real Madrid", "context": "club",
        "season": "2025-26", "minutes": 2700, "shots_p90": 4.4, "sot_p90": 2.1,
        "xg_p90": 0.82, "xa_p90": 0.31, "fouls_p90": 0.9, "penalty_duty": 1}
INTL = {"player": "Kylian Mbappe", "team": "France", "context": "intl",
        "season": "2025-26", "minutes": 850, "shots_p90": 3.6, "sot_p90": 1.6,
        "xg_p90": 0.66, "xa_p90": 0.25, "fouls_p90": 1.1, "penalty_duty": 1}
TOURN = {"player": "Kylian Mbappe", "team": "France", "context": "tournament",
         "season": "2025-26", "minutes": 180, "shots_p90": 5.0, "sot_p90": 2.5,
         "xg_p90": 1.0, "xa_p90": 0.2, "fouls_p90": 0.5, "penalty_duty": 1}


def test_parse_matches():
    payload = {"matches": [{
        "id": 501, "utcDate": "2026-07-04T19:00:00Z", "stage": "QUARTER_FINALS",
        "competition": {"name": "FIFA World Cup"}, "status": "TIMED",
        "homeTeam": {"name": "France"}, "awayTeam": {"name": "Brazil"},
        "referees": [{"name": "Strict Ref"}]}]}
    rows = soccer.parse_matches(payload)
    assert rows[0]["match_id"] == "501"
    assert rows[0]["referee"] == "Strict Ref"
    assert rows[0]["stage"] == "QUARTER_FINALS"


def test_wc_blend_60_30_10(conn):
    soccer.store_player_rates(conn, [CLUB, INTL, TOURN])
    blended = soccer.wc_blended_rates(soccer.player_rates(conn, "Kylian Mbappe", "2025-26"))
    expected = 0.6 * 4.4 + 0.3 * 3.6 + 0.1 * 5.0
    assert blended["shots_p90"] == pytest.approx(expected, abs=1e-3)
    assert blended["penalty_duty"] == 1
    assert blended["contexts_used"] == ["club", "intl", "tournament"]


def test_wc_blend_renormalizes_missing_contexts(conn):
    soccer.store_player_rates(conn, [CLUB, INTL])
    blended = soccer.wc_blended_rates(soccer.player_rates(conn, "Kylian Mbappe", "2025-26"))
    expected = (0.6 * 4.4 + 0.3 * 3.6) / 0.9
    assert blended["shots_p90"] == pytest.approx(expected, abs=1e-3)


def test_wc_blend_ignores_tiny_tournament_sample(conn):
    tiny = {**TOURN, "minutes": 45}
    soccer.store_player_rates(conn, [CLUB, INTL, tiny])
    blended = soccer.wc_blended_rates(soccer.player_rates(conn, "Kylian Mbappe", "2025-26"))
    assert "tournament" not in blended["contexts_used"]


def test_wc_blend_requires_club_anchor(conn):
    soccer.store_player_rates(conn, [INTL])
    assert soccer.wc_blended_rates(soccer.player_rates(conn, "Kylian Mbappe", "2025-26")) is None


def test_rotation_risk_trap():
    assert soccer.rotation_risk("GROUP_STAGE", qualification_locked=True)
    assert not soccer.rotation_risk("GROUP_STAGE", qualification_locked=False)
    assert not soccer.rotation_risk("QUARTER_FINALS", qualification_locked=True)


# --------------------------------------------------------------------- model

def _blended():
    return {"player": "Kylian Mbappe", "shots_p90": 4.2, "sot_p90": 2.0,
            "xg_p90": 0.78, "fouls_p90": 0.95, "penalty_duty": 1,
            "contexts_used": ["club", "intl"]}


def test_shots_projection_90_minutes_cap():
    p_90 = sm.project_shots(_blended(), expected_minutes=90)
    p_120 = sm.project_shots(_blended(), expected_minutes=120)   # books grade 90'
    assert p_90.mean == p_120.mean == pytest.approx(4.2, abs=0.01)
    p_60 = sm.project_shots(_blended(), expected_minutes=60)
    assert p_60.mean == pytest.approx(4.2 * 60 / 90, abs=0.01)


def test_chasing_teams_shoot_more():
    dog = sm.project_shots(_blended(), win_prob=0.25)
    fav = sm.project_shots(_blended(), win_prob=0.75)
    assert dog.mean > fav.mean


def test_anytime_scorer_poisson():
    p = sm.prob_anytime_scorer(_blended())
    # lam = 0.78 + 0.05 pen duty -> 1 - e^-0.83 ~ 0.564
    assert p == pytest.approx(0.564, abs=0.01)
    assert sm.prob_anytime_scorer(_blended(), expected_minutes=45) < p


def test_card_probability_ref_and_tension():
    base = sm.prob_card(_blended())
    strict = sm.prob_card(_blended(), referee_cards_per_game=6.0)
    derby = sm.prob_card(_blended(), tension=1.3)
    assert strict > base
    assert derby > base
    assert 0 < base < 0.5
