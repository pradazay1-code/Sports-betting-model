"""Tests for the alerting layer (no real email/push)."""

from __future__ import annotations

import pytest

from app import notify


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    import importlib
    import app.config as cfg; importlib.reload(cfg)
    import app.store as store; importlib.reload(store)
    store.init_db()
    # notify imported store at module load; point it at the fresh one.
    importlib.reload(notify)
    yield store


def _pick(grade="A+", edge=8.0, name="Star Player"):
    return {"sport": "NBA", "player_name": name, "market": "player_points",
            "side": "over", "line": 24.5, "price_american": -110, "book": "dk",
            "edge_pct": edge, "rating": 90.0, "grade": grade}


def test_grade_threshold(monkeypatch):
    monkeypatch.setenv("NOTIFY_MIN_GRADE", "A-")
    assert notify._grade_ok("A+")
    assert notify._grade_ok("A-")
    assert not notify._grade_ok("B+")
    assert not notify._grade_ok("C")


def test_no_channels_is_noop(monkeypatch):
    for v in ("NOTIFY_NTFY_TOPIC", "NOTIFY_EMAIL_FROM", "NOTIFY_EMAIL_APP_PASSWORD"):
        monkeypatch.delenv(v, raising=False)
    assert notify.alert_for_picks([_pick()], "2026-06-25") == 0


def test_alerts_send_once_and_dedupe(monkeypatch):
    monkeypatch.setenv("NOTIFY_NTFY_TOPIC", "test-topic")
    sent = []
    monkeypatch.setattr(notify, "send_push", lambda t, m: (sent.append((t, m)) or True))
    monkeypatch.setattr(notify, "send_email", lambda s, b: False)

    picks = [_pick(name="A"), _pick(name="B"), _pick(grade="C", name="C")]
    n1 = notify.alert_for_picks(picks, "2026-06-25")
    assert n1 == 2                      # only the two A+ picks
    assert len(sent) == 1              # one bundled push
    # Re-running the same slate does not re-alert.
    n2 = notify.alert_for_picks(picks, "2026-06-25")
    assert n2 == 0
