"""Agents tab of a World Simulation: who is active on which platform, read from the coordinator (read-only)."""

import csv
import io
import os
import sqlite3

import pytest

pytest.importorskip("ysocial_federation", reason="the federation SDK is not installed")

from y_web.src.federation import agent_states as ast, service  # noqa: E402
from y_web.tests.test_federation_humans import Offline, make, user  # noqa: E402,F401
from y_web.tests.test_federation_service import world  # noqa: E402,F401  (fixture)
from y_web.tests.test_world_simulation_ui import login, site  # noqa: E402,F401  (fixtures)


def coordinator(fed, rows, kinds=()):
    conn = sqlite3.connect(os.path.join(fed.folder, "federation.db"))
    conn.execute("CREATE TABLE federation_identity (global_agent_id TEXT, member TEXT, local_account_id TEXT, state TEXT, joined_tick INTEGER, left_tick INTEGER)")
    conn.execute("CREATE TABLE federation_identity_kind (global_agent_id TEXT PRIMARY KEY, kind TEXT)")
    conn.executemany("INSERT INTO federation_identity VALUES (?,?,?,?,?,?)", rows)
    conn.executemany("INSERT INTO federation_identity_kind VALUES (?,?)", kinds)
    conn.commit()
    conn.close()


def two_agents(fed):
    from y_web.src.models.admin import FederationIdentityLink

    ids = sorted({l.global_agent_id for l in FederationIdentityLink.query.filter_by(federation_pk=fed.id)})
    return ids[0], ids[1]


def test_before_the_first_run_every_account_is_not_started(world):
    fed, _ = make(world)
    data = ast.table(fed)
    assert data["source"] == "links" and data["members"] == ["forum", "microblogging"]
    assert len(data["rows"]) == 3 and all(c["state"] == "not started" for r in data["rows"] for c in r["states"].values())
    assert {r["name"] for r in data["rows"]} == {"a0", "a1", "a2"}


def test_states_come_from_the_coordinator_and_can_be_filtered_and_counted(world):
    fed, _ = make(world)
    a, b = two_agents(fed)
    coordinator(fed, [(a, "forum", a, "active", 0, None), (a, "microblogging", a, "dormant", 0, None),
                      (b, "forum", b, "left", 0, 48), (b, "microblogging", b, "active", 0, None)])
    data = ast.table(fed)
    assert data["source"] == "coordinator"
    by = {r["id"]: r for r in data["rows"]}
    assert by[a]["states"]["microblogging"]["state"] == "dormant" and by[b]["states"]["forum"]["left"] == 48
    only_active_forum = ast.filtered(data, member="forum", state="active")
    assert [r["id"] for r in only_active_forum] == [a]
    assert {r["id"] for r in ast.filtered(data, state="left")} == {b}
    assert [r["name"] for r in ast.filtered(data, query="A1")] == [by[x]["name"] for x in by if by[x]["name"] == "a1"]
    counts = ast.counts(data)
    assert counts["forum"] == {"active": 1, "left": 1, "not started": 1} and counts["microblogging"]["dormant"] == 1


def test_a_person_is_listed_with_the_username_and_kind(world):
    from y_web import db
    from y_web.src.models import Admin_users

    fed, _ = make(world)
    db.session.add(Admin_users(id=7, username="giulio", email="g@x.org", password="x", role="researcher", last_seen="2026-01-01"))
    db.session.commit()
    from y_web.src.federation import humans

    humans.enrol(fed, user(), ["forum"], offline=Offline())
    rows = {r["id"]: r for r in ast.table(fed)["rows"]}
    assert rows["human:7"]["kind"] == "human" and rows["human:7"]["name"] == "giulio"
    assert [r["id"] for r in ast.filtered(ast.table(fed), kind="human")] == ["human:7"]
    assert rows["human:7"]["states"].keys() == {"forum"}


def test_the_database_is_never_written(world):
    fed, _ = make(world)
    a, _b = two_agents(fed)
    coordinator(fed, [(a, "forum", a, "active", 0, None)])
    path = os.path.join(fed.folder, "federation.db")
    before = os.stat(path).st_mtime_ns
    ast.table(fed)
    assert os.stat(path).st_mtime_ns == before and not os.path.exists(path + "-wal")


def test_the_page_and_the_csv(site):
    app, exps, _ = site
    fed, _ = make(site)
    a, b = two_agents(fed)
    coordinator(fed, [(a, "forum", a, "active", 0, None), (b, "microblogging", b, "dormant", 0, None)])
    client = login(app, "admin")
    html = client.get(f"/admin/world_simulation/{fed.id}/agents").get_data(as_text=True)
    assert 'id="ws-agent-table"' in html and 'data-state="active"' in html and 'data-state="dormant"' in html
    filtered = client.get(f"/admin/world_simulation/{fed.id}/agents?state=dormant&member=microblogging").get_data(as_text=True)
    assert filtered.count('data-state="dormant"') == 1 and 'data-state="active"' not in filtered
    got = client.get(f"/admin/world_simulation/{fed.id}/agents.csv")
    assert got.mimetype == "text/csv"
    lines = list(csv.reader(io.StringIO(got.get_data(as_text=True))))
    assert lines[0] == ["global_agent_id", "name", "kind", "member", "account_id", "state", "joined_tick", "left_tick", "crossposts_own",
                        "crossposts_of_others", "times_crossposted", "times_crossposted_by_destination"]
    assert (a, "forum", "active") in {(l[0], l[3], l[5]) for l in lines[1:]}
    assert client.get("/admin/world_simulation/99999/agents").status_code == 404
