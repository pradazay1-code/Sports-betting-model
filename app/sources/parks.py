"""MLB park factors (runs scored, 100 = neutral, source: averages across
Baseball-Reference public 3-year park factors as of 2024-25).

Used as an additive feature for game totals + a small multiplier for batter
markets in inference. Numbers are stable enough not to need a feed; we can
refresh manually once a year.
"""

from __future__ import annotations

PARK_FACTORS = {
    "Coors Field": 112,
    "Globe Life Field": 105,
    "Great American Ball Park": 105,
    "Fenway Park": 104,
    "Camden Yards": 103,
    "Yankee Stadium": 103,
    "Citizens Bank Park": 102,
    "Wrigley Field": 101,
    "Minute Maid Park": 101,
    "Rogers Centre": 101,
    "Target Field": 100,
    "Truist Park": 100,
    "American Family Field": 100,
    "Chase Field": 100,
    "Citi Field": 99,
    "Busch Stadium": 99,
    "Angel Stadium": 99,
    "Nationals Park": 99,
    "Progressive Field": 98,
    "Kauffman Stadium": 98,
    "Dodger Stadium": 97,
    "Comerica Park": 97,
    "Oracle Park": 95,
    "Petco Park": 96,
    "T-Mobile Park": 95,
    "Tropicana Field": 95,
    "loanDepot park": 95,
    "Oakland Coliseum": 95,
    "PNC Park": 97,
}


def factor_for(venue: str | None) -> float:
    if not venue:
        return 1.0
    return PARK_FACTORS.get(venue, 100) / 100.0
