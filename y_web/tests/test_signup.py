"""Self-registration: settings, offers, account creation and the admin/login wiring."""

import pathlib

import pytest

from y_web import db
from y_web.src import signup
from y_web.src.models import Admin_users, Exps, User_Experiment
from y_web.tests._platform_repos import microblogging_file

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _exp(name, status):
    exp = Exps(
        exp_name=name,
        platform_type="microblogging",
        db_name=f"{name}.db",
        owner="admin",
        exp_descr="",
        status=status,
        running=0,
        port=5000,
        server="127.0.0.1",
    )
    db.session.add(exp)
    db.session.commit()
    return exp


@pytest.fixture
def ctx(app, monkeypatch):
    monkeypatch.setattr(signup, "training_candidates", lambda: None)
    with app.app_context():
        yield


def test_disabled_by_default(ctx):
    assert not signup.is_enabled() and not signup.is_open()


def test_only_active_selected_experiments_are_offered(ctx):
    live, idle, other = _exp("live", 1), _exp("idle", 0), _exp("other", 1)
    signup.save(True, [live.idexp, idle.idexp], [])
    assert [o["ref"] for o in signup.offers()] == [str(live.idexp)]
    assert signup.is_open()
    signup.save(False, [live.idexp], [])
    assert not signup.is_open()
    flags = {e["name"]: e for e in signup.candidates()["experiments"]}
    assert (
        flags["live"]["selected"]
        and not flags["other"]["selected"]
        and not flags["idle"]["active"]
    )
    assert signup.candidates()["modules"] is None


def test_create_account_joins_picked_experiment(ctx):
    live = _exp("live", 1)
    signup.save(True, [live.idexp], [])
    result = signup.create_account(
        "alice", "Alice@Example.org", "longenough", [f"experiment:{live.idexp}"]
    )
    user = db.session.get(Admin_users, result["user_id"])
    assert user.role == "user" and user.email == "alice@example.org"
    assert user.password != "longenough"
    assert (
        db.session.query(User_Experiment)
        .filter_by(user_id=user.id, exp_id=live.idexp)
        .count()
        == 1
    )
    assert result["failed"] == [] and result["joined"] == ["live"]


@pytest.mark.parametrize(
    "args",
    [
        ("ab", "a@b.org", "longenough"),
        ("alice", "nope", "longenough"),
        ("alice", "a@b.org", "short"),
    ],
)
def test_validation(ctx, args):
    live = _exp("live", 1)
    signup.save(True, [live.idexp], [])
    with pytest.raises(signup.SignupError):
        signup.create_account(*args, [f"experiment:{live.idexp}"])


def test_pick_must_be_offered_and_account_unique(ctx):
    live, idle = _exp("live", 1), _exp("idle", 0)
    signup.save(True, [live.idexp, idle.idexp], [])
    with pytest.raises(signup.SignupError):
        signup.create_account(
            "alice", "a@b.org", "longenough", [f"experiment:{idle.idexp}"]
        )
    with pytest.raises(signup.SignupError):
        signup.create_account("alice", "a@b.org", "longenough", [])
    signup.create_account(
        "alice", "a@b.org", "longenough", [f"experiment:{live.idexp}"]
    )
    with pytest.raises(signup.SignupError):
        signup.create_account(
            "alice", "c@d.org", "longenough", [f"experiment:{live.idexp}"]
        )


def test_training_module_enrolment_and_availability(app, monkeypatch):
    mods = [
        {"uid": "m1", "title": "Open", "archived": False, "open_run": True},
        {"uid": "m2", "title": "Archived", "archived": True, "open_run": True},
        {"uid": "m3", "title": "No run", "archived": False, "open_run": False},
    ]
    monkeypatch.setattr(signup, "training_candidates", lambda: mods)
    calls = []

    class Api:
        @staticmethod
        def enroll(uid, account_id):
            calls.append((uid, account_id))
            return "unavailable" if uid == "m1" and len(calls) > 1 else "enrolled"

    import y_web.src.external_runtime.backend_plugins as bp

    monkeypatch.setattr(bp, "training_signup_api", lambda: Api, raising=False)
    with app.app_context():
        signup.save(True, [], ["m1", "m2", "m3"])
        assert [o["ref"] for o in signup.offers()] == ["m1"]
        r = signup.create_account(
            "bob", "b@b.org", "longenough", ["training:m1", "training:m2"]
        )
        assert r["joined"] == ["Open"] and calls == [("m1", r["user_id"])]


