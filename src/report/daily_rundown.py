"""Daily rundown generator -> reports/YYYY-MM-DD.md (spec §6).

Renders surfaced plays by tier with model prob / fair prob / EV / stake,
the no-plays-that-looked-tempting section (trust in the threshold),
and yesterday's results + CLV grades. "NO PLAYS TODAY" is a valid,
first-class output — passing is a position (spec §0.3).
"""

from __future__ import annotations

import os
from datetime import date as date_cls

from src import config

try:  # Phase 5 delivery is optional at import time
    import requests
except ImportError:  # pragma: no cover
    requests = None


def _fmt_odds(american: int) -> str:
    return f"{american:+d}"


def _header_stats(conn) -> dict:
    bankroll = conn.execute(
        "SELECT bankroll FROM bankroll_history ORDER BY id DESC LIMIT 1").fetchone()[0]
    start = conn.execute(
        "SELECT bankroll FROM bankroll_history ORDER BY id ASC LIMIT 1").fetchone()[0]
    wins = conn.execute("SELECT COUNT(*) FROM picks WHERE status='won'").fetchone()[0]
    losses = conn.execute("SELECT COUNT(*) FROM picks WHERE status='lost'").fetchone()[0]
    clv = conn.execute("SELECT AVG(clv_pct) FROM clv_log WHERE clv_pct IS NOT NULL").fetchone()[0]
    settled = conn.execute(
        "SELECT COUNT(*) FROM picks WHERE status IN ('won','lost','push')").fetchone()[0]
    return {
        "bankroll": bankroll,
        "roi": (bankroll - start) / start if start else 0.0,
        "record": f"{wins}-{losses}",
        "clv": clv,
        "settled": settled,
    }


def _pick_block(i: int, p: dict) -> str:
    who = p["player"] or "game"
    line_part = f" {p['side'].title()} {p['line']}" if p["line"] is not None else f" {p['side'].title()}"
    unit_suffix = config.settings()["paper_mode"]["stake_display_suffix"] \
        if p.get("is_paper", 1) else "u"
    stake = f"{p['stake_units']:.2f} {unit_suffix}" if p["stake_units"] else "track only"
    lines = [
        f"{i}. [{p['sport']}] {who}{line_part} — {p['market']} "
        f"({_fmt_odds(p['odds_american'])} {p['book']})",
        f"   Model: {p['model_prob']:.1%} | Market (fair): {p['market_fair_prob']:.1%} "
        f"| EV: {p['ev_pct']:+.1%} | Stake: {stake}",
    ]
    if p.get("notes"):
        lines.append(f"   Why/risks: {p['notes']}")
    if p.get("needs_research"):
        memo = p.get("research_memo")
        lines.append(f"   Research: {memo if memo else 'REQUIRED (EV > 6%) — not yet validated; sized down'}")
    return "\n".join(lines)


def _yesterday_section(conn, today: str) -> list[str]:
    rows = conn.execute(
        """SELECT p.*, c.clv_pct, c.close_odds_american FROM picks p
           LEFT JOIN clv_log c ON c.pick_id = p.pick_id
           WHERE p.status IN ('won','lost','push') AND date(p.created_at) < date(?)
           ORDER BY p.settled_at DESC LIMIT 15""", (today,)).fetchall()
    if not rows:
        return ["(no graded picks yet)"]
    out = []
    for r in rows:
        clv = f"CLV {r['clv_pct']:+.1%}" if r["clv_pct"] is not None else "CLV pending"
        res = f"result {r['result_value']:g}" if r["result_value"] is not None else ""
        out.append(f"- {r['status'].upper()}: {r['player'] or 'game'} {r['side']} "
                   f"{r['line']} {r['market']} @{_fmt_odds(r['odds_american'])} | {clv} {res}")
    return out


