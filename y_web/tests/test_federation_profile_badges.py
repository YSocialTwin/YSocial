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
    """The accounts the runtimes created for the agent: the coordinator learns them by username (INV-17)."""
    from y_web.src.models.admin import FederationIdentityLink

    return {l.member: (l.local_account_id or f"{l.member}-{gid}") for l in FederationIdentityLink.query.filter_by(federation_pk=fed.id, global_agent_id=gid)}


def bind_all(fed):
    """A coordinator database in which every expected identity has been bound by its runtime."""
    from y_web.src.models.admin import FederationIdentityLink

    conn = sqlite3.connect(os.path.join(fed.folder, "federation.db"))
    conn.execute("CREATE TABLE IF NOT EXISTS federation_identity (global_agent_id TEXT, member TEXT, local_account_id TEXT, state TEXT)")
    for l in FederationIdentityLink.query.filter_by(federation_pk=fed.id):
        if l.username:
            conn.execute("INSERT INTO federation_identity VALUES (?,?,?,?)", (l.global_agent_id, l.member, f"{l.member}-{l.global_agent_id}", "active"))
    conn.commit()
    conn.close()


def first_agent(fed):
    from y_web.src.models.admin import FederationIdentityLink

    return FederationIdentityLink.query.filter_by(federation_pk=fed.id, member="forum").order_by(FederationIdentityLink.id).first().global_agent_id


def open_interfaces(*exp_ids):
    """The web interface of an experiment is active (``Exps.status == 1``): only then does a chip link to its profile."""
    from y_web import db
    from y_web.src.models.admin import Exps

    for exp_id in exp_ids:
        db.session.get(Exps, exp_id).status = 1
    db.session.commit()


def test_each_profile_links_to_the_other_platforms_of_the_same_agent(world):
    fed, _ = make(world)
    _, exps, _ = world
    gid = first_agent(fed)
    acc = accounts(fed, gid)
    bind_all(fed)
    open_interfaces(*exps.values())
    on_forum = pb.badges_for(exps["forum"], acc["forum"])
    assert on_forum == [{"member": "microblogging", "platform_type": "microblogging", "label": "microblogging",
                         "exp_id": exps["microblogging"], "icon": "message-circle", "state": "active", "active": True,
                         "handle": None, "crossposts": None, "href": f"/{exps['microblogging']}/profile/{acc['microblogging']}/recent/1"}]
    on_micro = pb.badges_for(exps["microblogging"], acc["microblogging"])
    assert [b["member"] for b in on_micro] == ["forum"] and on_micro[0]["href"] == f"/{exps['forum']}/profile/{acc['forum']}/recent/1"


def test_the_label_is_the_experiment_name_never_the_platform_type(world):
    from y_web import db
    from y_web.src.models.admin import Exps

    fed, _ = make(world)
    _, exps, _ = world
    acc = accounts(fed, first_agent(fed))
    bind_all(fed)
    db.session.get(Exps, exps["microblogging"]).exp_name = "XW"
    db.session.commit()
    badge = pb.badges_for(exps["forum"], acc["forum"])[0]
    assert badge["label"] == "XW" and badge["platform_type"] == "microblogging" and badge["icon"] == "message-circle"


def test_a_chip_has_no_link_while_the_interface_of_that_experiment_is_not_active(world):
    fed, _ = make(world)
    _, exps, _ = world
    acc = accounts(fed, first_agent(fed))
    bind_all(fed)  # the fixture experiments are stopped (status 0)
    badge = pb.badges_for(exps["forum"], acc["forum"])[0]
    assert badge["href"] is None and badge["state"] == "active"
    open_interfaces(exps["microblogging"])
    assert pb.badges_for(exps["forum"], acc["forum"])[0]["href"].startswith(f"/{exps['microblogging']}/profile/")


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


def coordinator(fed, rows):
    conn = sqlite3.connect(os.path.join(fed.folder, "federation.db"))
    conn.execute("CREATE TABLE IF NOT EXISTS federation_identity (global_agent_id TEXT, member TEXT, local_account_id TEXT, state TEXT)")
    conn.executemany("INSERT INTO federation_identity VALUES (?,?,?,?)", rows)
    conn.commit()
    conn.close()


@pytest.mark.parametrize("state", ["dormant", "left", "ineligible"])
def test_an_agent_that_is_not_active_on_a_platform_is_shown_muted_not_hidden(world, state):
    fed, _ = make(world)
    _, exps, _ = world
    gid = first_agent(fed)
    acc = accounts(fed, gid)
    open_interfaces(*exps.values())
    coordinator(fed, [(gid, "microblogging", acc["microblogging"], state), (gid, "forum", acc["forum"], "active")])
    shown = pb.badges_for(exps["forum"], acc["forum"])
    assert [(b["member"], b["state"], b["active"]) for b in shown] == [("microblogging", state, False)]
    assert shown[0]["href"]  # the profile still exists: the chip links to it while the interface is active
    assert [(b["member"], b["active"]) for b in pb.badges_for(exps["microblogging"], acc["microblogging"])] == [("forum", True)]
    before = os.stat(os.path.join(fed.folder, "federation.db")).st_mtime_ns
    pb.badges_for(exps["forum"], acc["forum"])
    assert os.stat(os.path.join(fed.folder, "federation.db")).st_mtime_ns == before  # read-only


