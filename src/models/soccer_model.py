"""Soccer prop models: shots, SOT, goals, cards, corners (spec §3).

BUILD PHASE 5 — scaffold only (spec §9). Not yet implemented.

Shots/SOT: per-90 x minutes x suppression x game state. Anytime scorer:
xG/90 x minutes x finishing regression -> Poisson. Cards: foul rate x ref x tension.
"""

from __future__ import annotations


def not_built() -> None:
    raise NotImplementedError(__doc__)
