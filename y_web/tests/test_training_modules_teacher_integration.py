"""The teacher role in the real core: who can create one, where it lands, what it can never open, and the module
rehearsal inside a real experiment (the only way into an experiment)."""

import re
from html import unescape as html_unescape

from sqlalchemy import select

from y_web.src.external_runtime import backend_plugins
from y_web.tests.test_training_modules_baseline_auth import (  # noqa: F401
    _make_admin_user,
    core_app,
)
from y_web.tests.test_training_modules_phase3_integration import (
    API,
    _client_as,
    _post,
    requires_plugin,
)
from y_web.tests.test_training_modules_phase6_integration import (  # noqa: F401
    _experiment,
    _experiment_paths_under_tmp,
)
from y_web.tests.test_training_modules_phase10_integration import _count
from y_web.tests.test_training_modules_preview_integration import _preview_of

HOME = "/admin/training/modules"


def _published_module(admin, title="Class module"):
    uid = _post(admin, f"{API}/modules", {"title": title}).get_json()["module"][
        "module_uid"
    ]
    r = _post(
        admin,
        f"{API}/modules/{uid}/versions/1/steps",
        {
            "type": "scenario",
            "title": "Simulation",
            "revision": 1,
            "completion_policy": {"signal_mode": "declared", "criteria": []},
            "config": {
                "slot_key": "s1",
                "hint_name": "Sim",
                "platform_type": "microblogging",
                "simulator_type": "Standard",
            },
        },
    )
    assert r.status_code == 201, r.get_json()
    assert (
        _post(
            admin,
            f"{API}/modules/{uid}/versions/1/publish",
            {"revision": r.get_json()["revision"]},
        ).status_code
        == 200
    )
    return uid


def _shared_with_experiment(app, admin, exp):
    """A published, shared module whose scenario slot a researcher's run already binds to *exp*."""
    uid = _published_module(admin)
    rid = _post(
        admin,
        f"{API}/runs",
        {"module_uid": uid, "version_no": 1, "name": "researcher run"},
    ).get_json()["run"]["id"]
    key = admin.get(f"{API}/runs/{rid}/bindings").get_json()["bindings"][0]["step_key"]
    assert (
        _post(
            admin, f"{API}/runs/{rid}/bindings/{key}", {"exp_id": exp}, method="put"
        ).status_code
        == 200
    )
    assert (
        _post(admin, f"{API}/modules/{uid}/share", {"shared": True}).status_code == 200
    )
    return uid


def _teacher_login(app):
    with app.app_context():
        row = _make_admin_user("teacher")
        email = row.email
    client = app.test_client()
    res = client.post("/login", data={"email": email, "password": "Passw0rd!"})
    with client.session_transaction() as s:
        s["tm_csrf"] = "tok"  # the plugin's CSRF token, as the pages carry it
    return client, res


@requires_plugin
def test_only_an_administrator_creates_teachers(core_app):  # noqa: F811
    admin, researcher = _client_as(core_app, "admin"), _client_as(
        core_app, "researcher"
    )

    def made(client, name, role):
        client.post(
            "/admin/add_user",
            data={
                "username": name,
                "email": f"{name}@example.test",
                "password": "Passw0rd!",
                "role": role,
            },
        )
        return _count(
            core_app, "SELECT COUNT(*) FROM admin_users WHERE username = :u", u=name
        )

    assert made(admin, "tchr_by_admin", "teacher") == 1
    assert (
        _count(
            core_app, "SELECT role FROM admin_users WHERE username = 'tchr_by_admin'"
        )
        == "teacher"
    )
    assert made(researcher, "tchr_by_researcher", "teacher") == 0
    bulk = researcher.post(
        "/admin/add_users_bulk",
        data={"users_data": "tchr_bulk,tchr_bulk@example.test,teacher,Passw0rd!"},
    )
    assert (
        _count(
            core_app, "SELECT COUNT(*) FROM admin_users WHERE username = 'tchr_bulk'"
        )
        == 0
    ), bulk.status_code
    # a teacher cannot create anything, whatever the role
    with core_app.app_context():
        row = _make_admin_user("teacher")
        uid = row.get_id()
    teacher = core_app.test_client()
    with teacher.session_transaction() as s:
        s["_user_id"], s["_fresh"] = uid, True
    teacher.post(
        "/admin/add_user",
        data={
            "username": "tchr_by_teacher",
            "email": "tt@example.test",
            "password": "Passw0rd!",
            "role": "teacher",
        },
    )
    assert (
        _count(
            core_app,
            "SELECT COUNT(*) FROM admin_users WHERE username = 'tchr_by_teacher'",
        )
        == 0
    )


