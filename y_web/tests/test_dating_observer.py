"""Dating observer: viewpoints, time travel, access guards and the IR-D-16 sentinel test (plan 6)."""

import json
import re
import uuid

import pytest

from y_web.tests.dating_fixture import SENTINELS, build_dating_db
from y_web.tests.test_im_admin_pages import im_app  # noqa: F401


@pytest.fixture
def observer(im_app, tmp_path, request):  # noqa: F811
    from y_web import db
    from y_web.src.models import Exps

    app, client = im_app
    sentinel = getattr(request, "param", True)
    with app.app_context():
        exp = Exps(
            exp_name="dating observer",
            platform_type="dating",
            simulator_type="HPC",
            db_name=f"experiments/{uuid.uuid4().hex}/database_server.db",
            owner="adm",
            exp_descr="d",
            status=1,
            port=5098,
            server="127.0.0.1",
            prompt_language="en",
        )
        db.session.add(exp)
        db.session.commit()
        exp_id = exp.idexp
        folder = tmp_path / "y_web" / "experiments" / exp.db_name.split("/")[1]
        folder.mkdir(parents=True)
        info = build_dating_db(str(folder / "database_server.db"), sentinel=sentinel)
    return app, client, exp_id, info


def _set(app, exp_id, **settings):
    from y_web import db
    from y_web.src.models import ExpFrontendSettings

    with app.app_context():
        row = db.session.get(ExpFrontendSettings, exp_id)
        if row is None:
            row = ExpFrontendSettings(exp_id=exp_id, settings_json="{}")
            db.session.add(row)
        data = json.loads(row.settings_json or "{}")
        data.update(settings)
        row.settings_json = json.dumps(data)
        db.session.commit()


def _urls(exp_id, info, vp, acc=None):
    base = f"/{exp_id}/dating"
    q = f"vp={vp}" + (f"&acc={acc}" if acc else "")
    u0, u1 = info["users"][0], info["users"][1]
    urls = [
        f"{base}?{q}",
        f"{base}/profile/{u1}?{q}",
        f"{base}/search?{q}&q=user",
        f"{base}/api/status?{q}",
    ]
    if vp != "public":
        urls += [f"{base}/matches?{q}", f"{base}/chat/{info['match']}?{q}"]
    if vp == "account":
        urls.append(f"{base}/notifications?{q}")
    if vp == "overview":
        urls += [f"{base}/api/history?{q}", f"{base}?{q}&acc={u0}"]
    return urls


def test_overview_shows_the_reserved_fields(observer):
    app, client, exp_id, info = observer
    html = "".join(client.get(u).data.decode() for u in _urls(exp_id, info, "overview"))
    for expected in (
        "SENTINEL_REASON",
        "SENTINEL_MODEL",
        "SENTINEL_DELETED_TEXT",
        "0.424242",
        "Researcher overview",
    ):
        assert expected in html, expected


def test_sentinel_values_never_reach_public_or_account_views(observer):
    """IR-D-16: reserved fields hold markers; none may appear in the HTML/JSON of the other viewpoints."""
    app, client, exp_id, info = observer
    u0 = info["users"][0]
    seen = 0
    for vp, acc in (("public", None), ("account", u0), ("account", info["users"][1])):
        for url in _urls(exp_id, info, vp, acc):
            r = client.get(url)
            assert r.status_code == 200, (url, r.status_code)
            text = r.data.decode()
            seen += 1
            for marker in SENTINELS["text"] + SENTINELS["numbers"]:
                assert marker not in text, (url, marker)
    assert seen > 10


def test_account_view_is_what_the_account_could_see(observer):
    app, client, exp_id, info = observer
    u = info["users"]
    home = client.get(f"/{exp_id}/dating?vp=account&acc={u[0]}").data.decode()
    assert "user_01" in home and "user_03" in home  # its deck
    assert "dt-stamp-like" in home and "dt-stamp-pass" in home  # its own decisions
    chat = client.get(
        f"/{exp_id}/dating/chat/{info['match']}?vp=account&acc={u[0]}"
    ).data.decode()
    assert "hello there" in chat and "Message removed" in chat
    other = client.get(f"/{exp_id}/dating/chat/{info['match']}?vp=account&acc={u[3]}")
    assert other.status_code == 404  # a chat the account is not part of


