"""
Tests for the keyless pricing path.

This is the path that must never break: no key, no network, no excuses.
"""

import json

import pytest

from lib import manual as M
from lib.fetch_odds import rank_plays


@pytest.fixture
def board_file(tmp_path):
    board = {
        "event": "Kansas City Chiefs @ Buffalo Bills",
        "sport": "americanfootball_nfl",
        "note": "researched via WebSearch",
        "markets": [{
            "name": "moneyline",
            "books": {
                "pinnacle": {"Chiefs": 118, "Bills": -128},
                "draftkings": {"Chiefs": 132, "Bills": -155},
                "fanduel": {"Chiefs": 115, "Bills": -136},
                "betmgm": {"Chiefs": 120, "Bills": -140},
            },
        }],
    }
    p = tmp_path / "board.json"
    p.write_text(json.dumps(board))
    return p


# --- the template is real, runnable input --------------------------------


def test_template_round_trips_through_the_engine(tmp_path):
    p = tmp_path / "t.json"
    p.write_text(json.dumps(M.TEMPLATE))
    views = M.board_to_views(M.load_board(p))
    assert views
    assert all(v.quotes for v in views)


# --- parsing and error messages ------------------------------------------


def test_missing_file_names_itself(tmp_path):
    with pytest.raises(M.BoardError) as e:
        M.load_board(tmp_path / "nope.json")
    assert "no such board file" in str(e.value)


def test_bad_json_says_so(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json")
    with pytest.raises(M.BoardError) as e:
        M.load_board(p)
    assert "not valid JSON" in str(e.value)


def test_missing_markets_key_points_at_the_template(tmp_path):
    p = tmp_path / "x.json"
    p.write_text('{"event": "a"}')
    with pytest.raises(M.BoardError) as e:
        M.load_board(p)
    assert "lib.manual template" in str(e.value)


def test_non_numeric_price_is_located_precisely(tmp_path):
    p = tmp_path / "x.json"
    p.write_text(json.dumps({"markets": [
        {"name": "ml", "books": {"pinnacle": {"A": "even"}}}]}))
    with pytest.raises(M.BoardError) as e:
        M.board_to_views(M.load_board(p))
    msg = str(e.value)
    assert "ml" in msg and "pinnacle" in msg and "not a number" in msg


def test_empty_market_rejected(tmp_path):
    p = tmp_path / "x.json"
    p.write_text(json.dumps({"markets": [{"name": "ml", "books": {}}]}))
    with pytest.raises(M.BoardError):
        M.board_to_views(M.load_board(p))


def test_book_names_normalize():
    views = M.board_to_views({"markets": [
        {"name": "ml", "books": {"Draft Kings": {"A": -110, "B": -110}}}]})
    assert views[0].quotes["A"][0].book == "draftkings"


# --- it produces the SAME result as the live feed -------------------------


def test_hand_built_board_finds_the_same_edge(board_file):
    """A manual board is a first-class board — identical engine, identical answer."""
    views = M.board_to_views(M.load_board(board_file))
    plays = rank_plays(views)
    assert plays, "expected an edge"
    top = plays[0]
    assert top["side"] == "Chiefs"
    assert top["book"] == "draftkings"
    assert top["ev"] == pytest.approx(0.0398, abs=2e-3)
    assert top["anchor"] == "pinnacle"


def test_anchor_is_never_also_the_bet(board_file):
    views = M.board_to_views(M.load_board(board_file))
    assert all(p["book"] != p["anchor"] for p in rank_plays(views))


# --- the audit catches silent failures ------------------------------------


def test_audit_flags_a_one_sided_market():
    views = M.board_to_views({"markets": [
        {"name": "spread", "books": {"draftkings": {"Chiefs -2.5": -110}}}]})
    a = M.audit_board(views)[0]
    assert a["one_sided"] is True
    assert a["devig_possible"] is False


def test_audit_flags_no_sharp_anchor():
    views = M.board_to_views({"markets": [
        {"name": "ml", "books": {
            "draftkings": {"A": -110, "B": -110},
            "fanduel": {"A": -105, "B": -115}}}]})
    a = M.audit_board(views)[0]
    assert a["has_sharp"] is False
    assert a["devig_possible"] is True


def test_audit_reports_sharp_anchor_when_present(board_file):
    a = M.audit_board(M.board_to_views(M.load_board(board_file)))[0]
    assert a["has_sharp"] and a["sharp_anchor"] == "pinnacle"
    assert set(a["soft_books_available"]) == {"draftkings", "fanduel", "betmgm"}


# --- CLI smoke ------------------------------------------------------------


def test_cli_board_runs(board_file, capsys):
    assert M.main(["board", str(board_file)]) == 0
    out = capsys.readouterr().out
    assert "Chiefs" in out and "EDGE" in out


def test_cli_devig_rejects_mismatched_labels(capsys):
    assert M.main(["devig", "--labels", "A,B,C", "--prices", "-110", "-110"]) == 2


def test_cli_shop_rejects_bad_format(capsys):
    assert M.main(["shop", "--prices", "pinnacle-182"]) == 2


def test_cli_board_reports_error_not_traceback(tmp_path, capsys):
    p = tmp_path / "bad.json"
    p.write_text("{")
    assert M.main(["board", str(p)]) == 1
    assert "BOARD ERROR" in capsys.readouterr().out