def render(conn, day: str | None = None, no_plays: list[dict] | None = None,
           slips: list[dict] | None = None) -> str:
    day = day or date_cls.today().isoformat()
    hs = _header_stats(conn)
    picks = [dict(r) for r in conn.execute(
        """SELECT * FROM picks WHERE date(created_at) = date(?)
           AND status IN ('pending','hold_lineup') AND tier IS NOT NULL
           ORDER BY ev_pct DESC""", (day,)).fetchall()]

    clv_str = f"{hs['clv']:+.1%}" if hs["clv"] is not None else "n/a"
    md = [f"# 🏆 EDGE ENGINE DAILY — {day}",
          f"Bankroll: ${hs['bankroll']:,.2f} | YTD ROI: {hs['roi']:+.1%} | "
          f"CLV avg: {clv_str} | Record: {hs['record']}", ""]

    by_tier: dict[str, list[dict]] = {"A": [], "B": [], "C": []}
    for p in picks:
        by_tier.setdefault(p["tier"], []).append(p)

    if not any(by_tier.values()):
        md += ["## NO PLAYS TODAY",
               "Nothing cleared the edge threshold "
               f"({config.settings()['edges']['min_ev_props']:.0%} props / "
               f"{config.settings()['edges']['min_ev_main_markets']:.0%} mains). "
               "Passing is a position.", ""]
    for tier, label in (("A", "A-TIER PLAYS"), ("B", "B-TIER"), ("C", "C-TIER (0.3x / track)")):
        if by_tier.get(tier):
            md.append(f"## === {label} ===")
            md += [_pick_block(i + 1, p) for i, p in enumerate(by_tier[tier])]
            md.append("")

    md.append("## === SLIP OF THE DAY (PrizePicks/Underdog) ===")
    if slips:
        for s in slips:
            legs = " + ".join(f"{l.player} {l.side} {l.line} ({l.market})" for l in s["legs"])
            note = f" | {'; '.join(s['notes'])}" if s["notes"] else ""
            md.append(f"- {len(s['legs'])}-leg: {legs}")
            md.append(f"  Combined model prob {s['combined_prob']:.1%} vs "
                      f"{s['breakeven']:.1%} breakeven | EV {s['ev']:+.1%}{note}")
    else:
        md.append("(no slip cleared the breakeven-with-margin bar today)")
    md.append("")

    md.append("## === NO-PLAYS THAT LOOKED TEMPTING (and why we passed) ===")
    if no_plays:
        for np_ in no_plays:
            md.append(f"- {np_['player'] or 'game'} {np_['side']} {np_['line']} "
                      f"{np_['market']}: EV {np_['ev']:+.1%} — {np_['reason']}")
    else:
        md.append("(none near the threshold today)")
    md.append("")

    md.append("## === YESTERDAY'S RESULTS + CLV GRADES ===")
    md += _yesterday_section(conn, day)
    md.append("")
    return "\n".join(md)


def write_report(conn, day: str | None = None, no_plays: list[dict] | None = None,
                 slips: list[dict] | None = None) -> str:
    day = day or date_cls.today().isoformat()
    md = render(conn, day, no_plays, slips)
    reports_dir = config.REPO_ROOT / config.settings()["paths"]["reports"]
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"{day}.md"
    path.write_text(md)
    deliver(md)
    return str(path)


def deliver(md: str) -> None:
    """Optional delivery (spec §6): Discord webhook and/or SMTP email."""
    hook = os.environ.get("DISCORD_WEBHOOK_URL")
    if hook and requests is not None:
        try:  # Discord caps content at 2000 chars
            requests.post(hook, json={"content": md[:1900]}, timeout=10)
        except Exception:
            pass
    host, to = os.environ.get("SMTP_HOST"), os.environ.get("EMAIL_TO")
    if host and to:
        try:
            import smtplib
            from email.message import EmailMessage
            msg = EmailMessage()
            msg["Subject"] = md.splitlines()[0].lstrip("# ")
            msg["From"] = os.environ.get("SMTP_USER", "edge-engine")
            msg["To"] = to
            msg.set_content(md)
            with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587"))) as s:
                s.starttls()
                user, pw = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASS")
                if user and pw:
                    s.login(user, pw)
                s.send_message(msg)
        except Exception:
            pass
