"""Profile badges: the other platforms where an account takes part, with a link to its profile there (read-only)."""

import json
import os
import sqlite3

import pytest

pytest.importorskip("ysocial_federation", reason="the federation SDK is not installed")

from jinja2 import Environment, FileSystemLoader  # noqa: E402

from y_web.src.federation import profile_badges as pb, service  # noqa: E402
from y_web.tests.test_federation_humans import Offline, make, user  # noqa: E402,F401
from y_web.tests.test_federation_service import world  # noqa: E402,F401  (fixture)

TEMPLATES = os.path.join(os.path.dirname(__file__), "..", "templates")


def accounts(fed, gid):
    from y_web.src.models.admin import FederationIdentityLink

    return {l.member: l.local_account_id for l in FederationIdentityLink.query.filter_by(federation_pk=fed.id, global_agent_id=gid)}


def first_agent(fed):
    from y_web.src.models.admin import FederationIdentityLink

    return FederationIdentityLink.query.filter_by(federation_pk=fed.id, member="forum").order_by(FederationIdentityLink.id).first().global_agent_id


def test_each_profile_links_to_the_other_platforms_of_the_same_agent(world):
    fed, _ = make(world)
    _, exps, _ = world
    gid = first_agent(fed)
    acc = accounts(fed, gid)
    on_forum = pb.badges_for(exps["forum"], acc["forum"])
    assert on_forum == [{"member": "microblogging", "platform_type": "microblogging", "label": "Microblogging",
                         "href": f"/{exps['microblogging']}/profile/{acc['microblogging']}/recent/1"}]
    on_micro = pb.badges_for(exps["microblogging"], acc["microblogging"])
    assert [b["member"] for b in on_micro] == ["forum"] and on_micro[0]["href"] == f"/{exps['forum']}/profile/{acc['forum']}/recent/1"


def test_nothing_for_an_account_outside_a_world_simulation_or_without_identity(world):
    _, exps, _ = world
    assert pb.badges_for(exps["forum"], "1") == []  # no federation yet
    fed, _ = make(world)
    assert pb.badges_for(exps["forum"], "no-such-account") == [] and pb.badges_for(None, "1") == [] and pb.badges_for(exps["forum"], None) == []
    assert pb.badges_for(99999, "1") == []


def test_the_url_of_every_platform():
    assert pb.profile_href("photo_sharing", 3, "u") == "/3/photo/profile/u/recent/1"
    assert pb.profile_href("instant_messaging", 3, "u") == "/3/im/profile/u"
    assert pb.profile_href("dating", 3, "u") == "/3/dating/profile/u"
    assert pb.profile_href("unknown", 3, "u") is None


def test_an_agent_that_is_dormant_or_left_on_a_platform_is_not_shown_there(world):
    fed, _ = make(world)
    _, exps, _ = world
    gid = first_agent(fed)
    acc = accounts(fed, gid)
    conn = sqlite3.connect(os.path.join(fed.folder, "federation.db"))
    conn.execute("CREATE TABLE federation_identity (global_agent_id TEXT, member TEXT, local_account_id TEXT, state TEXT)")
    conn.execute("INSERT INTO federation_identity VALUES (?,?,?,?)", (gid, "microblogging", acc["microblogging"], "dormant"))
    conn.execute("INSERT INTO federation_identity VALUES (?,?,?,?)", (gid, "forum", acc["forum"], "active"))
    conn.commit()
    conn.close()
    assert pb.badges_for(exps["forum"], acc["forum"]) == []
    assert [b["member"] for b in pb.badges_for(exps["microblogging"], acc["microblogging"])] == ["forum"]
    before = os.stat(os.path.join(fed.folder, "federation.db")).st_mtime_ns
    pb.badges_for(exps["forum"], acc["forum"])
    assert os.stat(os.path.join(fed.folder, "federation.db")).st_mtime_ns == before  # read-only


def test_a_person_is_shown_only_where_the_account_exists(world):
    from y_web import db
    from y_web.src.federation import humans
    from y_web.src.models.admin import FederationHuman

    fed, _ = make(world)
    _, exps, _ = world
    humans.enrol(fed, user(), ["forum", "microblogging"], offline=Offline())
    acc = accounts(fed, "human:7")
    assert [b["member"] for b in pb.badges_for(exps["forum"], acc["forum"])] == ["microblogging"]
    row = FederationHuman.query.filter_by(human_id="human:7").one()
    state = json.loads(row.members_json)
    state["microblogging"]["created"] = False  # e.g. a dating profile not filled yet
    row.members_json = json.dumps(state)
    db.session.commit()
    assert pb.badges_for(exps["forum"], acc["forum"]) == []


def render(badges):
    env = Environment(loader=FileSystemLoader(TEMPLATES))
    env.globals.update(ws_profile_badges=lambda exp, acc: badges, _=lambda s, **k: s % k if k else s)
    return env.from_string("{% set ws_exp = 1 %}{% set ws_account = 'a' %}{% include 'shared/world_simulation_profile_badges.html' %}").render()


def test_the_partial_renders_one_link_per_badge_and_nothing_without(world):
    assert render([]).strip() == ""
    html = render([{"member": "forum", "label": "Forum", "href": "/2/profile/9/recent/1"},
                   {"member": "photo_sharing", "label": "Photo sharing", "href": "/3/photo/profile/5/recent/1"}])
    assert html.count('class="ws-profile-badge"') == 2 and 'href="/2/profile/9/recent/1"' in html and ">Photo sharing<" in html


@pytest.mark.parametrize("name", ["microblogging", "forum", "photo", "dating", "im"])
def test_every_profile_page_includes_the_badges(name):
    text = open(os.path.join(TEMPLATES, name, "profile.html"), encoding="utf-8").read()
    assert "shared/world_simulation_profile_badges.html" in text