@requires_plugin
def test_a_teacher_logs_in_to_the_training_area(core_app):  # noqa: F811
    teacher, res = _teacher_login(core_app)
    assert res.status_code == 302 and res.headers["Location"].endswith(HOME)
    page = teacher.get(HOME)
    html = re.sub(
        r"<!--.*?-->", "", page.get_data(as_text=True), flags=re.S
    )  # what the browser shows
    assert page.status_code == 200 and 'id="sidebar-group-training_modules"' in html
    for entry in (
        "/admin/training/modules",
        "/admin/training/runs",
        "/admin/training/activity",
        "/admin/training/analysis",
        "/admin/training/guide",
    ):
        assert f'href="{entry}"' in html, entry
    for closed in (
        "/admin/training/library",
        "/admin/training/components",
        "/admin/training/settings",
        "/admin/experiments",
        "/admin/dashboard",
        "/admin/users",
        "/admin/populations",
        "/admin/miscellanea",
        "/admin/about",
    ):
        assert f'href="{closed}"' not in html, closed
    with core_app.test_request_context("/"):
        items = [
            i["label"]
            for g in backend_plugins.backend_suite_sidebar_groups("teacher")
            for i in g["items"]
        ]
    assert items == ["Modules", "Runs", "Analysis", "Data & exports", "Guide"]


@requires_plugin
def test_a_teacher_opens_no_page_of_the_core_administration(core_app):  # noqa: F811
    """Crawl every route of the application with a teacher session: none but the Training area answers."""
    teacher, _ = _teacher_login(core_app)
    allowed = (
        "/admin/training",
        "/training",
        "/static/",
        "/plugins/",
        "/uploads/",
        "/login",
        "/logout",
    )
    reached = []
    for rule in core_app.url_map.iter_rules():
        path = re.sub(r"<[^>]+>", "1", rule.rule)
        if path.startswith(allowed):
            continue
        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            res = (
                getattr(teacher, method.lower())(path, headers={"Accept": "text/html"})
                if method == "GET"
                else getattr(teacher, method.lower())(
                    path, json={}, headers={"X-CSRF-Token": "tok"}
                )
            )
            if res.status_code == 200 or (
                res.status_code == 302 and not res.headers["Location"].endswith(HOME)
            ):
                reached.append(
                    (method, rule.rule, res.status_code, res.headers.get("Location"))
                )
    assert reached == []
    # the answer a browser gets is a way back, a script gets a refusal
    assert (
        teacher.get("/admin/dashboard", headers={"Accept": "text/html"})
        .headers["Location"]
        .endswith(HOME)
    )
    assert (
        teacher.get(
            "/admin/experiments", headers={"Accept": "application/json"}
        ).status_code
        == 403
    )
    assert teacher.post("/admin/add_user", data={"username": "x"}).status_code == 403


@requires_plugin
def test_the_gate_leaves_everyone_else_alone(core_app):  # noqa: F811
    for role in ("admin", "researcher"):
        client = _client_as(core_app, role)
        assert client.get("/admin/dashboard").status_code == 200
        assert client.get(HOME).status_code == 200
    assert "teacher" not in backend_plugins.__dict__.get("DEFAULT_GROUP_ITEM_ROLES", ())


