"""Soccer/World Cup ingest — football-data.org + FBref/Understat (spec §2.2).

BUILD PHASE 5 — scaffold only (spec §9). Not yet implemented.

xG/xA per 90, shots/SOT per 90, set pieces, penalty duty. WC weighting:
club 60% / international last-10 30% / tournament context 10%. Lineup rotation
tracking, referee card tendencies, 90-minute (not 120) grading.
"""

from __future__ import annotations


def not_built() -> None:
    raise NotImplementedError(__doc__)
