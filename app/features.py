"""Feature engineering from raw player_game_stats.

Two public functions:

- build_training_frame(sport, market) -> DataFrame with one row per
  (player, historical_game) and the actual stat as `target`. All features
  are computed strictly from games BEFORE the target game (shift(1)) so
  there's no leakage.

- build_inference_features(sport, market, player_name, on_date) -> dict of
  features for predicting that player's market value on `on_date`. Uses
  every game strictly before `on_date`.

Features intentionally stay simple and stable. Honest > clever.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from app.store import connection


def _load_history(sport: str) -> pd.DataFrame:
    with connection() as conn:
        rows = [dict(r) for r in conn.execute(
            """SELECT pgs.*, pl.full_name
               FROM player_game_stats pgs
               LEFT JOIN players pl ON pl.player_id = pgs.player_id
               WHERE pgs.sport = ?
               ORDER BY pgs.game_date""",
            (sport,),
        ).fetchall()]
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    parsed = df["stats_json"].apply(lambda s: json.loads(s) if s else {})
    stat_df = pd.json_normalize(parsed)
    df = pd.concat([df.drop(columns=["stats_json"]), stat_df], axis=1)
    df["game_date"] = pd.to_datetime(df["game_date"])
    df["full_name_lower"] = df.get("full_name", "").fillna("").astype(str).str.lower()
    return df.sort_values(["player_id", "game_date"]).reset_index(drop=True)


def _attach_features(df: pd.DataFrame, market: str) -> pd.DataFrame:
    g = df.groupby("player_id", group_keys=False)
    for w in (5, 10, 25):
        df[f"r{w}_mean"] = g[market].apply(lambda s: s.shift(1).rolling(w, min_periods=2).mean())
        df[f"r{w}_std"]  = g[market].apply(lambda s: s.shift(1).rolling(w, min_periods=2).std())
        df[f"r{w}_max"]  = g[market].apply(lambda s: s.shift(1).rolling(w, min_periods=2).max())
    df["season_avg"] = g[market].apply(lambda s: s.shift(1).expanding(min_periods=2).mean())
    df["season_std"] = g[market].apply(lambda s: s.shift(1).expanding(min_periods=2).std())
    df["n_games"]    = g[market].apply(lambda s: s.shift(1).expanding().count())
    df["days_rest"]  = g["game_date"].apply(lambda s: s.diff().dt.days)
    df["home"]       = df["home"].astype("Int64").fillna(0).astype(int)

    # --- advanced / derived features (all leakage-safe: shift(1) already applied) ---
    # Exponentially-weighted mean weights recent games more heavily than a flat
    # rolling average — better at catching hot/cold runs.
    df["ewm8"]   = g[market].apply(lambda s: s.shift(1).ewm(span=8, min_periods=2).mean())
    # Floor/ceiling of the recent window: how bad a bad night is, how high the upside.
    df["floor10"]   = g[market].apply(lambda s: s.shift(1).rolling(10, min_periods=2).min())
    df["ceiling10"] = g[market].apply(lambda s: s.shift(1).rolling(10, min_periods=2).max())
    # Momentum: recent 5 vs longer 25 baseline (positive = trending up).
    df["trend_5_25"] = df["r5_mean"] - df["r25_mean"]
    # Consistency: mean / volatility — high means a dependable producer.
    df["consistency"] = df["r10_mean"] / (df["r10_std"].abs() + 1e-6)
    # Back-to-back flag (fatigue signal).
    df["back_to_back"] = (df["days_rest"].fillna(3) <= 1).astype(int)

    opp = df[["game_date", "opp_team", market]].dropna(subset=["opp_team"]).copy()
    opp.sort_values(["opp_team", "game_date"], inplace=True)
    opp["opp_allowed"] = (
        opp.groupby("opp_team")[market]
        .apply(lambda s: s.shift(1).rolling(200, min_periods=20).mean())
        .reset_index(level=0, drop=True)
    )
    df = df.merge(opp[["game_date", "opp_team", "opp_allowed"]],
                  on=["game_date", "opp_team"], how="left")
    # Matchup edge: player's recent level vs. what the opponent typically allows.
    df["vs_opp"] = df["r10_mean"] - df["opp_allowed"]
    return df


FEATURE_COLS = [
    "r5_mean", "r5_std", "r5_max",
    "r10_mean", "r10_std", "r10_max",
    "r25_mean", "r25_std", "r25_max",
    "season_avg", "season_std", "n_games",
    "days_rest", "home", "opp_allowed",
    # advanced
    "ewm8", "floor10", "ceiling10", "trend_5_25",
    "consistency", "back_to_back", "vs_opp",
]


def build_training_frame(sport: str, market: str) -> pd.DataFrame:
    df = _load_history(sport)
    if df.empty or market not in df.columns:
        return pd.DataFrame()
    df[market] = pd.to_numeric(df[market], errors="coerce")
    df = df.dropna(subset=[market]).copy()
    df = _attach_features(df, market)
    df["target"] = df[market].astype(float)
    keep = ["player_id", "full_name", "game_id", "game_date", "team", "opp_team", "target"] + FEATURE_COLS
    out = df[keep].copy()
    # Drop rows with too little history to be useful (need at least 5 prior games).
    out = out.dropna(subset=["r5_mean"]).reset_index(drop=True)
    out["game_date"] = out["game_date"].dt.strftime("%Y-%m-%d")
    return out


def build_inference_features(sport: str, market: str, player_name: str,
                             on_date: str, opp_team: str | None = None,
                             home: int | None = None) -> dict | None:
    df = _load_history(sport)
    if df.empty or market not in df.columns:
        return None
    df[market] = pd.to_numeric(df[market], errors="coerce")
    df = df.dropna(subset=[market]).copy()

    name_l = player_name.lower().strip()
    pids = df.loc[df["full_name_lower"] == name_l, "player_id"].unique()
    if not len(pids):
        # rapidfuzz partial match as a fallback
        try:
            from rapidfuzz import process, fuzz
            choices = df["full_name_lower"].dropna().unique().tolist()
            match = process.extractOne(name_l, choices, scorer=fuzz.WRatio, score_cutoff=92)
            if match:
                pids = df.loc[df["full_name_lower"] == match[0], "player_id"].unique()
        except Exception:
            pass
    if not len(pids):
        return None
    sub = df[df["player_id"].isin(pids)].copy()
    sub = sub[sub["game_date"] < pd.Timestamp(on_date)]
    if sub.empty:
        return None
    sub = _attach_features(sub, market)
    last = sub.iloc[-1]
    feats = {c: float(last[c]) if pd.notna(last[c]) else 0.0 for c in FEATURE_COLS}
    if home is not None:
        feats["home"] = int(home)
    if opp_team is not None:
        # use opponent's all-time allowed mean for this market
        opp_hist = df[df["opp_team"] == opp_team][market]
        if len(opp_hist) >= 5:
            feats["opp_allowed"] = float(opp_hist.tail(200).mean())
    return feats