@requires_plugin
def test_a_teacher_rehearses_in_a_real_experiment_and_nowhere_else(
    core_app,
):  # noqa: F811
    app, admin = core_app, _client_as(core_app, "admin")
    exp, other = _experiment(app, "microblogging", "Standard"), _experiment(
        app, "microblogging", "Standard"
    )
    uid = _shared_with_experiment(app, admin, exp)
    teacher, _ = _teacher_login(app)

    assert uid in [
        m["module_uid"] for m in teacher.get(f"{API}/modules").get_json()["modules"]
    ]
    # before any rehearsal the experiment is closed to the teacher, in every form
    for url in (
        f"/admin/join_experiment/{exp}",
        f"/{exp}/feed/1/feed/rf/1",
        f"/admin/select_experiment/{exp}",
        "/feed",
    ):
        res = teacher.get(url, headers={"Accept": "text/html"})
        assert res.status_code in (302, 403) and (
            res.status_code == 403 or res.headers["Location"].endswith(HOME)
        ), url

    panel = teacher.get(f"/admin/training/preview/{uid}/1")
    assert panel.status_code == 200 and b"tm-preview-start" in panel.data
    rid, key = _preview_of(app, uid)
    assert (
        _count(app, "SELECT exp_id FROM tm_run_binding WHERE run_id = :r", r=rid) == exp
    )  # inherited, not chosen
    assert (
        _post(
            teacher,
            f"{API}/preview/{rid}/bindings/{key}",
            {"exp_id": other},
            method="put",
        ).status_code
        == 403
    )

    start = teacher.post(
        f"/training/runs/{rid}/steps/{key}/start", data={"csrf_token": "tok"}
    )
    assert start.status_code == 303 and start.headers["Location"].endswith(
        f"/admin/join_experiment/{exp}"
    )
    joined = teacher.get(start.headers["Location"])
    assert joined.status_code == 302 and f"/{exp}/feed/" in joined.headers["Location"]
    assert teacher.get(joined.headers["Location"]).status_code != 403

    # the rehearsal opens that experiment only
    res = teacher.get(
        f"/admin/join_experiment/{other}", headers={"Accept": "text/html"}
    )
    assert res.status_code == 302 and res.headers["Location"].endswith(HOME)
    assert (
        teacher.get(f"/{other}/feed/1/feed/rf/1", headers={"Accept": "text/html"})
        .headers["Location"]
        .endswith(HOME)
    )
    assert (
        teacher.get("/admin/dashboard", headers={"Accept": "text/html"})
        .headers["Location"]
        .endswith(HOME)
    )

    # leaving it closes the experiment again
    assert teacher.get(f"/training/runs/{rid}/preview/exit").status_code == 303
    res = teacher.get(f"/admin/join_experiment/{exp}", headers={"Accept": "text/html"})
    assert res.status_code == 302 and res.headers["Location"].endswith(HOME)
    assert (
        _count(app, "SELECT COUNT(*) FROM tm_preview_trace WHERE run_id = :r", r=rid)
        == 0
    )


@requires_plugin
def test_a_teachers_run_takes_students_without_any_core_right(core_app):  # noqa: F811
    app, admin = core_app, _client_as(core_app, "admin")
    exp = _experiment(app, "microblogging", "Standard")
    uid = _shared_with_experiment(app, admin, exp)
    teacher, _ = _teacher_login(app)
    made = _post(
        teacher, f"{API}/runs", {"module_uid": uid, "version_no": 1, "name": "3B"}
    )
    assert made.status_code == 201 and [
        i["bound"] for i in made.get_json()["inherited"]
    ] == [True]
    rid = made.get_json()["run"]["id"]
    from y_web.tests.test_training_modules_phase6_integration import _participant

    student, username, _email = _participant(app, exp)
    res = _post(
        teacher,
        f"{API}/runs/{rid}/enrollments/import",
        {"csv": username, "group_label": "3B"},
    )
    assert res.status_code in (200, 201), res.get_json()
    assert _post(teacher, f"{API}/runs/{rid}/activate").status_code == 200
    assert teacher.get(f"{API}/runs/{rid}/progress").status_code == 200
    assert teacher.get(f"{API}/runs/{rid}/analytics/overview").status_code == 200
    assert _post(teacher, f"{API}/runs/{rid}/close").status_code == 200
    # what the teacher cannot do, the core still refuses to them
    assert _post(teacher, f"{API}/runs/{rid}/experiments/activate").status_code == 403
    assert (
        teacher.get(
            f"/admin/experiment_details/{exp}", headers={"Accept": "text/html"}
        ).status_code
        != 200
    )


@requires_plugin
def test_the_sidebar_lists_the_training_entries_under_their_sections(
    core_app,
):  # noqa: F811
    admin = _client_as(core_app, "admin")
    html = re.sub(
        r"<!--.*?-->",
        "",
        admin.get("/admin/dashboard").get_data(as_text=True),
        flags=re.S,
    )
    block = html[html.index('id="sidebar-submenu-training_modules"') :]
    block = block[: block.index("</div>\n        </div>")]
    assert re.findall(r'dashboard-aside-submenu-section">([^<]+)<', block) == [
        "Design",
        "Run",
        "Results",
        "Setup",
        "Help",
    ]
    assert [html_unescape(t) for t in re.findall(r"<span>([^<]+)</span>", block)] == [
        "Modules",
        "Activity library",
        "Activities Templates",
        "Runs",
        "Analysis",
        "Data & exports",
        "Settings",
        "Guide",
    ]
