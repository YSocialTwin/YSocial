"""YFederation is an optional plugin: without it classic simulations and the whole of YWeb keep working.

Audit (static): only the adapter modules of the servers import ``ysocial_federation`` at module level, and they are
loaded only when a ``federation`` section is enabled. Empirical: the SDK is made unimportable and the web application,
its classic pages, the servers' ``init_federation``/``build_gate`` and the World Simulation guards are exercised.
"""

import ast
import importlib.abc
import importlib.util
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from y_web.src.federation import availability
from y_web.tests.test_federation_service import (  # noqa: F401  (fixture of the site fixture)
    world,
)
from y_web.tests.test_world_simulation_ui import (  # noqa: F401  (fixtures and helper)
    login,
    site,
)

ROOT = Path(__file__).resolve().parents[2]
SDK = "ysocial_federation"
SERVER_FEDERATION_PACKAGES = {
    "YServer": ROOT / "external/YServer/y_server/federation",
    "YServerReddit": ROOT / "external/YServerReddit/y_server/federation",
    "YSimulator": ROOT / "external/YSimulator/YSimulator/YServer/federation",
    "YPhotoSharing": ROOT / "external/YPhotoSharing/YPhotoSharing/YServer/federation",
    "YInstantMessaging": ROOT
    / "external/YInstantMessaging/yinstantmessaging/federation",
    "YDating": ROOT / "external/YDating/YDating/YServer/federation",
}


class Blocker(importlib.abc.MetaPathFinder):
    """Makes ``ysocial_federation`` (and its submodules) fail to import, as on an installation without the plugin."""

    def find_spec(self, name, path=None, target=None):
        if name == SDK or name.startswith(SDK + "."):
            raise ModuleNotFoundError(f"No module named '{name}'", name=name)
        return None


@pytest.fixture
def sdk_blocked(monkeypatch):
    for name in [n for n in sys.modules if n == SDK or n.startswith(SDK + ".")]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setattr(sys, "meta_path", [Blocker(), *sys.meta_path])
    availability.reset_cache()
    yield
    availability.reset_cache()


# ------------------------------------------------------------------------------------------------ static audit
def python_files(*folders):
    for folder in folders:
        for path in Path(folder).rglob("*.py"):
            parts = set(path.parts)
            if parts & {
                "tests",
                "test",
                "node_modules",
                "__pycache__",
                ".git",
                "YFederation",
                "plugin-registry",
            }:
                continue
            yield path


