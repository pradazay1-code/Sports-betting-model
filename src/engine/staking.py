"""Fractional Kelly staking + exposure caps — enforced, not advised (spec §5).

BUILD PHASE 3 — scaffold only (spec §9). Not yet implemented.

f = (bp - q)/b x 0.25; caps: 2%/play, 6%/day; -15% drawdown -> track-only
7 days + calibration audit. Paper mode until 200 tracked picks with +CLV.
"""

from __future__ import annotations


def not_built() -> None:
    raise NotImplementedError(__doc__)
