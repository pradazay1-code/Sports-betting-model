"""On-the-spot alerts: push a notification the moment a strong pick lands.

Two free channels, either or both:

- **Phone push** via https://ntfy.sh — no account, no key. Set NOTIFY_NTFY_TOPIC
  to any hard-to-guess string, install the free ntfy app, subscribe to that
  topic, and every qualifying pick pings your phone instantly.
- **Email** via SMTP (Gmail). Set NOTIFY_EMAIL_FROM, NOTIFY_EMAIL_APP_PASSWORD
  (a Google *app password*, not your login), and NOTIFY_EMAIL_TO.

Alerts only fire for picks graded at or above NOTIFY_MIN_GRADE (default "A-"),
and each pick is sent once — a small alerts_sent table de-dupes so repeated
pipeline runs during the slate don't spam you.
"""

from __future__ import annotations

import os
import smtplib
from email.mime.text import MIMEText

from app.analysis import GRADES, _letter_from
from app.store import connection
from app.utils import get_logger

LOG = get_logger("notify")


def _min_grade() -> str:
    g = os.environ.get("NOTIFY_MIN_GRADE", "A-")
    return g if g in GRADES else "A-"


def _grade_ok(grade: str) -> bool:
    try:
        return GRADES.index(grade) >= GRADES.index(_min_grade())
    except ValueError:
        return False


def _pick_key(on_date: str, p: dict) -> str:
    return f"{on_date}|{p.get('sport')}|{p.get('player_name')}|{p.get('market')}|{p.get('side')}|{p.get('line')}"


def _already_sent(key: str) -> bool:
    with connection() as conn:
        row = conn.execute("SELECT 1 FROM alerts_sent WHERE alert_key=?", (key,)).fetchone()
        return row is not None


def _mark_sent(key: str) -> None:
    from app.utils import now_iso
    with connection() as conn:
        conn.execute("INSERT OR IGNORE INTO alerts_sent (alert_key, sent_at) VALUES (?, ?)",
                     (key, now_iso()))


# ---- channels ------------------------------------------------------------


def send_push(title: str, message: str) -> bool:
    topic = os.environ.get("NOTIFY_NTFY_TOPIC")
    if not topic:
        return False
    import httpx
    try:
        with httpx.Client(timeout=15) as c:
            c.post(f"https://ntfy.sh/{topic}", content=message.encode("utf-8"),
                   headers={"Title": title, "Priority": "high", "Tags": "dart"})
        return True
    except Exception as e:  # noqa: BLE001
        LOG.warning("ntfy push failed: %s", e)
        return False


def send_email(subject: str, body: str) -> bool:
    frm = os.environ.get("NOTIFY_EMAIL_FROM")
    pwd = os.environ.get("NOTIFY_EMAIL_APP_PASSWORD")
    to = os.environ.get("NOTIFY_EMAIL_TO") or frm
    if not (frm and pwd and to):
        return False
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = frm
    msg["To"] = to
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as s:
            s.starttls()
            s.login(frm, pwd)
            s.sendmail(frm, [a.strip() for a in to.split(",")], msg.as_string())
        return True
    except Exception as e:  # noqa: BLE001
        LOG.warning("email send failed: %s", e)
        return False


def channels_configured() -> bool:
    return bool(os.environ.get("NOTIFY_NTFY_TOPIC") or (
        os.environ.get("NOTIFY_EMAIL_FROM") and os.environ.get("NOTIFY_EMAIL_APP_PASSWORD")))


# ---- formatting + entry point -------------------------------------------


def _line(p: dict) -> str:
    grade = p.get("grade") or _letter_from(p.get("rating", 0.0), p.get("edge_pct", 0.0))
    price = p.get("price_american")
    price = (f"+{price}" if isinstance(price, (int, float)) and price >= 0 else str(price))
    return (f"{grade} | {p.get('sport')} {p.get('player_name')} "
            f"{str(p.get('side','')).upper()} {p.get('line')} {(p.get('market') or '').replace('_',' ')} "
            f"@ {price} ({p.get('book','')}) — edge +{p.get('edge_pct',0):.1f}%")


def alert_for_picks(picks: list[dict], on_date: str) -> int:
    """Send one alert bundling every new qualifying pick. Returns # sent."""
    if not channels_configured():
        LOG.info("notify: no channels configured — skipping alerts")
        return 0
    qualifying = []
    for p in picks:
        grade = p.get("grade") or _letter_from(p.get("rating", 0.0), p.get("edge_pct", 0.0))
        if not _grade_ok(grade):
            continue
        key = _pick_key(on_date, p)
        if _already_sent(key):
            continue
        qualifying.append((key, p))
    if not qualifying:
        return 0

    lines = [_line(p) for _, p in qualifying]
    title = f"🎯 {len(lines)} new {_min_grade()}+ pick(s) — {on_date}"
    body = title + "\n\n" + "\n".join(lines) + "\n\nPradapicks — bet responsibly."
    sent_push = send_push(title, "\n".join(lines))
    sent_email = send_email(title, body)
    if sent_push or sent_email:
        for key, _ in qualifying:
            _mark_sent(key)
        LOG.info("notify: alerted %d picks (push=%s email=%s)", len(lines), sent_push, sent_email)
        return len(lines)
    return 0
