"""Source providers — all free, no paid API keys.

Each module exposes:
  fetch_schedule(date)         -> list[dict]  (game rows)
  fetch_box_scores(date)       -> list[dict]  (player_game_stats rows)

Odds modules expose:
  fetch_offers()               -> list[dict]  (prop_offers rows)
"""
