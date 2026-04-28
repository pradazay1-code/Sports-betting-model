"""Pradapicks public API."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .bootstrap import kick_off_bootstrap_if_needed
from .config import get_settings
from .db import Pick, SessionLocal, init_db
from .ingest import backfill_box_scores, ingest_box_scores, ingest_odds
from .models.trainer import train_all
from .picks import generate_daily_picks
from .scheduler import start_scheduler
from .tracker import grade_picks, progress_report
from .betslip import analyze_slip

logging.basicConfig(level=get_settings().log_level)
log = logging.getLogger("pradapicks")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    kick_off_bootstrap_if_needed(days=get_settings().auto_bootstrap_days)
    sched = start_scheduler()
    try:
        yield
    finally:
        if sched:
            sched.shutdown(wait=False)


app = FastAPI(
    title="Pradapicks",
    version="0.1.0",
    description="AI-driven prop scoring for MLB / NBA / NHL",
    lifespan=lifespan,
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_token(authorization: Optional[str] = Header(None)) -> None:
    settings = get_settings()
    if not settings.api_auth_token or settings.api_auth_token == "dev-token":
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    if authorization.split(" ", 1)[1] != settings.api_auth_token:
        raise HTTPException(status_code=403, detail="bad token")


@app.get("/health")
def health(db: Session = Depends(get_db)):
    from .db import PlayerGameStat, ModelArtifact, PropOffer
    n_player_rows = db.query(PlayerGameStat).count()
    n_models = db.query(ModelArtifact).filter(ModelArtifact.is_active.is_(True)).count()
    n_offers_today = db.query(PropOffer).filter(PropOffer.game_date == date.today()).count()
    n_picks_today = db.query(Pick).filter(Pick.pick_date == date.today()).count()
    bootstrapping = n_player_rows == 0
    return {
        "ok": True,
        "service": "pradapicks",
        "bootstrapping": bootstrapping,
        "player_rows": n_player_rows,
        "active_models": n_models,
        "offers_today": n_offers_today,
        "picks_today": n_picks_today,
    }


@app.get("/picks/today")
def picks_today(
    sport: Optional[str] = Query(None, pattern="^(MLB|NBA|NHL)$"),
    db: Session = Depends(get_db),
):
    today = date.today()
    q = db.query(Pick).filter(Pick.pick_date == today)
    if sport:
        q = q.filter(Pick.sport == sport)
    rows = q.order_by(Pick.rating.desc()).all()
    return {"date": today.isoformat(), "count": len(rows), "picks": [_pick_dict(p) for p in rows]}


@app.get("/picks")
def picks_for_date(
    on: date = Query(...),
    sport: Optional[str] = Query(None, pattern="^(MLB|NBA|NHL)$"),
    db: Session = Depends(get_db),
):
    q = db.query(Pick).filter(Pick.pick_date == on)
    if sport:
        q = q.filter(Pick.sport == sport)
    rows = q.order_by(Pick.rating.desc()).all()
    return {"date": on.isoformat(), "count": len(rows), "picks": [_pick_dict(p) for p in rows]}


@app.post("/picks/generate", dependencies=[Depends(require_token)])
def picks_generate(
    on: Optional[date] = None,
    top_n: Optional[int] = None,
    db: Session = Depends(get_db),
):
    rows = generate_daily_picks(db, on=on or date.today(), top_n=top_n)
    return {"count": len(rows), "picks": [_pick_dict(p) for p in rows]}


class BetSlipLeg(BaseModel):
    sport: str = Field(..., pattern="^(MLB|NBA|NHL|mlb|nba|nhl)$")
    player_name: str
    market: str
    line: float
    side: str = Field(..., pattern="^(over|under|Over|Under|OVER|UNDER)$")
    price_american: int
    opponent: Optional[str] = None
    is_home: Optional[bool] = None


class BetSlipRequest(BaseModel):
    legs: list[BetSlipLeg]
    book: Optional[str] = None
    submitted_by: Optional[str] = None


@app.post("/betslip/analyze")
def betslip_analyze(req: BetSlipRequest, db: Session = Depends(get_db)):
    if not req.legs:
        raise HTTPException(status_code=400, detail="legs required")
    return analyze_slip(
        db,
        legs=[l.model_dump() for l in req.legs],
        book=req.book,
        submitted_by=req.submitted_by,
    )


@app.get("/progress")
def progress(days: int = 30, db: Session = Depends(get_db)):
    return progress_report(db, days=days)


@app.post("/admin/ingest/odds", dependencies=[Depends(require_token)])
def admin_ingest_odds(on: Optional[date] = None, db: Session = Depends(get_db)):
    n = ingest_odds(db, on=on or date.today())
    return {"ingested": n}


@app.post("/admin/ingest/box", dependencies=[Depends(require_token)])
def admin_ingest_box(on: Optional[date] = None, db: Session = Depends(get_db)):
    return ingest_box_scores(db, on=on or (date.today() - timedelta(days=1)))


@app.post("/admin/ingest/backfill", dependencies=[Depends(require_token)])
def admin_backfill(days: int = 30, db: Session = Depends(get_db)):
    return backfill_box_scores(db, days=days)


@app.post("/admin/train", dependencies=[Depends(require_token)])
def admin_train(db: Session = Depends(get_db)):
    return {"results": train_all(db)}


@app.post("/admin/grade", dependencies=[Depends(require_token)])
def admin_grade(on: Optional[date] = None, db: Session = Depends(get_db)):
    return grade_picks(db, on=on)


@app.post("/admin/bootstrap", dependencies=[Depends(require_token)])
def admin_bootstrap(days: int = 30):
    """Force a backfill + train + pick-generation cycle in the background."""
    from .bootstrap import run_bootstrap
    import threading
    threading.Thread(target=run_bootstrap, args=(days,), daemon=True).start()
    return {"status": "started", "days": days}


def _pick_dict(p: Pick) -> dict:
    return {
        "id": p.id,
        "pick_date": p.pick_date.isoformat(),
        "sport": p.sport,
        "player_name": p.player_name,
        "team": p.team,
        "opponent": p.opponent,
        "market": p.market,
        "line": p.line,
        "side": p.side,
        "book": p.book,
        "price_american": p.price_american,
        "model_prob": round(p.model_prob, 4),
        "implied_prob": round(p.implied_prob, 4),
        "edge_pct": round(p.edge_pct, 3),
        "rating": p.rating,
        "kelly_unit": round(p.kelly_unit, 4),
        "rationale": p.rationale,
        "result": p.result,
        "actual_value": p.actual_value,
    }