def test_wiring_in_templates_and_routes():
    login = (ROOT / "templates/login/login.html").read_text(encoding="utf-8")
    assert "signup_open() %}" in login and "auth.signup" in login
    register = (ROOT / "templates/login/register.html").read_text(encoding="utf-8")
    assert "signup_token" in register and 'name="pick"' in register
    assert "only.ref" in register  # direct link: the form posts back to it
    users_page = (ROOT / "templates/admin/users.html").read_text(encoding="utf-8")
    assert 'id="box-self-registration"' in users_page and "signup_enabled" in users_page
    assert (
        "{% if signup is not none %}" in users_page
        and 'id="signup-search"' in users_page
    )
    assert (
        users_page.count('role="switch"') == 2 and "slider-small" in users_page
    )  # toggles, not plain checkboxes
    assert (
        'class="sr-tag is-platform"' in users_page
        and 'class="sr-tag is-training"' in users_page
    )
    assert "box-self-registration" not in (
        ROOT / "templates/admin/miscellanea.html"
    ).read_text(encoding="utf-8")
    assert "/admin/signup_settings" in (
        ROOT / "static/assets/js/admin-users.js"
    ).read_text(encoding="utf-8")
    assert "box-self-registration" in (
        ROOT / "static/assets/js/users-tutorial.js"
    ).read_text(encoding="utf-8")
    users_route = (ROOT / "routes/admin/sub/users.py").read_text(encoding="utf-8")
    assert (
        'if user.role == "admin":' in users_route
        and "signup_candidates()" in users_route
    )
    routes = (ROOT / "routes/auth/routes.py").read_text(encoding="utf-8")
    assert "compare_digest" in routes and "is_open()" in routes


def test_italian_strings():
    import babel.messages.pofile as pofile

    cat = pofile.read_po(open(ROOT / "translations/it/LC_MESSAGES/messages.po", "rb"))
    for msgid in (
        "Self-registration",
        "Create an account",
        "Sign-up page",
        "Choose at least one of the available activities.",
    ):
        assert cat.get(msgid) and cat.get(msgid).string, msgid


def test_profile_topics_and_onboarding_flags_are_honoured():
    common = (ROOT / "routes/social/common.py").read_text(encoding="utf-8")
    assert '"onboarding_enabled", True' in common
    assert 'get("profile_topics_box", True)' in common
    tpl = pathlib.Path(
        microblogging_file("y_web/templates/microblogging/edit_profile.html")
    ).read_text(encoding="utf-8")
    assert "profile_topics_box|default(true) and topics and opinion_groups" in tpl


def test_direct_link_to_one_module(app, monkeypatch):
    from y_web.routes.auth import auth

    if "auth" not in app.blueprints:
        app.register_blueprint(auth)
    client = app.test_client()
    mods = [
        {"uid": "m1", "title": "Open", "archived": False, "open_run": True},
        {"uid": "m2", "title": "Other", "archived": False, "open_run": True},
        {"uid": "m3", "title": "Not allowed", "archived": False, "open_run": True},
    ]
    monkeypatch.setattr(signup, "training_candidates", lambda: mods)
    calls = []

    class Api:
        @staticmethod
        def enroll(uid, account_id):
            calls.append(uid)
            return "enrolled"

    import y_web.src.external_runtime.backend_plugins as bp

    monkeypatch.setattr(bp, "training_signup_api", lambda: Api, raising=False)
    with app.app_context():
        signup.save(True, [], ["m1", "m2"])
        assert signup.find_offer("training", "m1")["label"] == "Open"
        assert signup.find_offer("training", "m3") is None

    import y_web.routes.auth.routes as auth_routes

    seen = {}
    monkeypatch.setattr(
        auth_routes,
        "render_template",
        lambda name, **kw: seen.update(kw) or "page",
    )
    client.get("/signup?module=m1")
    assert [o["ref"] for o in seen["offers"]] == ["m1"] and seen["only"]["ref"] == "m1"
    client.get("/signup")
    assert [o["ref"] for o in seen["offers"]] == ["m1", "m2"] and seen["only"] is None

    # a module the admin did not allow bounces to the login page
    assert client.get("/signup?module=m3").status_code == 302

    client.get("/signup?module=m1")
    with client.session_transaction() as sess:
        token = sess["signup_token"]
    # tampering with the picks cannot add another activity: the link wins
    client.post(
        "/signup?module=m1",
        data={
            "signup_token": token,
            "name": "carol",
            "email": "c@c.org",
            "password": "longenough",
            "pick": ["training:m2"],
        },
    )
    assert calls == ["m1"]


def test_target_switch_and_live_requirement(app, monkeypatch):
    mods = [{"uid": "m1", "title": "T", "archived": False, "open_run": True, "live": False}]
    monkeypatch.setattr(signup, "training_candidates", lambda: mods)
    with app.app_context():
        signup.save(True, [], [])
        signup.set_target(signup.TRAINING, "m1", True)
        signup.set_target(signup.TRAINING, "m1", True)  # idempotent
        assert signup.is_target(signup.TRAINING, "m1") and signup.is_enabled()
        assert signup.offers() == []  # selected, but not published and running yet
        mods[0]["live"] = True
        assert [o["ref"] for o in signup.offers()] == ["m1"]
        signup.set_target(signup.TRAINING, "m1", False)
        assert not signup.is_target(signup.TRAINING, "m1") and signup.offers() == []
