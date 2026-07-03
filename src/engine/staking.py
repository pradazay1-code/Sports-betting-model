"""Fractional Kelly staking + exposure caps — enforced, not advised (spec §0.5, §5).

Quarter-Kelly, 2% of bankroll per play, 6% daily exposure, -15% drawdown
kill switch (7-day track-only + calibration audit flag), and the paper-mode
gate: 200 tracked picks with positive CLV before real sizing displays.

Units: 1 unit = 1% of current bankroll.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src import config, db


def kelly_fraction(p: float, decimal_odds: float) -> float:
    """f* = (bp - q)/b, floored at 0 (spec §5)."""
    b = decimal_odds - 1.0
    if b <= 0:
        return 0.0
    return max(0.0, (b * p - (1.0 - p)) / b)


def stake_fraction(p: float, decimal_odds: float, tier_multiplier: float = 1.0) -> float:
    """Bankroll fraction for one play: quarter-Kelly x tier, hard-capped."""
    cfg = config.settings()["bankroll"]
    f = kelly_fraction(p, decimal_odds) * cfg["kelly_fraction"] * tier_multiplier
    return min(f, cfg["max_pct_per_play"])


# ------------------------------------------------------------- system state

def _get_state(conn, key: str) -> str | None:
    conn.execute("CREATE TABLE IF NOT EXISTS system_state (key TEXT PRIMARY KEY, value TEXT)")
    row = conn.execute("SELECT value FROM system_state WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def _set_state(conn, key: str, value: str) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS system_state (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT OR REPLACE INTO system_state VALUES (?, ?)", (key, value))
    conn.commit()


def drawdown_check(conn) -> bool:
    """True = trading allowed. -15% off peak triggers 7-day track-only mode."""
    until = _get_state(conn, "track_only_until")
    now = datetime.now(timezone.utc)
    if until and now < datetime.fromisoformat(until):
        return False
    peak, current = conn.execute(
        "SELECT MAX(bankroll), (SELECT bankroll FROM bankroll_history ORDER BY id DESC LIMIT 1) "
        "FROM bankroll_history").fetchone()
    stop = config.settings()["bankroll"]["drawdown_stop_pct"]
    if peak and current < peak * (1.0 - stop):
        _set_state(conn, "track_only_until", (now + timedelta(days=7)).isoformat())
        _set_state(conn, "calibration_audit_required", "1")
        return False
    return True


def paper_gate_active(conn) -> bool:
    """Paper until >= 200 tracked picks AND positive average CLV (spec §9)."""
    cfg = config.settings()["paper_mode"]
    if not cfg["enabled"]:
        return False
    n, avg_clv = conn.execute(
        "SELECT COUNT(*), AVG(clv_pct) FROM clv_log WHERE clv_pct IS NOT NULL").fetchone()
    return n < cfg["min_tracked_picks"] or (avg_clv or 0) <= 0


def daily_exposure_used(conn) -> float:
    """Bankroll fraction already staked today (units are % of bankroll)."""
    used = conn.execute(
        "SELECT COALESCE(SUM(stake_units), 0) FROM picks "
        "WHERE date(created_at) = date('now') AND status = 'pending'").fetchone()[0]
    return used / 100.0


def apply(conn, edges: list) -> dict[int, tuple[float, bool]]:
    """Stake every surfaced edge. Returns index -> (stake_units, is_paper).

    Research-flagged edges that are not yet validated get C-tier sizing at
    most — model finds candidates, research validates them (spec §4).
    """
    settings = config.settings()
    tiers = settings["tiers"]
    is_paper = paper_gate_active(conn)
    allowed = drawdown_check(conn)
    budget = settings["bankroll"]["max_pct_per_day"] - daily_exposure_used(conn)

    out: dict[int, tuple[float, bool]] = {}
    for i, e in enumerate(edges):
        if not e.surface or e.tier is None or not allowed:
            out[i] = (0.0, is_paper)
            continue
        mult = tiers[e.tier]["stake_multiplier"]
        if e.needs_research:
            mult = min(mult, tiers["C"]["stake_multiplier"])
        frac = stake_fraction(e.model_prob, e.odds_decimal, mult)
        frac = min(frac, max(0.0, budget))
        budget -= frac
        out[i] = (round(frac * 100.0, 2), is_paper)   # fraction -> units
    return out