def test_public_view_has_no_swipes_matches_or_chats(observer):
    app, client, exp_id, info = observer
    for path in ("/matches", f"/chat/{info['match']}", "/notifications"):
        assert client.get(f"/{exp_id}/dating{path}?vp=public").status_code == 404
    html = client.get(f"/{exp_id}/dating?vp=public").data.decode()
    assert "dt-stamp" not in html and "hello there" not in html


def test_time_travel_rebuilds_the_profile_and_hides_the_future(observer):
    app, client, exp_id, info = observer
    u1 = info["users"][1]
    early = client.get(f"/{exp_id}/dating/profile/{u1}?vp=public&round=5").data.decode()
    late = client.get(f"/{exp_id}/dating/profile/{u1}?vp=public&round=8").data.decode()
    assert "bio of 1" in early and "new bio of 1" not in early
    assert "new bio of 1" in late
    # the match is created at round 4: before that there is none
    before = client.get(f"/{exp_id}/dating/matches?vp=overview&round=3").data.decode()
    assert "No matches" in before
    # a user who left at round 9 is gone afterwards, present before
    gone = info["users"][-1]
    assert (
        client.get(f"/{exp_id}/dating/profile/{gone}?vp=public&round=8").status_code
        == 200
    )
    assert (
        client.get(f"/{exp_id}/dating/profile/{gone}?vp=public&round=10").status_code
        == 404
    )
    assert (
        "Time travel" in client.get(f"/{exp_id}/dating?vp=public&round=2").data.decode()
    )


def test_non_staff_see_only_the_public_view_and_switches_apply(observer, monkeypatch):
    app, client, exp_id, info = observer
    monkeypatch.setattr("y_web.routes.social.dating._staff_user", lambda: None)
    assert client.get(f"/{exp_id}/dating").status_code == 200  # defaults to public
    assert client.get(f"/{exp_id}/dating?vp=overview").status_code == 403
    assert (
        client.get(f"/{exp_id}/dating?vp=account&acc={info['users'][0]}").status_code
        == 403
    )
    _set(app, exp_id, dating_allow_time_travel=False)
    html = client.get(f"/{exp_id}/dating?round=2").data.decode()
    assert "Time travel" not in html  # the request for a past round is ignored
    _set(app, exp_id, dating_public_observer_enabled=False)
    assert client.get(f"/{exp_id}/dating").status_code == 403


def test_wrong_platform_and_missing_database(im_app):  # noqa: F811
    app, client = im_app
    assert client.get("/999999/dating").status_code == 404


@pytest.mark.parametrize("observer", [False], indirect=True)
def test_page_chrome_is_accessible_and_marks_the_simulation(observer):
    app, client, exp_id, info = observer
    html = client.get(f"/{exp_id}/dating?vp=public").data.decode()
    assert "dt-skip" in html and 'id="dt-main"' in html
    assert "fictional" in html  # permanent simulation banner
    assert re.search(r'<html lang="[a-z]{2}', html)
    assert 'aria-label="Sections"' in html or "Sections" in html


def test_dating_frontend_settings_are_declared():
    from y_web.routes.admin.sub.experiments import _frontend_settings as fs
    from y_web.src.experiment.frontend_defaults import DEFAULT_SETTINGS

    keys = {
        "dating_allow_time_travel",
        "dating_public_observer_enabled",
        "dating_poll_seconds",
    }
    assert "dating" in fs.SUPPORTED_PLATFORMS
    assert keys <= set(fs.capabilities_for("dating"))
    assert keys <= set(DEFAULT_SETTINGS)
    assert fs._INT_RANGES["dating_poll_seconds"] == (1, 60)
