"""Train every (sport, market) model from data currently in the DB."""

from __future__ import annotations

from app.config import MARKETS
from app.models.prop_model import train
from app.utils import get_logger

LOG = get_logger("trainer")


def train_all() -> dict[str, int]:
    summary: dict[str, int] = {}
    for sport, markets in MARKETS.items():
        for market in markets:
            try:
                tm = train(sport, market)
                summary[f"{sport}/{market}"] = tm.n_train if tm else 0
            except Exception as e:  # noqa: BLE001
                LOG.warning("train %s/%s failed: %s", sport, market, e)
                summary[f"{sport}/{market}"] = 0
    return summary