def module_level_imports(path):
    """Names imported by the statements of the module body (not inside functions, classes or ``if``/``try`` blocks)."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return []
    out = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            out += [(a.name, 0) for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            out.append((node.module or "", node.level))
            out += [(f"{node.module or ''}.{a.name}", node.level) for a in node.names]
    return out


def test_only_adapter_modules_import_the_sdk_at_module_level():
    external = ROOT / "external"
    if not external.is_dir():
        pytest.skip("external/ is not checked out")
    offenders = []
    for path in python_files(
        ROOT / "y_web",
        *[p for p in external.iterdir() if p.is_dir() and p.name != "YFederation"],
    ):
        if (
            any(
                n == SDK or n.startswith(SDK + ".")
                for n, _ in module_level_imports(path)
            )
            and path.name != "adapter.py"
        ):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_nothing_outside_the_federation_packages_imports_an_adapter_at_module_level():
    external = ROOT / "external"
    if not external.is_dir():
        pytest.skip("external/ is not checked out")
    offenders = []
    for path in python_files(
        ROOT / "y_web",
        *[p for p in external.iterdir() if p.is_dir() and p.name != "YFederation"],
    ):
        if "federation" in path.parts or path.name == "adapter.py":
            continue
        for name, _level in module_level_imports(path):
            if (
                name.endswith("federation.adapter")
                or name.endswith("federation.gate")
                or name.endswith("federation.bindings")
            ):
                offenders.append(f"{path.relative_to(ROOT)}: {name}")
    assert offenders == []


def test_yweb_modules_that_use_the_sdk_import_it_inside_functions():
    users = [
        p
        for p in python_files(ROOT / "y_web")
        if SDK in p.read_text(encoding="utf-8", errors="ignore")
        and any(
            l.strip().startswith(
                ("from ysocial_federation", "import ysocial_federation")
            )
            for l in p.read_text(encoding="utf-8", errors="ignore").splitlines()
        )
    ]
    assert sorted(p.name for p in users) == [
        "dynamic.py",
        "humans.py",
        "pending_notice.py",
    ]
    for path in users:
        assert [
            n for n, _ in module_level_imports(path) if n.startswith(SDK)
        ] == [], path


# ---------------------------------------------------------------------------------------------------- guard
def test_blocked_sdk_is_reported_with_a_reason(sdk_blocked):
    assert availability.sdk_available() is False
    assert availability.sdk_reason().startswith(
        "The YFederation plugin is not installed"
    )
    assert "ModuleNotFoundError" in availability.sdk_reason()


def test_availability_answers_are_cached_and_reset(monkeypatch):
    calls = []
    monkeypatch.setattr(
        availability, "_probe", lambda: (calls.append(1), (True, ""))[1]
    )
    availability.reset_cache()
    assert (
        availability.sdk_available()
        and availability.sdk_available()
        and availability.sdk_available()
    )
    assert len(calls) == 1
    availability.sdk_available(refresh=True)
    assert len(calls) == 2
    availability.reset_cache()


def test_a_negative_answer_is_cached_for_a_short_time_only(monkeypatch):
    answers = [(False, "no"), (True, "")]
    monkeypatch.setattr(availability, "_probe", lambda: answers.pop(0))
    availability.reset_cache()
    assert not availability.sdk_available() and not availability.sdk_available()
    assert len(answers) == 1
    availability._cache["at"] -= (
        availability.NEGATIVE_TTL + 1
    )  # the plugin was installed meanwhile
    assert availability.sdk_available()
    availability.reset_cache()


def test_require_sdk_raises_a_world_simulation_error(sdk_blocked):
    from y_web.src.federation.service import WorldSimulationError

    with pytest.raises(WorldSimulationError) as caught:
        availability.require_sdk()
    assert caught.value.codes == ["sdk_missing"]


@pytest.mark.skipif(
    not (ROOT / "external/YFederation/ysocial_federation").is_dir(),
    reason="external/YFederation is not installed",
)
def test_child_check_sees_the_plugin_through_the_subprocess_environment(tmp_path):
    from y_web.src.simulation.subprocess_env import build_subprocess_env

    assert availability.child_import_check(env=build_subprocess_env()) == (True, "")
    bare = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(tmp_path),
    }  # nothing leads to the plugin
    ok, message = availability.child_import_check(env=bare)
    assert not ok and "No module named" in message and SDK in message


def test_child_check_failure_is_a_clear_error(monkeypatch):
    from y_web.src.federation.service import WorldSimulationError

    monkeypatch.setattr(
        availability,
        "child_import_check",
        lambda **k: (
            False,
            "ModuleNotFoundError: No module named 'ysocial_federation'",
        ),
    )
    with pytest.raises(WorldSimulationError) as caught:
        availability.require_child_sdk()
    assert caught.value.codes == ["sdk_not_importable"] and "No module named" in str(
        caught.value
    )


def test_child_check_times_out_quietly(monkeypatch):
    def slow(*a, **k):
        raise subprocess.TimeoutExpired("python", 1)

    monkeypatch.setattr(subprocess, "run", slow)
    ok, message = availability.child_import_check(timeout=1, env={})
    assert not ok and "took more than 1 s" in message


# ---------------------------------------------------------------------- servers: federation off is a no-op
def load_standalone(name, folder):
    """The ``federation/__init__.py`` of a server loaded alone (importing the server package would start the server)."""
    spec = importlib.util.spec_from_file_location(
        f"audit_{name}",
        folder / "__init__.py",
        submodule_search_locations=[str(folder)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        pass
    return module


@pytest.mark.parametrize("name", sorted(SERVER_FEDERATION_PACKAGES))
def test_servers_do_nothing_without_a_federation_section(name, sdk_blocked):
    folder = SERVER_FEDERATION_PACKAGES[name]
    if not folder.is_dir():
        pytest.skip(f"{name} is not checked out")
    module = load_standalone(name, folder)
    try:
        assert not any(n == SDK or n.startswith(SDK + ".") for n in sys.modules)
        entry = getattr(module, "init_federation", None)
        if entry is not None:  # YServer, YServerReddit
            assert (
                entry({}) is None
                and entry({"federation": {}}) is None
                and entry({"federation": {"enabled": False}}) is None
            )
        else:  # the other servers build the gate from their configuration
            assert module.build_gate(object(), {}) is None
            assert (
                module.build_gate(object(), {"federation": {"enabled": False}}) is None
            )
        assert not any(n == SDK or n.startswith(SDK + ".") for n in sys.modules)
    finally:
        sys.modules.pop(f"audit_{name}", None)


def test_an_enabled_federation_without_the_sdk_fails_loudly_at_the_server(sdk_blocked):
    folder = SERVER_FEDERATION_PACKAGES["YSimulator"]
    if not folder.is_dir():
        pytest.skip("YSimulator is not checked out")
    module = load_standalone("YSimulator_on", folder)
    try:
        with pytest.raises(ModuleNotFoundError, match=SDK):
            module.build_gate(
                object(), {"federation": {"enabled": True, "member": "x"}}
            )
    finally:
        sys.modules.pop("audit_YSimulator_on", None)


# ------------------------------------------------------------------- the whole web application, SDK missing
APP_SCRIPT = textwrap.dedent("""
    import json, sys, importlib.abc
    class Block(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path=None, target=None):
            if name == "ysocial_federation" or name.startswith("ysocial_federation."):
                raise ModuleNotFoundError("No module named '%s'" % name, name=name)
    sys.meta_path.insert(0, Block())
    out = {}
    from y_web import create_app, db
    app = create_app(db_type="sqlite")
    out["sdk_loaded_by_create_app"] = [m for m in sys.modules if m.startswith("ysocial_federation")]
    client = app.test_client()
    out["login_page"] = client.get("/login").status_code
    # the protected World Simulation and experiment pages send an anonymous visitor to the login page, never a 500
    out["world_simulation_anonymous"] = client.get("/admin/world_simulation").status_code
    out["experiments_anonymous"] = client.get("/admin/experiments").status_code
    with app.test_request_context("/"):
        g = app.jinja_env.globals
        out["badges"] = g["ws_profile_badges"](1, 1)
        out["destinations"] = g["ws_destinations"](1)
        out["pending"] = g["ws_pending"](1)
        out["menu_flag"] = g["ws_sdk_available"]()
        from flask import render_template_string
        out["badge_include"] = render_template_string("{% set ws_exp = 1 %}{% set ws_account = 1 %}{% include 'shared/world_simulation_profile_badges.html' %}").strip()
        out["badge_variants"] = [render_template_string("{% set ws_exp = 1 %}{% set ws_account = 1 %}{% set ws_variant = '" + v + "' %}{% include 'shared/world_simulation_profile_badges.html' %}").strip() for v in ("microblogging", "forum", "photo", "dating", "im")]
        out["classic_exp_info"] = g["world_simulation_of"](1)
    # classic start paths: the runtime modules import without the SDK and a classic experiment is not federated
    import y_web.src.simulation.execution_backend as eb, y_web.src.simulation.server, y_web.src.simulation.client
    from types import SimpleNamespace
    with app.app_context():
        eb._register_gate_probe(SimpleNamespace(idexp=424242), SimpleNamespace(id=1))
        out["classic_probe"] = "ok"
    out["sdk_loaded_at_end"] = [m for m in sys.modules if m.startswith("ysocial_federation")]
    print("RESULT " + json.dumps(out))
    """)


def test_the_web_application_and_its_classic_pages_work_without_the_sdk(tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH",)}
    env.update(PYTHONPATH=str(ROOT), YSOCIAL_HOME=str(tmp_path), PYTEST_CURRENT_TEST="")
    done = subprocess.run(
        [sys.executable, "-c", APP_SCRIPT],
        env=env,
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=240,
    )
    lines = [l for l in done.stdout.splitlines() if l.startswith("RESULT ")]
    assert lines, done.stdout[-1500:] + done.stderr[-3000:]
    out = json.loads(lines[-1][len("RESULT ") :])
    assert out["sdk_loaded_by_create_app"] == [] and out["sdk_loaded_at_end"] == []
    assert (
        out["login_page"] == 200
        and out["world_simulation_anonymous"] == 302
        and out["experiments_anonymous"] == 302
    )
    assert (
        out["badges"] == []
        and out["destinations"] == []
        and out["pending"] == []
        and out["menu_flag"] is False
    )
    assert (
        out["badge_include"] == ""
        and out["badge_variants"] == [""] * 5
        and out["classic_exp_info"] in (None, {}, False)
        and out["classic_probe"] == "ok"
    )


# ------------------------------------------------------------------------------------- guard in the pages
def test_the_menu_entry_follows_the_availability(world_site):
    app, tmp = world_site
    client = login(app, "admin")
    html = client.get("/admin/world_simulation").get_data(as_text=True)
    assert (
        "sidebar-group-world-simulation" in html
        and 'id="world-simulation-list"' in html
    )
    availability._cache.update(
        ok=False, reason="The YFederation plugin is not installed (test)", at=1e18
    )
    try:
        page = client.get("/admin/world_simulation")
        html = page.get_data(as_text=True)
        assert page.status_code == 503 and "sidebar-group-world-simulation" not in html
        assert (
            "The YFederation plugin is not installed" in html
            and "world-simulation-unavailable" in html
        )
        assert "(test)" in html  # the reason is shown for the admin
        json_page = client.get("/admin/world_simulation/1/status.json")
        assert (
            json_page.status_code == 503 and json_page.get_json()["available"] is False
        )
        assert (
            client.post("/admin/world_simulation/1/start").status_code == 503
        )  # commands too: no half-started runs
    finally:
        availability.reset_cache()


@pytest.fixture
def world_site(request):
    pytest.importorskip(SDK, reason="the federation SDK is not installed")
    site = request.getfixturevalue("site")
    app, exps, tmp = site
    app.jinja_env.globals["ws_sdk_available"] = availability.sdk_available
    return app, tmp


def test_start_checks_the_plugin_up_front_and_leaves_the_state_alone(
    world_site, sdk_blocked
):
    from y_web import db
    from y_web.src.federation import service
    from y_web.src.federation.service import WorldSimulationError
    from y_web.src.models import Exps
    from y_web.src.simulation import execution_backend as eb

    app, tmp = world_site
    exps = {e.platform_type: e.idexp for e in db.session.query(Exps).all()}
    fed = service.create_federation("w", list(exps.values()), owner="admin", seed=1)
    with pytest.raises(WorldSimulationError) as caught:
        eb.start_federation(fed)
    assert caught.value.codes == ["sdk_missing"]
    assert fed.status == "stopped" and not os.path.exists(
        os.path.join(fed.folder, "federation_coordinator.json")
    )


def test_start_checks_that_the_member_processes_can_import_the_plugin(
    world_site, monkeypatch
):
    from y_web import db
    from y_web.src.federation import service
    from y_web.src.federation.service import WorldSimulationError
    from y_web.src.models import Exps
    from y_web.src.simulation import execution_backend as eb

    app, tmp = world_site
    exps = {e.platform_type: e.idexp for e in db.session.query(Exps).all()}
    fed = service.create_federation("w", list(exps.values()), owner="admin", seed=1)
    monkeypatch.setattr(
        availability,
        "child_import_check",
        lambda **k: (
            False,
            "ModuleNotFoundError: No module named 'ysocial_federation'",
        ),
    )
    started = []
    monkeypatch.setattr(
        eb, "start_server_for_experiment", lambda exp: started.append(exp)
    )
    with pytest.raises(WorldSimulationError) as caught:
        eb.start_federation(fed)
    assert (
        caught.value.codes == ["sdk_not_importable"]
        and "No module named" in str(caught.value)
        and started == []
    )
    assert fed.status == "stopped"
    client = login(app, "admin")
    page = client.post(
        f"/admin/world_simulation/{fed.id}/start", follow_redirects=True
    ).get_data(as_text=True)
    assert "cannot import the YFederation plugin" in page and "No module named" in page


def test_the_italian_catalog_translates_the_new_texts():
    from babel.messages.pofile import read_po

    catalog = read_po(
        open(ROOT / "y_web/translations/it/LC_MESSAGES/messages.po", "rb"), locale="it"
    )
    for msgid in (
        "The YFederation plugin is not installed",
        "Waiting for %(who)s",
        "Stalled",
        "Not running",
        "Health",
        "The servers and clients of the members cannot import the YFederation plugin.",
        "Some members need attention",
        "Probable cause: Python module '%(name)s' not found",
        "~%(t)s per tick",
        "ETA %(eta)s",
    ):
        assert catalog.get(msgid) is not None and catalog.get(msgid).string, msgid
