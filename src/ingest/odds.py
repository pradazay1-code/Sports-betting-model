"""Odds + prop line ingestion from The Odds API, with line-movement logging.

Every pull is (1) cached raw to data/raw/odds/<date>/ with a timestamp and
(2) normalized into the line_snapshots table. The append-only time series
powers line-movement analysis, line shopping, and CLV (spec §2.1).

CLI:
    python -m src.ingest.odds --pull                 # featured markets, enabled sports
    python -m src.ingest.odds --pull --props         # + player props (1 request/event!)
    python -m src.ingest.odds --sample <file.json>   # ingest a cached/sample payload
    python -m src.ingest.odds --movement [--hours N] # line-movement report
    python -m src.ingest.odds --shop EVENT_ID MARKET # best price across books
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import requests

from src import config, db

# ---------------------------------------------------------------- odds math


def american_to_decimal(american: int) -> float:
    if american >= 100:
        return 1.0 + american / 100.0
    if american <= -100:
        return 1.0 + 100.0 / abs(american)
    raise ValueError(f"invalid american odds: {american}")


def implied_prob(decimal_odds: float) -> float:
    """Implied probability WITH vig. De-vig lives in the value engine (Phase 2)."""
    return 1.0 / decimal_odds


def canonical_side(outcome_name: str, home_team: str | None, away_team: str | None) -> str:
    name = outcome_name.strip().lower()
    if name == "over":
        return "over"
    if name == "under":
        return "under"
    if name == "draw":
        return "draw"
    if home_team and outcome_name.strip() == home_team.strip():
        return "home"
    if away_team and outcome_name.strip() == away_team.strip():
        return "away"
    return "other"


# ------------------------------------------------------------ normalization


def normalize_event(event: dict, pulled_at: str, raw_file: str | None = None) -> tuple[dict, list[dict]]:
    """One Odds API event object -> (event row, snapshot rows)."""
    home, away = event.get("home_team"), event.get("away_team")
    event_row = {
        "event_id": event["id"],
        "sport": event["sport_key"],
        "commence_time": event.get("commence_time"),
        "home_team": home,
        "away_team": away,
    }
    rows: list[dict] = []
    for bookmaker in event.get("bookmakers", []):
        for market in bookmaker.get("markets", []):
            for outcome in market.get("outcomes", []):
                price = outcome.get("price")
                if price is None:
                    continue
                american = int(price)
                decimal = american_to_decimal(american)
                rows.append({
                    "pulled_at": pulled_at,
                    "sport": event["sport_key"],
                    "event_id": event["id"],
                    "book": bookmaker["key"],
                    "market": market["key"],
                    # player props carry the player in outcome.description
                    "player": outcome.get("description"),
                    "outcome": outcome["name"],
                    "side": canonical_side(outcome["name"], home, away),
                    "line": outcome.get("point"),
                    "odds_american": american,
                    "odds_decimal": round(decimal, 6),
                    "implied_prob": round(implied_prob(decimal), 6),
                    "raw_file": raw_file,
                })
    return event_row, rows


def ingest_payload(conn, payload: list[dict] | dict, pulled_at: str | None = None,
                   raw_file: str | None = None) -> int:
    """Normalize an Odds API payload (list of events, or one event) into the DB."""
    pulled_at = pulled_at or db.utcnow()
    events = payload if isinstance(payload, list) else [payload]
    inserted = 0
    for event in events:
        if not isinstance(event, dict) or "id" not in event:
            continue
        event_row, rows = normalize_event(event, pulled_at, raw_file)
        db.upsert_event(conn, event_row, pulled_at)
        inserted += db.insert_snapshots(conn, rows)
    conn.commit()
    return inserted


# ----------------------------------------------------------------- API pull


class OddsAPIClient:
    """The Odds API v4 client. Caches every response and logs quota headers."""

    def __init__(self):
        cfg = config.sources()["odds_api"]
        http = config.sources()["http"]
        self.base_url = cfg["base_url"].rstrip("/")
        self.regions = ",".join(cfg["regions"])
        self.odds_format = cfg["odds_format"]
        self.featured_markets = ",".join(cfg["featured_markets"])
        self.prop_markets = cfg.get("prop_markets", {})
        self.max_prop_events = cfg.get("max_prop_events_per_pull", 8)
        self.timeout = http["timeout_seconds"]
        self.max_retries = http["max_retries"]
        self.backoff = http["backoff_base_seconds"]
        self.api_key = config.odds_api_key()
        if not self.api_key:
            raise RuntimeError(
                "ODDS_API_KEY is not set. Get a free key at https://the-odds-api.com "
                "and put it in .env — or ingest a cached payload with --sample."
            )
        self.session = requests.Session()

    def _get(self, conn, path: str, **params) -> list | dict | None:
        url = f"{self.base_url}{path}"
        params["apiKey"] = self.api_key
        for attempt in range(self.max_retries):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException:
                time.sleep(self.backoff * 2 ** attempt)
                continue
            used = resp.headers.get("x-requests-used")
            remaining = resp.headers.get("x-requests-remaining")
            db.log_api_usage(conn, path,
                             int(used) if used else None,
                             int(remaining) if remaining else None)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in (429, 500, 502, 503):
                time.sleep(self.backoff * 2 ** attempt)
                continue
            # 401/402/404/422: plan doesn't cover this market/endpoint —
            # skip it, never kill the whole run over one market
            print(f"  odds api {resp.status_code} for {path} — skipped")
            return None
        return None

    def _cache_raw(self, payload, sport_key: str, label: str, pulled_at: str) -> str:
        day_dir = config.raw_dir() / "odds" / pulled_at[:10]
        day_dir.mkdir(parents=True, exist_ok=True)
        stamp = pulled_at.replace(":", "").replace("-", "")
        out = day_dir / f"{stamp}_{sport_key}_{label}.json"
        out.write_text(json.dumps(payload, indent=1))
        return str(out.relative_to(config.REPO_ROOT))

    def pull_sport(self, conn, sport_key: str, include_props: bool = False) -> int:
        """Pull featured markets (1 request), optionally props (1 request/event)."""
        pulled_at = db.utcnow()
        payload = self._get(conn, f"/sports/{sport_key}/odds",
                            regions=self.regions, markets=self.featured_markets,
                            oddsFormat=self.odds_format)
        if payload is None:
            print(f"  {sport_key}: pull failed")
            return 0
        raw_file = self._cache_raw(payload, sport_key, "featured", pulled_at)
        inserted = ingest_payload(conn, payload, pulled_at, raw_file)

        if include_props and payload:
            markets = self.prop_markets.get(sport_key)
            if markets:
                for event in payload[: self.max_prop_events]:
                    props = self._get(conn, f"/sports/{sport_key}/events/{event['id']}/odds",
                                      regions=self.regions, markets=",".join(markets),
                                      oddsFormat=self.odds_format)
                    if props:
                        pf = self._cache_raw(props, sport_key, f"props_{event['id'][:8]}", pulled_at)
                        inserted += ingest_payload(conn, props, pulled_at, pf)
        return inserted


def pull_all(conn, include_props: bool = False) -> dict[str, int]:
    """Pull every enabled sport. Returns sport -> snapshot rows inserted."""
    client = OddsAPIClient()
    results: dict[str, int] = {}
    for name, sport_cfg in config.enabled_sports().items():
        keys = [sport_cfg["odds_key"], *sport_cfg.get("extra_keys", [])]
        results[name] = sum(client.pull_sport(conn, k, include_props) for k in keys)
    return results


# ------------------------------------------------- line movement & shopping


def line_movement(conn, hours: float = 24.0, sport: str | None = None,
                  min_snapshots: int = 2) -> list[dict]:
    """Movement per (event, book, market, player, side) over the window.

    Returns entries where the line or the price actually moved,
    with open -> current values and deltas.
    """
    params: list = [f"-{hours} hours"]
    sport_filter = ""
    if sport:
        sport_filter = "AND s.sport = ?"
        params.append(sport)
    rows = conn.execute(
        f"""
        SELECT s.event_id, s.sport, s.book, s.market, s.player, s.side,
               s.pulled_at, s.line, s.odds_american, s.odds_decimal,
               e.home_team, e.away_team, e.commence_time
        FROM line_snapshots s
        LEFT JOIN events e ON e.event_id = s.event_id
        WHERE s.pulled_at >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', ?)
        {sport_filter}
        ORDER BY s.event_id, s.book, s.market, s.player, s.side, s.pulled_at
        """,
        params,
    ).fetchall()

    movements: list[dict] = []
    series: dict[tuple, list] = {}
    for r in rows:
        key = (r["event_id"], r["book"], r["market"], r["player"], r["side"])
        series.setdefault(key, []).append(r)
    for (event_id, book, market, player, side), snaps in series.items():
        if len(snaps) < min_snapshots:
            continue
        first, last = snaps[0], snaps[-1]
        line_delta = ((last["line"] or 0) - (first["line"] or 0)) if first["line"] is not None else 0.0
        odds_delta = last["odds_american"] - first["odds_american"]
        if line_delta == 0 and odds_delta == 0:
            continue
        movements.append({
            "event_id": event_id, "sport": first["sport"],
            "matchup": f"{first['away_team']} @ {first['home_team']}",
            "book": book, "market": market, "player": player, "side": side,
            "open_at": first["pulled_at"], "open_line": first["line"],
            "open_odds": first["odds_american"],
            "last_at": last["pulled_at"], "last_line": last["line"],
            "last_odds": last["odds_american"],
            "line_delta": round(line_delta, 2), "odds_delta": odds_delta,
            "n_snapshots": len(snaps),
        })
    movements.sort(key=lambda m: (abs(m["line_delta"]), abs(m["odds_delta"])), reverse=True)
    return movements


def best_prices(conn, event_id: str, market: str, player: str | None = None,
                side: str | None = None, line: float | None = None) -> list[dict]:
    """Line shopping: latest price per book, best decimal first (spec §2.1).

    Pass `line` when the caller's probability was computed for a specific
    line — a P(under 5.5) must never be priced against an under 4.5 quote.
    Books quoting a different line for the same market are excluded.
    """
    params: list = [event_id, market]
    extra = ""
    if player:
        extra += " AND player = ?"
        params.append(player)
    if side:
        extra += " AND side = ?"
        params.append(side)
    if line is not None:
        extra += " AND line = ?"
        params.append(line)
    rows = conn.execute(
        f"""
        SELECT book, player, side, line, odds_american, odds_decimal, implied_prob,
               MAX(pulled_at) AS pulled_at
        FROM line_snapshots
        WHERE event_id = ? AND market = ? {extra}
        GROUP BY book, player, side, line
        ORDER BY odds_decimal DESC
        """,
        params,
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pull", action="store_true", help="pull live odds for enabled sports")
    ap.add_argument("--props", action="store_true", help="also pull player props")
    ap.add_argument("--sample", metavar="FILE", help="ingest a cached/sample Odds API payload")
    ap.add_argument("--movement", action="store_true", help="print line-movement report")
    ap.add_argument("--hours", type=float, default=24.0)
    ap.add_argument("--shop", nargs=2, metavar=("EVENT_ID", "MARKET"), help="best price per book")
    args = ap.parse_args(argv)

    conn = db.connect()
    if args.sample:
        payload = json.loads(Path(args.sample).read_text())
        n = ingest_payload(conn, payload, raw_file=args.sample)
        print(f"ingested {n} line snapshots from {args.sample}")
    if args.pull:
        for sport, n in pull_all(conn, include_props=args.props).items():
            print(f"{sport}: {n} line snapshots")
    if args.movement:
        moves = line_movement(conn, hours=args.hours)
        if not moves:
            print(f"no line movement in the last {args.hours:g}h")
        for m in moves[:40]:
            who = m["player"] or m["matchup"]
            print(f"[{m['sport']}] {who} {m['market']}/{m['side']} @{m['book']}: "
                  f"line {m['open_line']} -> {m['last_line']} "
                  f"odds {m['open_odds']:+d} -> {m['last_odds']:+d} ({m['n_snapshots']} snaps)")
    if args.shop:
        for r in best_prices(conn, *args.shop):
            print(f"{r['book']:>14}  {r['player'] or ''} {r['side']:<6} "
                  f"line {r['line']}  {r['odds_american']:+d}  (dec {r['odds_decimal']:.3f})")
    conn.close()


if __name__ == "__main__":
    main()
