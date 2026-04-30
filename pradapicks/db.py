from datetime import datetime, date
from typing import Optional

from sqlalchemy import (
    create_engine,
    String,
    Integer,
    Float,
    Date,
    DateTime,
    Boolean,
    ForeignKey,
    JSON,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import (
    declarative_base,
    sessionmaker,
    Mapped,
    mapped_column,
    relationship,
    Session,
)

from .config import get_settings


Base = declarative_base()
_settings = get_settings()


def _normalize_db_url(url: str) -> str:
    # Render's managed Postgres exposes "postgres://..." but SQLAlchemy 2.x
    # requires the "postgresql://" scheme. Normalize for portability.
    if url.startswith("postgres://"):
        return "postgresql+psycopg2://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


_db_url = _normalize_db_url(_settings.database_url)
connect_args = {"check_same_thread": False} if _db_url.startswith("sqlite") else {}
engine = create_engine(_db_url, future=True, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def database_kind() -> str:
    if _db_url.startswith("sqlite"):
        return "sqlite"
    if _db_url.startswith("postgresql"):
        return "postgresql"
    return "other"


def is_persistent() -> bool:
    """SQLite on Render's ephemeral filesystem is NOT persistent across
    deploys/restarts. Only Postgres counts as persistent here."""
    return database_kind() == "postgresql"


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


class Player(Base):
    __tablename__ = "players"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sport: Mapped[str] = mapped_column(String(8), index=True)
    external_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    team: Mapped[Optional[str]] = mapped_column(String(64))
    position: Mapped[Optional[str]] = mapped_column(String(16))
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("sport", "external_id", name="uq_player_sport_ext"),)


class Game(Base):
    __tablename__ = "games"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sport: Mapped[str] = mapped_column(String(8), index=True)
    external_id: Mapped[str] = mapped_column(String(64), index=True)
    game_date: Mapped[date] = mapped_column(Date, index=True)
    home_team: Mapped[str] = mapped_column(String(64))
    away_team: Mapped[str] = mapped_column(String(64))
    starts_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    venue: Mapped[Optional[str]] = mapped_column(String(128))
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("sport", "external_id", name="uq_game_sport_ext"),)


class PlayerGameStat(Base):
    """Per-player per-game box score row. `stats` holds the full statline JSON."""
    __tablename__ = "player_game_stats"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sport: Mapped[str] = mapped_column(String(8), index=True)
    player_external_id: Mapped[str] = mapped_column(String(64), index=True)
    game_external_id: Mapped[str] = mapped_column(String(64), index=True)
    game_date: Mapped[date] = mapped_column(Date, index=True)
    team: Mapped[Optional[str]] = mapped_column(String(64))
    opponent: Mapped[Optional[str]] = mapped_column(String(64))
    is_home: Mapped[Optional[bool]] = mapped_column(Boolean)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (
        UniqueConstraint("sport", "player_external_id", "game_external_id", name="uq_pgs"),
        Index("ix_pgs_player_date", "player_external_id", "game_date"),
    )


class TeamGameStat(Base):
    __tablename__ = "team_game_stats"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sport: Mapped[str] = mapped_column(String(8), index=True)
    team: Mapped[str] = mapped_column(String(64), index=True)
    game_external_id: Mapped[str] = mapped_column(String(64), index=True)
    game_date: Mapped[date] = mapped_column(Date, index=True)
    opponent: Mapped[str] = mapped_column(String(64))
    is_home: Mapped[bool] = mapped_column(Boolean)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("sport", "team", "game_external_id", name="uq_tgs"),)


