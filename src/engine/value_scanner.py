"""Value engine: model prob vs de-vigged market -> EV ranking (spec §5).

BUILD PHASE 2 — scaffold only (spec §9). Not yet implemented.

De-vig two-way markets (p_fair = p_over/(p_over+p_under)), EV% = prob x payout - 1,
tier A/B/C assignment, sharp/soft confidence adjustment vs Pinnacle.
"""

from __future__ import annotations


def not_built() -> None:
    raise NotImplementedError(__doc__)
