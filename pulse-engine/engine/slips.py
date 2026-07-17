"""Real-time slip detection: spot has moved, the Kalshi quote hasn't.

Kalshi's 15-minute crypto quotes reprice seconds behind spot. A "slip" is a
measurable dislocation: given how far spot moved since the current quote was
fetched, the Brownian fair value says the quote *should* have repriced by N
points — and hasn't yet. The scanner computes this every pass from the tick
buffer; the dashboard's LIVE PLAYS panel surfaces it as it happens.

This is a pure-math module (no I/O) so it is fully unit-testable.
"""
from __future__ import annotations

from dataclasses import dataclass

import config
from engine import gbm


@dataclass
class Slip:
    quote_age_s: float
    spot_move_pct: float          # spot move since the quote was fetched
    expected_repricing_pts: float  # how far fair value moved (prob points)
    flagged: bool

    def as_dict(self) -> dict:
        return {"quote_age_s": round(self.quote_age_s, 1),
                "spot_move_pct": round(self.spot_move_pct * 100, 4),
                "expected_repricing_pts": round(self.expected_repricing_pts * 100, 1),
                "flagged": self.flagged}


def assess(win_open: float, spot_at_quote: float | None, spot_now: float | None,
           sigma_s: float, seconds_remaining: float,
           quote_age_s: float) -> Slip | None:
    """Quantify how much the quote should have moved since it was posted.

    Returns None when the inputs aren't there (no ticks / no quote / no
    window open). `flagged` is True when the expected repricing exceeds
    SLIP_ALERT_POINTS and the quote is at least SLIP_MIN_QUOTE_AGE old —
    i.e. the market is visibly lagging spot right now.
    """
    if not win_open or not spot_at_quote or not spot_now or win_open <= 0:
        return None
    fair_then = gbm.prob_up(win_open, spot_at_quote, sigma_s,
                            seconds_remaining + quote_age_s)
    fair_now = gbm.prob_up(win_open, spot_now, sigma_s, seconds_remaining)
    delta = fair_now - fair_then
    move = spot_now / spot_at_quote - 1.0
    flagged = (abs(delta) >= config.SLIP_ALERT_POINTS
               and quote_age_s >= config.SLIP_MIN_QUOTE_AGE)
    return Slip(quote_age_s=quote_age_s, spot_move_pct=move,
                expected_repricing_pts=delta, flagged=flagged)
