"""Training orchestrator: builds X/y per (sport, market) and fits a PropModel."""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import ModelArtifact
from ..features import build_training_frame
from ..data import PROVIDERS
from .prop_model import PropModel

log = logging.getLogger(__name__)


def train_market(db: Session, sport: str, market: str, min_rows: int = 200) -> dict:
    X, y = build_training_frame(db, sport, market)
    if len(X) < min_rows:
        return {"sport": sport, "market": market, "skipped": True, "rows": int(len(X))}

    model = PropModel(sport=sport, market=market)
    metrics = model.fit(X, y)

    settings = get_settings()
    version = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    path = model.save(settings.artifacts_dir / sport)

    db.query(ModelArtifact).filter(
        ModelArtifact.sport == sport,
        ModelArtifact.market == market,
        ModelArtifact.is_active.is_(True),
    ).update({"is_active": False})
    db.add(ModelArtifact(
        sport=sport,
        market=market,
        version=version,
        path=str(path),
        metrics=metrics.to_dict(),
        is_active=True,
    ))
    db.commit()
    log.info("trained %s/%s rows=%d mae=%.3f", sport, market, metrics.n, metrics.mae)
    return {"sport": sport, "market": market, "rows": metrics.n, "metrics": metrics.to_dict()}


def train_all(db: Session) -> list[dict]:
    out: list[dict] = []
    for sport, provider_cls in PROVIDERS.items():
        for market in provider_cls().supported_markets:
            try:
                out.append(train_market(db, sport, market))
            except Exception as e:
                log.exception("train failed %s/%s: %s", sport, market, e)
                out.append({"sport": sport, "market": market, "error": str(e)})
    return out


def load_active_model(db: Session, sport: str, market: str) -> PropModel | None:
    art = (
        db.query(ModelArtifact)
        .filter(ModelArtifact.sport == sport, ModelArtifact.market == market, ModelArtifact.is_active.is_(True))
        .order_by(ModelArtifact.trained_at.desc())
        .first()
    )
    if not art:
        return None
    try:
        from pathlib import Path
        return PropModel.load(Path(art.path))
    except Exception as e:
        log.warning("load model failed %s/%s: %s", sport, market, e)
        return None
