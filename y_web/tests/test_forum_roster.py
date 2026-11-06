"""The roster file of a forum client: dropped for a client that never ran, kept for one with progress."""

import json
from types import SimpleNamespace

from y_web.src.forum.roster import (
    ABSENT,
    KEPT_STARTED,
    REMOVED,
    client_has_started,
    reset_unstarted_roster,
    roster_path,
)


def _config(tmp_path, agents_file=None):
    cfg = tmp_path / "client_c1-pop.json"
    population = {"file": "pop.json"}
    if agents_file:
        population["agents_file"] = agents_file
    cfg.write_text(json.dumps({"population": population}), encoding="utf-8")
    return str(cfg)


def test_roster_path_default_and_configured(tmp_path):
    assert roster_path(_config(tmp_path), "c1").endswith("agents_c1.json")
    assert roster_path(_config(tmp_path, "mine.json"), "c1").endswith("mine.json")
    assert roster_path(str(tmp_path / "missing.json"), "c2").endswith("agents_c2.json")


def test_client_has_started():
    assert not client_has_started(None)
    assert not client_has_started(SimpleNamespace(last_active_day=-1, last_active_hour=-1))
    assert client_has_started(SimpleNamespace(last_active_day=0, last_active_hour=-1))
    assert client_has_started(SimpleNamespace(last_active_day=-1, last_active_hour=3))


def test_unstarted_client_loses_its_roster(tmp_path):
    cfg = _config(tmp_path)
    assert reset_unstarted_roster(cfg, "c1") == ABSENT
    roster = tmp_path / "agents_c1.json"
    roster.write_text("{}", encoding="utf-8")
    ex = SimpleNamespace(last_active_day=-1, last_active_hour=-1)
    assert reset_unstarted_roster(cfg, "c1", ex) == REMOVED
    assert not roster.exists()


def test_started_client_keeps_its_roster(tmp_path):
    cfg = _config(tmp_path)
    roster = tmp_path / "agents_c1.json"
    roster.write_text("{}", encoding="utf-8")
    ex = SimpleNamespace(last_active_day=2, last_active_hour=5)
    assert reset_unstarted_roster(cfg, "c1", ex) == KEPT_STARTED
    assert roster.exists()


def test_opinion_page_hook_discards_roster_of_unstarted_forum_client(tmp_path, monkeypatch):
    from y_web.routes.admin.sub.clients import _opinion as op

    cfg = _config(tmp_path)
    roster = tmp_path / "agents_c1.json"
    roster.write_text("{}", encoding="utf-8")
    flashed = []
    monkeypatch.setattr(op, "flash", lambda msg, cat="message": flashed.append(cat))
    monkeypatch.setattr(op, "_", lambda s, **k: s)
    monkeypatch.setattr("y_web.src.forum.is_forum_hpc_experiment", lambda e: True)
    execution = SimpleNamespace(last_active_day=-1, last_active_hour=-1)
    monkeypatch.setattr(
        op.db.session, "scalars", lambda *a, **k: SimpleNamespace(first=lambda: execution)
    )
    ctx = {
        "exp": object(),
        "client": SimpleNamespace(id=1, name="c1"),
        "client_config_file": cfg,
    }
    op._refresh_forum_roster_after_opinion_change(ctx)
    assert not roster.exists() and flashed == ["info"]

    roster.write_text("{}", encoding="utf-8")
    execution.last_active_day = 1
    op._refresh_forum_roster_after_opinion_change(ctx)
    assert roster.exists() and flashed == ["info", "warning"]
