"""Aggregator that calls every free book in parallel and merges into store."""

from __future__ import annotations

import concurrent.futures as cf
from typing import Callable

from app.sources import bovada, draftkings, fanduel, pinnacle, prizepicks
from app.store import insert_prop_offers
from app.utils import get_logger

LOG = get_logger("odds")


PROVIDERS: dict[str, Callable[[], list[dict]]] = {
    "prizepicks": prizepicks.fetch_offers,
    "draftkings": draftkings.fetch_offers,
    "fanduel":    fanduel.fetch_offers,
    "bovada":     bovada.fetch_offers,
    "pinnacle":   pinnacle.fetch_offers,
}


def fetch_all() -> dict[str, int]:
    """Fetch every provider concurrently and persist offers.

    Returns a per-provider count of inserted rows.
    """
    counts: dict[str, int] = {}
    with cf.ThreadPoolExecutor(max_workers=len(PROVIDERS)) as ex:
        futs = {ex.submit(fn): name for name, fn in PROVIDERS.items()}
        for fut in cf.as_completed(futs):
            name = futs[fut]
            try:
                rows = fut.result() or []
                inserted = insert_prop_offers(rows)
                counts[name] = inserted
                LOG.info("odds.%s: fetched=%d inserted=%d", name, len(rows), inserted)
            except Exception as e:  # noqa: BLE001
                LOG.warning("odds.%s failed: %s", name, e)
                counts[name] = 0
    return counts
