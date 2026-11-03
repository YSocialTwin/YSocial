"""Execution tab, Cross-posts line in agent_action mode: the members emit crosspost.v1 (not content.v1) and the line says so."""

import json
import os
import sqlite3

import pytest

pytest.importorskip("ysocial_federation", reason="the federation SDK is not installed")

from y_web.src.federation import service  # noqa: E402
from y_web.tests.test_federation_service import world  # noqa: E402,F401  (fixture)
from y_web.tests.test_world_simulation_crosspost_warning import (  # noqa: E402,F401
    make_run,
    status_of,
)
from y_web.tests.test_world_simulation_ui import (  # noqa: E402,F401  (fixtures and helper)
    login,
    site,
)

AGENT = {"crosspost": {"mode": "agent_action", "decision": "llm", "propensity": 0.4}}


def add(fed, rows, delivered=()):
    """Messages ``(id, source, target, payload_type)`` and the ids that were delivered (as in the World Simulation 1 run)."""
    db = sqlite3.connect(
        os.path.join(fed.folder, "federation.db"), isolation_level=None
    )
    for i, source, target, kind in rows:
        db.execute(
            "INSERT INTO federation_message VALUES (?,?,?,?,?,?,?)",
            (i, source, target, 2, 3, kind, "{}"),
        )
    for i in delivered:
        db.execute(
            "INSERT INTO federation_delivery VALUES (?,?,?)", (i, "microblogging", 3)
        )
    db.close()


def test_agent_action_counts_the_messages_sent_by_the_agents(site):
    app, exps, tmp = site
    fed = service.create_federation(
        "W", list(exps.values()), owner="admin", options=AGENT
    )
    make_run(
        fed
    )  # no crosspost_materialized event: they exist only with the coordinator rule
    add(
        fed,
        [(f"1:forum:2:{n}", "forum", "microblogging", "crosspost.v1") for n in range(4)]
        + [
            ("1:micro:2:1", "microblogging", "forum", "crosspost.v1"),
            ("e1", "microblogging", "coordinator", "exposure.v1"),
        ],
        delivered=[f"1:forum:2:{n}" for n in range(3)] + ["1:micro:2:1"],
    )
    data = status_of(app, fed)["crossposts"]
    assert (
        data["text"]
        == "Cross-posts: 5 sent by the agents (forum → microblogging: 4, microblogging → forum: 1) · delivered: 4"
    )
    assert (data["sent"], data["delivered"], data["mode"], data["hint"]) == (
        5,
        4,
        "agent_action",
        None,
    )


def test_the_run_of_world_simulation_1_is_not_reported_as_zero(site, monkeypatch):
    app, exps, tmp = site
    fed = service.create_federation(
        "W", list(exps.values()), owner="admin", options=AGENT
    )
    make_run(fed)
    add(
        fed,
        [
            (f"1:forum:{t}:{n}", "forum", "microblogging", "crosspost.v1")
            for t, n in ((2, 2), (2, 3), (3, 2), (3, 3), (4, 2), (4, 3))
        ],
        delivered=[
            f"1:forum:{t}:{n}"
            for t, n in ((2, 2), (2, 3), (3, 2), (3, 3), (4, 2), (4, 3))
        ],
    )
    fed.status = "running"
    data = status_of(app, fed, monkeypatch, tick=10)["crossposts"]
    assert (
        data["text"]
        == "Cross-posts: 6 sent by the agents (forum → microblogging: 6) · delivered: 6"
        and data["hint"] is None
    )


def test_the_notice_in_agent_action_needs_no_crosspost_message(site, monkeypatch):
    app, exps, tmp = site
    fed = service.create_federation(
        "W", list(exps.values()), owner="admin", options=AGENT
    )
    make_run(fed)
    add(
        fed, [("c1", "forum", "coordinator", "content.v1")]
    )  # content.v1 does not count in this mode
    fed.status = "running"
    data = status_of(app, fed, monkeypatch, tick=9)["crossposts"]
    assert data["text"] == "Cross-posts: 0 sent by the agents (-) · delivered: 0"
    assert data["hint"].startswith(
        "No content has been marked for cross-posting after 9 ticks."
    )
    assert (
        status_of(app, fed, monkeypatch, tick=6)["crossposts"]["hint"] is None
    )  # not before tick 7
    add(fed, [("x1", "forum", "microblogging", "crosspost.v1")])
    assert status_of(app, fed, monkeypatch, tick=9)["crossposts"]["hint"] is None


def test_the_coordinator_rule_line_is_unchanged(site, monkeypatch):
    app, exps, tmp = site
    fed = service.create_federation(
        "W",
        list(exps.values()),
        owner="admin",
        options={"crosspost": {"mode": "coordinator_rule"}},
    )
    make_run(fed, ticks=[(2, 3)], messages=["content.v1"] * 2 + ["crosspost.v1"])
    assert (
        status_of(app, fed)["crossposts"]["text"]
        == "Cross-posts: 3 materialised (in 1 ticks) · content exported: 2"
    )


def test_the_italian_line():
    from babel.messages.pofile import read_po

    po = read_po(
        open(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "translations",
                "it",
                "LC_MESSAGES",
                "messages.po",
            ),
            "rb",
        )
    )
    message = po.get(
        "Cross-posts: %(sent)s sent by the agents (%(directions)s) · delivered: %(delivered)s"
    )
    assert (
        message is not None
        and "%(sent)s" in message.string
        and "%(delivered)s" in message.string
    )
