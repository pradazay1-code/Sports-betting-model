"""MLB prop models: Ks, hits, TBs, HRs, NRFI (spec §3).

BUILD PHASE 2 — scaffold only (spec §9). Not yet implemented.

K props: pitcher K% x opposing lineup K% vs hand x expected batters faced.
NRFI: P(clean 1st A) x P(clean 1st B), park + top-3 lineup adjusted.
"""

from __future__ import annotations


def not_built() -> None:
    raise NotImplementedError(__doc__)
