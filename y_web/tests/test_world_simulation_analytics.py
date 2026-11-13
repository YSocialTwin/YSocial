"""F7.2: analytics of a World Simulation (data, CSV, manual recalculation, tab in the detail page, access rules)."""

import json
import os
import sqlite3

import pytest

pytest.importorskip("ysocial_federation", reason="the federation SDK is not installed")

from ysocial_federation.coordinator.db import SCHEMA  # noqa: E402

from y_web.tests.test_federation_service import world  # noqa: E402,F401  (fixture)
from y_web.tests.test_world_simulation_ui import (  # noqa: E402,F401  (fixtures and helper)
    login,
    site,
)

BASE = "/admin/world_simulation"


def make(site, owner="admin", with_data=True):
    from y_web.src.federation import service

    app, exps, tmp = site
    fed = service.create_federation("W", list(exps.values()), owner=owner)
    if with_data:
        db = sqlite3.connect(
            os.path.join(fed.folder, "federation.db"), isolation_level=None
        )
        db.executescript(SCHEMA)
        db.execute("INSERT INTO federation_attention VALUES ('a1','forum',0,1.0,1.0)")
        db.execute(
            "INSERT INTO federation_message VALUES ('1:0','coordinator','forum',3,4,'crosspost.v1',?)",
            (json.dumps({"source_ref": "ysocial://1/microblogging/post/1"}),),
        )
        db.execute("INSERT INTO federation_affective VALUES ('forum',0,'a1',0,0,0,0)")
        db.close()
    return fed


def test_the_analytics_are_served_built_on_first_use(site):
    fed = make(site)
    data = login(site[0], "admin").get(f"{BASE}/{fed.id}/analytics.json").get_json()
    assert data["state"]["state"] == "fresh"
    assert data["tables"]["daily_attention"] == [
        {"day": 0, "member": "forum", "agents": 1, "weight": 1.0, "share": 1.0}
    ]
    assert data["tables"]["crosspost_flows"] == [
        {"day": 0, "source": "microblogging", "target": "forum", "n": 1}
    ]


def test_without_a_run_the_data_are_empty_and_the_csv_is_not_found(site):
    fed = make(site, with_data=False)
    client = login(site[0], "admin")
    data = client.get(f"{BASE}/{fed.id}/analytics.json").get_json()
    assert data["tables"] == {} and data["state"]["state"] == "never"
    assert client.get(f"{BASE}/{fed.id}/analytics/survival.csv").status_code == 404


def test_csv_of_a_table_and_unknown_tables(site):
    fed = make(site)
    client = login(site[0], "admin")
    res = client.get(f"{BASE}/{fed.id}/analytics/crosspost_flows.csv")
    assert res.status_code == 200 and res.mimetype == "text/csv"
    assert res.get_data(as_text=True).splitlines() == [
        "day,source,target,n",
        "0,microblogging,forum,1",
    ]
    assert client.get(f"{BASE}/{fed.id}/analytics/etl_state.csv").status_code == 404


def test_manual_recalculation_redirects_to_the_analytics_tab(site):
    fed = make(site)
    res = login(site[0], "admin").post(f"{BASE}/{fed.id}/analytics/rebuild")
    assert res.status_code == 302 and res.headers["Location"].endswith(
        f"{BASE}/{fed.id}#analytics"
    )
    assert os.path.isfile(os.path.join(fed.folder, "analytics_federation.db"))


def test_the_detail_page_has_the_analytics_tab(site):
    fed = make(site)
    html = login(site[0], "admin").get(f"{BASE}/{fed.id}").get_data(as_text=True)
    assert (
        'data-ws-tab="analytics"' in html
        and 'data-ws-pane="analytics"' in html
        and "ws-chart-survival" in html
    )


def test_access_rules(site):
    fed = make(site, owner="admin")
    assert (
        login(site[0], "teacher").get(f"{BASE}/{fed.id}/analytics.json").status_code
        == 403
    )
    assert (
        login(site[0], "researcher").get(f"{BASE}/{fed.id}/analytics.json").status_code
        == 404
    )  # not the owner
