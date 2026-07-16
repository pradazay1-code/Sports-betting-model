"""Tennis total-games projection."""

from __future__ import annotations

import json

from app.models.game_model import predict_for_games, predict_tennis


def _match(best_of):
    return {"game_id": f"TEN-{best_of}", "home_team": "Alcaraz", "away_team": "Sinner",
            "extra": json.dumps({"tour": "atp", "best_of": best_of})}


def test_best_of_three_baseline():
    p = predict_tennis([_match(3)])[0]
    assert p.sport == "TEN"
    assert p.pred_total == 22.5
    assert abs((p.pred_home_score + p.pred_away_score) - p.pred_total) <= 0.2


def test_best_of_five_is_higher():
    p3 = predict_tennis([_match(3)])[0]
    p5 = predict_tennis([_match(5)])[0]
    assert p5.pred_total > p3.pred_total


def test_predict_for_games_routes_tennis():
    preds = predict_for_games("TEN", [_match(3)])
    assert len(preds) == 1 and preds[0].sport == "TEN"
