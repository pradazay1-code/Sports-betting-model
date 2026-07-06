"""SQLite storage layer for Pulse Engine (SQLAlchemy Core).

All timestamps are UTC epoch seconds (INTEGER). Candle `ts` is the start of
the minute the candle covers, i.e. candle (ts) aggregates trades in
[ts, ts+60) and is only complete once now >= ts+60.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any, Iterable

import pandas as pd
from sqlalchemy import (
    Column, Float, Integer, MetaData, String, Table, Text, UniqueConstraint,
    create_engine, insert, select, text,
)
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

import config

metadata = MetaData()

candles = Table(
    "candles", metadata,
    Column("asset", String(8), nullable=False),
    Column("ts", Integer, nullable=False),
    Column("open", Float, nullable=False),
    Column("high", Float, nullable=False),
    Column("low", Float, nullable=False),
    Column("close", Float, nullable=False),
    Column("volume", Float, nullable=False),
    Column("source", String(16), nullable=False),
    UniqueConstraint("asset", "ts", name="uq_candles_asset_ts"),
)

kalshi_markets = Table(
    "kalshi_markets", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ticker", String(64), nullable=False),
    Column("asset", String(8), nullable=False),
    Column("window_start", Integer),
    Column("window_close", Integer),
    Column("strike_type", String(16)),
    Column("yes_bid", Float),
    Column("yes_ask", Float),
    Column("last_price", Float),
    Column("fetched_at", Integer, nullable=False),
)

news = Table(
    "news", metadata,
    Column("id", String(40), primary_key=True),  # sha1 of url/title
    Column("ts", Integer, nullable=False),
    Column("source", String(32), nullable=False),
    Column("title", Text, nullable=False),
    Column("url", Text),
    Column("assets_mentioned", String(32)),      # comma-separated
    Column("sentiment_score", Float),
    Column("importance", Float),
)

features_snapshot = Table(
    "features_snapshot", metadata,
    Column("asset", String(8), nullable=False),
    Column("window_start", Integer, nullable=False),
    Column("feature_json", Text, nullable=False),
    UniqueConstraint("asset", "window_start", name="uq_features_asset_window"),
)

predictions = Table(
    "predictions", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("asset", String(8), nullable=False),
    Column("window_start", Integer, nullable=False),
    Column("window_close", Integer, nullable=False),
    Column("prob_up", Float, nullable=False),
    Column("pick", String(8), nullable=False),   # UP | DOWN | NO PLAY
    Column("kalshi_yes_price_at_signal", Float),  # dollars 0-1, NULL if no market
    Column("edge", Float),
    Column("model_version", String(48)),
    Column("created_at", Integer, nullable=False),
    UniqueConstraint("asset", "window_start", name="uq_pred_asset_window"),
)

outcomes = Table(
    "outcomes", metadata,
    Column("prediction_id", Integer, primary_key=True),
    Column("actual_direction", String(8)),       # UP | DOWN | FLAT | UNKNOWN
    Column("correct", Integer),                  # 1/0, NULL for NO PLAY/UNKNOWN
    Column("brier_component", Float),
    Column("paper_pnl", Float),                  # dollars, 0 for NO PLAY
    Column("resolved_at", Integer, nullable=False),
)

model_registry = Table(
    "model_registry", metadata,
    Column("version", String(48), primary_key=True),
    Column("asset", String(8), nullable=False),
    Column("trained_at", Integer, nullable=False),
    Column("train_rows", Integer),
    Column("val_logloss", Float),
    Column("val_brier", Float),
    Column("val_accuracy", Float),
    Column("notes", Text),
)

settings_kv = Table(
    "settings", metadata,
    Column("key", String(64), primary_key=True),
    Column("value", Text, nullable=False),
)

fear_greed = Table(
    "fear_greed", metadata,
    Column("ts", Integer, primary_key=True),     # day granularity
    Column("value", Integer, nullable=False),
)

_engine = None
_lock = threading.Lock()


def get_engine():
    global _engine
    with _lock:
        if _engine is None:
            _engine = create_engine(
                f"sqlite:///{config.DB_PATH}",
                connect_args={"timeout": 30, "check_same_thread": False},
            )
            with _engine.connect() as conn:
                conn.execute(text("PRAGMA journal_mode=WAL"))
                conn.commit()
        return _engine


def init_db() -> None:
    metadata.create_all(get_engine())


# ------------------------------------------------------------- candles ------

def upsert_candles(rows: Iterable[dict[str, Any]]) -> int:
    """Insert candles, replacing on (asset, ts) conflict. Returns row count."""
    rows = list(rows)
    if not rows:
        return 0
    stmt = sqlite_insert(candles)
    stmt = stmt.on_conflict_do_update(
        index_elements=["asset", "ts"],
        set_={c: stmt.excluded[c] for c in ("open", "high", "low", "close", "volume", "source")},
    )
    with get_engine().begin() as conn:
        conn.execute(stmt, rows)
    return len(rows)


def latest_candle_ts(asset: str) -> int | None:
    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT MAX(ts) FROM candles WHERE asset=:a"), {"a": asset}
        ).scalar()
    return int(row) if row is not None else None


def candle_count(asset: str) -> int:
    with get_engine().connect() as conn:
        return int(conn.execute(
            text("SELECT COUNT(*) FROM candles WHERE asset=:a"), {"a": asset}
        ).scalar() or 0)


def get_candles(asset: str, start_ts: int, end_ts: int | None = None) -> pd.DataFrame:
    """1m candles for asset in [start_ts, end_ts), sorted, ts-indexed."""
    end_ts = end_ts or int(time.time()) + 60
    q = ("SELECT ts, open, high, low, close, volume FROM candles "
         "WHERE asset=:a AND ts>=:s AND ts<:e ORDER BY ts")
    with get_engine().connect() as conn:
        df = pd.read_sql_query(text(q), conn, params={"a": asset, "s": int(start_ts), "e": int(end_ts)})
    return df.set_index("ts") if not df.empty else df


# -------------------------------------------------------------- kalshi ------

def insert_kalshi_snapshot(row: dict[str, Any]) -> None:
    with get_engine().begin() as conn:
        conn.execute(insert(kalshi_markets).values(**row))


def kalshi_price_at(asset: str, window_close: int, before_ts: int) -> dict | None:
    """Most recent Kalshi snapshot for a window fetched at/before `before_ts`."""
    q = ("SELECT * FROM kalshi_markets WHERE asset=:a AND window_close=:w "
         "AND fetched_at<=:t ORDER BY fetched_at DESC LIMIT 1")
    with get_engine().connect() as conn:
        row = conn.execute(text(q), {"a": asset, "w": int(window_close), "t": int(before_ts)}).mappings().first()
    return dict(row) if row else None


# ---------------------------------------------------------------- news ------

def insert_news(rows: Iterable[dict[str, Any]]) -> int:
    rows = list(rows)
    if not rows:
        return 0
    stmt = sqlite_insert(news).on_conflict_do_nothing(index_elements=["id"])
    with get_engine().begin() as conn:
        res = conn.execute(stmt, rows)
    return res.rowcount if res.rowcount and res.rowcount > 0 else 0


def recent_news(limit: int = 10, since_ts: int | None = None, asset: str | None = None) -> list[dict]:
    q = "SELECT * FROM news WHERE 1=1"
    params: dict[str, Any] = {}
    if since_ts:
        q += " AND ts>=:s"
        params["s"] = int(since_ts)
    if asset:
        q += " AND assets_mentioned LIKE :m"
        params["m"] = f"%{asset}%"
    q += " ORDER BY ts DESC LIMIT :l"
    params["l"] = limit
    with get_engine().connect() as conn:
        return [dict(r) for r in conn.execute(text(q), params).mappings()]


def set_fear_greed(day_ts: int, value: int) -> None:
    stmt = sqlite_insert(fear_greed).values(ts=day_ts, value=value)
    stmt = stmt.on_conflict_do_update(index_elements=["ts"], set_={"value": value})
    with get_engine().begin() as conn:
        conn.execute(stmt)


def get_fear_greed(n: int = 2) -> list[dict]:
    with get_engine().connect() as conn:
        return [dict(r) for r in conn.execute(
            text("SELECT ts, value FROM fear_greed ORDER BY ts DESC LIMIT :n"), {"n": n}
        ).mappings()]


# ---------------------------------------------------- predictions/grades ----

def save_features(asset: str, window_start: int, feats: dict[str, Any]) -> None:
    stmt = sqlite_insert(features_snapshot).values(
        asset=asset, window_start=int(window_start), feature_json=json.dumps(feats))
    stmt = stmt.on_conflict_do_update(
        index_elements=["asset", "window_start"], set_={"feature_json": stmt.excluded.feature_json})
    with get_engine().begin() as conn:
        conn.execute(stmt)


def insert_prediction(row: dict[str, Any]) -> int | None:
    stmt = sqlite_insert(predictions).values(**row).on_conflict_do_nothing(
        index_elements=["asset", "window_start"])
    with get_engine().begin() as conn:
        res = conn.execute(stmt)
        return res.inserted_primary_key[0] if res.rowcount else None


def unresolved_predictions(before_close_ts: int) -> list[dict]:
    q = ("SELECT p.* FROM predictions p LEFT JOIN outcomes o ON o.prediction_id=p.id "
         "WHERE o.prediction_id IS NULL AND p.window_close<=:t ORDER BY p.window_close")
    with get_engine().connect() as conn:
        return [dict(r) for r in conn.execute(text(q), {"t": int(before_close_ts)}).mappings()]


def insert_outcome(row: dict[str, Any]) -> None:
    stmt = sqlite_insert(outcomes).values(**row).on_conflict_do_nothing(
        index_elements=["prediction_id"])
    with get_engine().begin() as conn:
        conn.execute(stmt)


def resolved_history(limit: int = 50, asset: str | None = None, since_ts: int | None = None) -> list[dict]:
    q = ("SELECT p.*, o.actual_direction, o.correct, o.brier_component, o.paper_pnl, o.resolved_at, "
         "f.feature_json FROM predictions p JOIN outcomes o ON o.prediction_id=p.id "
         "LEFT JOIN features_snapshot f ON f.asset=p.asset AND f.window_start=p.window_start WHERE 1=1")
    params: dict[str, Any] = {}
    if asset:
        q += " AND p.asset=:a"
        params["a"] = asset
    if since_ts:
        q += " AND p.window_close>=:s"
        params["s"] = int(since_ts)
    q += " ORDER BY p.window_close DESC LIMIT :l"
    params["l"] = limit
    with get_engine().connect() as conn:
        return [dict(r) for r in conn.execute(text(q), params).mappings()]


def resolved_count() -> int:
    with get_engine().connect() as conn:
        return int(conn.execute(text("SELECT COUNT(*) FROM outcomes")).scalar() or 0)


def register_model(row: dict[str, Any]) -> None:
    stmt = sqlite_insert(model_registry).values(**row)
    stmt = stmt.on_conflict_do_update(
        index_elements=["version"],
        set_={k: v for k, v in row.items() if k != "version"})
    with get_engine().begin() as conn:
        conn.execute(stmt)


def registry_rows(asset: str | None = None) -> list[dict]:
    q = "SELECT * FROM model_registry"
    params = {}
    if asset:
        q += " WHERE asset=:a"
        params["a"] = asset
    q += " ORDER BY trained_at DESC"
    with get_engine().connect() as conn:
        return [dict(r) for r in conn.execute(text(q), params).mappings()]


# ------------------------------------------------------------- settings -----

def get_setting(key: str, default: str | None = None) -> str | None:
    with get_engine().connect() as conn:
        row = conn.execute(select(settings_kv.c.value).where(settings_kv.c.key == key)).scalar()
    return row if row is not None else default


def set_setting(key: str, value: str) -> None:
    stmt = sqlite_insert(settings_kv).values(key=key, value=str(value))
    stmt = stmt.on_conflict_do_update(index_elements=["key"], set_={"value": str(value)})
    with get_engine().begin() as conn:
        conn.execute(stmt)


def current_edge_buffer() -> float:
    raw = get_setting("edge_buffer")
    return float(raw) if raw else config.MIN_EDGE_BUFFER