def test_active_platforms_come_first_and_the_handle_is_shown_only_when_different(world, monkeypatch):
    fed, _ = make(world)
    _, exps, _ = world
    gid = first_agent(fed)
    acc = accounts(fed, gid)
    bind_all(fed)
    names = {exps["forum"]: "mara_rossi", exps["microblogging"]: "mara_rossi"}
    monkeypatch.setattr(pb, "_handle", lambda exp, ptype, account: names.get(exp.idexp))
    assert pb.badges_for(exps["forum"], acc["forum"])[0]["handle"] is None  # the same username on both
    names[exps["microblogging"]] = "mara.shots"
    assert pb.badges_for(exps["forum"], acc["forum"])[0]["handle"] == "mara.shots"


def test_the_crosspost_figure_comes_from_one_grouped_read_per_request(world, monkeypatch):
    from y_web.src.federation import agent_states

    fed, _ = make(world)
    _, exps, _ = world
    gid = first_agent(fed)
    acc = accounts(fed, gid)
    bind_all(fed)
    calls = []
    monkeypatch.setattr(agent_states, "_stats", lambda folder: calls.append(folder) or {gid: {"by_dest": {"microblogging": 5}}})
    assert pb.badges_for(exps["forum"], acc["forum"])[0]["crossposts"] == 5
    assert pb.badges_for(exps["forum"], acc["forum"])[0]["crossposts"] == 5 and len(calls) == 1  # cached for the rest of the request
    from flask import g

    g.pop("_ws_badge_stats", None)
    monkeypatch.setattr(agent_states, "_stats", lambda folder: (_ for _ in ()).throw(RuntimeError("no figures")))
    assert pb.badges_for(exps["forum"], acc["forum"])[0]["crossposts"] is None  # optional: a failure never breaks the page


def test_the_number_of_chips_is_bounded(world, monkeypatch):
    fed, _ = make(world)
    _, exps, _ = world
    acc = accounts(fed, first_agent(fed))
    bind_all(fed)
    monkeypatch.setattr(pb, "MAX_BADGES", 0)
    assert pb.badges_for(exps["forum"], acc["forum"]) == []


def test_the_handle_lookup_is_read_only_and_tolerates_a_missing_database(world, tmp_path):
    from y_web.src.models.admin import Exps

    _, exps, _ = world
    assert pb._handle(Exps.query.get(exps["forum"]), "forum", "1") is None  # no database yet
    assert pb._handle(None, "forum", "1") is None and pb._handle(Exps.query.get(exps["forum"]), "unknown", "1") is None
    assert set(pb.USERNAME_SQL) == set(pb.PROFILE_PATHS)


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


VARIANTS = ("microblogging", "forum", "photo", "dating", "im")
CHIPS = [{"member": "xw", "platform_type": "microblogging", "label": "XW", "icon": "message-circle", "href": "/2/profile/9/recent/1",
          "state": "active", "active": True, "handle": "mara_rossi", "crossposts": 14},
         {"member": "pw", "platform_type": "photo_sharing", "label": "Photo Lab", "icon": "camera", "href": "/3/photo/profile/5/recent/1",
          "state": "dormant", "active": False, "handle": None, "crossposts": None},
         {"member": "im", "platform_type": "instant_messaging", "label": "TeleTwin", "icon": "send", "href": None,
          "state": "left", "active": False, "handle": None, "crossposts": None}]


def render(badges, variant=None):
    env = Environment(loader=FileSystemLoader(TEMPLATES))
    env.globals.update(ws_profile_badges=lambda exp, acc: badges, _=lambda s, **k: s % k if k else s)
    chosen = f"{{% set ws_variant = '{variant}' %}}" if variant else ""
    return env.from_string("{% set ws_exp = 1 %}{% set ws_account = 'a' %}" + chosen + "{% include 'shared/world_simulation_profile_badges.html' %}").render()


def test_the_partial_renders_one_link_per_badge_and_nothing_without(world):
    assert render([]).strip() == ""
    html = render([{"member": "forum", "label": "FW", "icon": "message-square", "href": "/2/profile/9/recent/1", "state": "active", "active": True},
                   {"member": "photo_sharing", "label": "PW", "icon": "camera", "href": "/3/photo/profile/5/recent/1", "state": "active", "active": True}])
    assert html.count('class="ws-also-chip"') == 2 and 'href="/2/profile/9/recent/1"' in html and ">PW</span>" in html and "Photo sharing" not in html and "<svg" in html


