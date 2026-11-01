"""H3: the Participants section of the World Simulation page and its routes."""

import pytest

pytest.importorskip("ysocial_federation", reason="the federation SDK is not installed")

from y_web.src.federation import humans, service  # noqa: E402
from y_web.tests.test_federation_service import world  # noqa: E402,F401  (fixture the site fixture needs)
from y_web.tests.test_world_simulation_ui import login, site  # noqa: E402,F401  (fixtures and helper)

BASE = "/admin/world_simulation"


@pytest.fixture()
def fake_gateways(monkeypatch):
    calls = []

    def ensurer(platform_type, exp, user, hid, session=None, offline=None):
        calls.append((platform_type, user.username, hid))
        return str(500 + len(calls)), True

    monkeypatch.setattr(humans, "ENSURERS", {k: ensurer for k in humans.ENSURERS})
    return calls


def make(site_fixture, owner="researcher"):
    app, exps, tmp = site_fixture
    return service.create_federation("w", list(exps.values()), owner=owner, seed=1)


def user_id(name):
    from y_web import db
    from y_web.src.models import Admin_users

    return db.session.query(Admin_users).filter_by(username=name).first().id


def test_detail_shows_the_participants_section_and_the_enrolment_form(site):
    app, _, _ = site
    fed = make(site)
    html = login(app, "researcher").get(f"{BASE}/{fed.id}").get_data(as_text=True)
    assert 'id="ws-enrol"' in html and 'name="members" value="forum"' in html and 'name="members" value="microblogging"' in html
    assert 'id="ws-participants"' not in html  # nobody yet
    assert "teacher" in html  # the users that can be enrolled


def test_enrol_then_list_then_remove(site, fake_gateways):
    app, _, _ = site
    fed = make(site)
    client = login(app, "researcher")
    uid = user_id("teacher")
    resp = client.post(f"{BASE}/{fed.id}/humans/enrol", data={"user_id": uid, "members": ["forum", "microblogging"]})
    assert resp.status_code == 302
    assert sorted(c[0] for c in fake_gateways) == ["forum", "microblogging"] and {c[2] for c in fake_gateways} == {f"human:{uid}"}
    html = client.get(f"{BASE}/{fed.id}").get_data(as_text=True)
    assert 'id="ws-participants"' in html and f"human:{uid}" in html and "Enrolled" in html
    client.post(f"{BASE}/{fed.id}/humans/{uid}/unenrol")
    html = client.get(f"{BASE}/{fed.id}").get_data(as_text=True)
    assert "Removed" in html and humans.accounts_by_member(fed) == {}


def test_an_error_is_shown_and_nothing_is_recorded(site, fake_gateways):
    app, _, _ = site
    fed = make(site)
    client = login(app, "researcher")
    resp = client.post(f"{BASE}/{fed.id}/humans/enrol", data={"user_id": user_id("teacher")}, follow_redirects=True)
    assert "Pick at least one platform." in resp.get_data(as_text=True)
    assert humans.list_humans(fed) == []


def test_only_the_owner_or_an_admin_can_enrol(site, fake_gateways):
    app, _, _ = site
    fed = make(site, owner="admin")
    assert login(app, "researcher").post(f"{BASE}/{fed.id}/humans/enrol", data={"user_id": user_id("teacher"), "members": ["forum"]}).status_code == 404
    assert login(app, "teacher").post(f"{BASE}/{fed.id}/humans/enrol", data={"user_id": user_id("teacher"), "members": ["forum"]}).status_code in (302, 403, 404)
    assert humans.list_humans(fed) == [] and fake_gateways == []