class PropOffer(Base):
    """A single sportsbook offering for a player prop on a given game."""
    __tablename__ = "prop_offers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sport: Mapped[str] = mapped_column(String(8), index=True)
    game_external_id: Mapped[str] = mapped_column(String(64), index=True)
    game_date: Mapped[date] = mapped_column(Date, index=True)
    player_name: Mapped[str] = mapped_column(String(128), index=True)
    player_external_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    team: Mapped[Optional[str]] = mapped_column(String(64))
    market: Mapped[str] = mapped_column(String(48), index=True)  # e.g. player_points
    line: Mapped[float] = mapped_column(Float)
    side: Mapped[str] = mapped_column(String(8))  # over / under
    price_american: Mapped[int] = mapped_column(Integer)
    book: Mapped[str] = mapped_column(String(32), index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class Pick(Base):
    """A model-generated pick (one of the daily top-N)."""
    __tablename__ = "picks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pick_date: Mapped[date] = mapped_column(Date, index=True)
    sport: Mapped[str] = mapped_column(String(8), index=True)
    player_name: Mapped[str] = mapped_column(String(128))
    team: Mapped[Optional[str]] = mapped_column(String(64))
    opponent: Mapped[Optional[str]] = mapped_column(String(64))
    market: Mapped[str] = mapped_column(String(48))
    line: Mapped[float] = mapped_column(Float)
    side: Mapped[str] = mapped_column(String(8))
    book: Mapped[str] = mapped_column(String(32))
    price_american: Mapped[int] = mapped_column(Integer)
    model_prob: Mapped[float] = mapped_column(Float)
    implied_prob: Mapped[float] = mapped_column(Float)
    edge_pct: Mapped[float] = mapped_column(Float)
    rating: Mapped[float] = mapped_column(Float)  # 0..100
    kelly_unit: Mapped[float] = mapped_column(Float)
    rationale: Mapped[dict] = mapped_column(JSON, default=dict)
    game_external_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)

    result: Mapped[Optional[str]] = mapped_column(String(8))  # win / loss / push / pending
    actual_value: Mapped[Optional[float]] = mapped_column(Float)
    graded_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BetSlip(Base):
    __tablename__ = "betslips"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    submitted_by: Mapped[Optional[str]] = mapped_column(String(64))
    book: Mapped[Optional[str]] = mapped_column(String(32))
    legs: Mapped[list] = mapped_column(JSON, default=list)
    combined_odds_american: Mapped[Optional[int]] = mapped_column(Integer)
    combined_prob: Mapped[float] = mapped_column(Float)
    implied_prob: Mapped[float] = mapped_column(Float)
    edge_pct: Mapped[float] = mapped_column(Float)
    rating: Mapped[float] = mapped_column(Float)
    notes: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class ModelArtifact(Base):
    __tablename__ = "model_artifacts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sport: Mapped[str] = mapped_column(String(8), index=True)
    market: Mapped[str] = mapped_column(String(48), index=True)
    version: Mapped[str] = mapped_column(String(32))
    path: Mapped[str] = mapped_column(String(256))
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    trained_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    __table_args__ = (UniqueConstraint("sport", "market", "version", name="uq_artifact"),)


class GamePrediction(Base):
    """Daily game-level predictions: score, ML prob, spread, total."""
    __tablename__ = "game_predictions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sport: Mapped[str] = mapped_column(String(8), index=True)
    game_external_id: Mapped[str] = mapped_column(String(64), index=True)
    game_date: Mapped[date] = mapped_column(Date, index=True)
    home_team: Mapped[str] = mapped_column(String(64))
    away_team: Mapped[str] = mapped_column(String(64))
    pred_home_score: Mapped[float] = mapped_column(Float)
    pred_away_score: Mapped[float] = mapped_column(Float)
    pred_total: Mapped[float] = mapped_column(Float)
    pred_spread: Mapped[float] = mapped_column(Float)  # home - away
    home_win_prob: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)  # 0..1, how sure the model is
    # Posted market lines (for edge calc against books).
    market_total: Mapped[Optional[float]] = mapped_column(Float)
    market_spread: Mapped[Optional[float]] = mapped_column(Float)
    market_home_ml: Mapped[Optional[int]] = mapped_column(Integer)
    market_away_ml: Mapped[Optional[int]] = mapped_column(Integer)
    rationale: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("sport", "game_external_id", name="uq_gpred"),)


class GameOdds(Base):
    """Posted game-level offers (h2h / spread / total) per book."""
    __tablename__ = "game_odds"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sport: Mapped[str] = mapped_column(String(8), index=True)
    game_external_id: Mapped[str] = mapped_column(String(64), index=True)
    game_date: Mapped[date] = mapped_column(Date, index=True)
    book: Mapped[str] = mapped_column(String(32), index=True)
    market: Mapped[str] = mapped_column(String(16), index=True)  # h2h | spread | total
    side: Mapped[str] = mapped_column(String(16))  # home/away/over/under
    line: Mapped[Optional[float]] = mapped_column(Float)
    price_american: Mapped[int] = mapped_column(Integer)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