@pytest.mark.parametrize("variant", VARIANTS)
def test_every_variant_renders_nothing_without_badges_and_the_same_chips_with(variant):
    assert render([], variant).strip() == ""
    html = render(CHIPS, variant)
    assert f"ws-also--{variant}" in html and "data-ws-profile-badges" in html
    # names of the experiments, never the platform type (it is only the icon)
    for label in ("XW", "Photo Lab", "TeleTwin"):
        assert f">{label}</span>" in html
    for kind in ("Microblogging", "Photo sharing", "Instant messaging", "microblogging", "photo_sharing"):
        assert kind not in html.replace("ws-also--microblogging", "").replace("ws-also--photo", "")
    assert html.count("<svg") == 3 and 'aria-hidden="true"' in html
    # the chip of an interface that is not active is not a link: a muted element with a tooltip that says why
    assert html.count("<a ") == 2 and 'class="ws-also-chip is-left is-nolink"' in html and "is not running" in html
    assert 'class="ws-also-chip is-dormant"' in html and 'data-ws-state="dormant"' in html and "Dormant there" in html
    assert "Cross-posts delivered there: 14" in html and "Username there: mara_rossi" in html
    assert "<style" not in html and "style=" not in html.replace('style="vertical-align:-2px"', "")  # styled by the stylesheet of the frontend


def test_each_variant_reuses_the_components_of_its_frontend():
    assert 'class="forum-profile-card ws-also ws-also--forum"' in render(CHIPS, "forum") and "forum-profile-about-row" in render(CHIPS, "forum")
    assert 'class="photo-profile-links ws-also ws-also--photo"' in render(CHIPS, "photo")
    assert 'class="dt-pf-facts ws-also ws-also--dating"' in render(CHIPS, "dating") and "<li" in render(CHIPS, "dating")
    assert 'class="im-card ws-also ws-also--im"' in render(CHIPS, "im") and "<dl class=\"im-facts\">" in render(CHIPS, "im")
    assert 'class="ws-also ws-also--microblogging"' in render(CHIPS) and render(CHIPS) == render(CHIPS, "microblogging")


@pytest.mark.parametrize("name", ["microblogging", "forum", "photo", "dating", "im"])
def test_every_profile_page_includes_the_badges(name):
    text = open(os.path.join(TEMPLATES, name, "profile.html"), encoding="utf-8").read()
    assert "shared/world_simulation_profile_badges.html" in text
    variant = {"microblogging": "microblogging", "forum": "forum", "photo": "photo", "dating": "dating", "im": "im"}[name]
    assert f"{{% set ws_variant = '{variant}' %}}" in text


@pytest.mark.parametrize("name", VARIANTS)
def test_every_variant_has_its_style_in_the_stylesheet_of_its_frontend(name):
    css = {"microblogging": "social-components.css", "photo": "social-components.css", "forum": "reddit/forum-components.css",
           "dating": "dating.css", "im": "im.css"}[name]
    text = open(os.path.join(TEMPLATES, "..", "static", "assets", "css", css), encoding="utf-8").read()
    assert f".ws-also--{name}" in text and (".is-quiet" if name == "dating" else ".is-dormant") in text and ".is-nolink" in text


def test_the_new_texts_are_translated_into_italian_and_only_there():
    from babel.messages import mofile, pofile

    base = os.path.join(TEMPLATES, "..", "translations")
    texts = ["%(platform)s is not running: its profile cannot be opened now", "Dormant there: the agent takes a break on this platform",
             "Left this platform", "Not active there", "Username there: %(name)s", "Cross-posts delivered there: %(n)s", "Dormant", "Also on"]
    po = pofile.read_po(open(os.path.join(base, "it", "LC_MESSAGES", "messages.po"), "rb"))
    pot = pofile.read_po(open(os.path.join(base, "messages.pot"), "rb"))
    mo = mofile.read_mo(open(os.path.join(base, "it", "LC_MESSAGES", "messages.mo"), "rb"))
    for text in texts:
        assert po[text] is not None and po[text].string and po[text].string != text  # Italian only in the .po
        assert pot[text] is not None and not pot[text].string  # the template stays empty
        assert mo[text].string == po[text].string  # and the .mo is recompiled
    source = open(os.path.join(TEMPLATES, "shared", "world_simulation_profile_badges.html"), encoding="utf-8").read()
    assert "in pausa" not in source.lower() and "consegnati" not in source


def test_an_agent_whose_accounts_are_not_reported_yet_has_no_badges(world):
    fed, _ = make(world)
    _, exps, _ = world
    gid = first_agent(fed)
    assert pb.badges_for(exps["forum"], f"forum-{gid}") == []  # nothing is bound: the profile page does not know the account yet
    bind_all(fed)
    assert [b["member"] for b in pb.badges_for(exps["forum"], f"forum-{gid}")] == ["microblogging"]
