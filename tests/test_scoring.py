from pradapicks.scoring import rating_from_components


def test_rating_zero_for_no_edge():
    rating, _ = rating_from_components(model_prob=0.5, price_american=-110)
    assert rating < 30


def test_rating_high_for_strong_edge():
    rating, _ = rating_from_components(
        model_prob=0.65, price_american=-110, fair_prob=0.52,
        sample_size=500, market_consensus_count=4,
    )
    assert rating >= 60
