"""NBA prop models: pts/reb/ast/3PM/PRA (spec §3).

BUILD PHASE 4 — scaffold only (spec §9). Not yet implemented.

Chain: minutes model -> usage/role -> per-minute rates -> opponent/pace -> distribution.
PRA via Monte Carlo with correlated components.
"""

from __future__ import annotations


def not_built() -> None:
    raise NotImplementedError(__doc__)
