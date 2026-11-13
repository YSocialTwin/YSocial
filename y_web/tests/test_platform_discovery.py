"""Platforms declared by installed repositories are found, checked and registered; bad ones are skipped."""

import json
import types

import pytest

from y_web.platforms import discovery, registry
from y_web.platforms.discovery import (
    api_problem,
    discover_platforms,
    platform_restart_required,
    read_declaration,
)


def _repo(tmp_path, name="YDemo", key="demo", api="1.0", provider_key=None):
    repo = tmp_path / name
    package = repo / "ysocial_platform"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "provider.py").write_text(
        "from y_web.platforms.base import PlatformProvider\n"
        "class Demo(PlatformProvider):\n"
        f"    key = {provider_key or key!r}\n"
    )
    (repo / "meta").mkdir()
    (repo / "meta" / "registry.json").write_text(
        json.dumps(
            {
                "platform": {
                    "key": key,
                    "api_version": api,
                    "provider": "ysocial_platform.provider:Demo",
                }
            }
        )
    )
    return repo


@pytest.fixture
def world(tmp_path, monkeypatch):
    specs = {}
    # backend_plugins binds supported_repos when first imported: import it before the fake is in place
    from y_web.src.external_runtime import backend_plugins  # noqa: F401
    from y_web.src.external_runtime import registry as runtime_registry

    monkeypatch.setattr(runtime_registry, "supported_repos", lambda: specs)
    before = dict(registry._PROVIDERS)
    monkeypatch.setattr(discovery, "_DISCOVERED", {})
    yield specs
    registry._PROVIDERS.clear()
    registry._PROVIDERS.update(before)


def _install(specs, tmp_path, key="ydemo", **kwargs):
    specs[key] = types.SimpleNamespace(path=_repo(tmp_path, **kwargs))


def test_api_compatibility():
    assert api_problem("1.0") is None
    assert api_problem("1") is None
    assert api_problem("1.1") is not None  # newer than the core knows
    assert api_problem("2.0") is not None
    assert api_problem("x") is not None


def test_a_valid_repository_registers_its_platform(tmp_path, world):
    _install(world, tmp_path)
    assert discover_platforms() == {"ydemo": []}
    provider = registry.get("demo")
    assert provider.package_dir == world["ydemo"].path / "ysocial_platform"
    assert not platform_restart_required("ydemo")


def test_problems_are_reported_and_nothing_is_registered(tmp_path, world):
    _install(world, tmp_path / "a", key="ya", api="2.0")
    _install(world, tmp_path / "b", key="yb", provider_key="other")
    report = discover_platforms()
    assert "platform API" in report["ya"][0]
    assert "differs" in report["yb"][0]
    assert registry.get("other") is None
    assert registry.get("demo") is None


def test_a_repository_replaces_the_built_in_provider_of_its_key(tmp_path, world):
    _install(world, tmp_path, key="y1")
    builtin = registry.register(
        type("Mine", (registry.PlatformProvider,), {"key": "demo"})()
    )
    assert discover_platforms() == {"y1": []}
    assert registry.get("demo") is not builtin
    assert registry.get("demo").package_dir is not None


def test_two_repositories_for_one_key_are_refused(tmp_path, world):
    _install(world, tmp_path / "a", key="y1", name="Y1")
    _install(world, tmp_path / "b", key="y2", name="Y2")
    report = discover_platforms()
    assert report["y1"] == []
    assert "already provided" in report["y2"][0]


def test_repository_without_declaration_is_ignored(tmp_path, world):
    (tmp_path / "plain").mkdir()
    world["plain"] = types.SimpleNamespace(path=tmp_path / "plain")
    assert discover_platforms() == {}
    assert read_declaration(tmp_path / "plain") == (None, [])


def test_installed_after_startup_asks_for_a_restart(tmp_path, world):
    _install(world, tmp_path)
    assert platform_restart_required("ydemo")
    discover_platforms()
    assert not platform_restart_required("ydemo")


def _declare(repo, **extra):
    path = repo / "meta" / "registry.json"
    payload = json.loads(path.read_text())
    payload["platform"].update(extra)
    path.write_text(json.dumps(payload))


def test_translation_domain_is_registered_and_a_clash_is_reported(tmp_path, world):
    from y_web.src.external_runtime import plugin_i18n

    _install(world, tmp_path / "a", key="ya")
    _declare(world["ya"].path, i18n={"domain": "demo_pf"})
    assert discover_platforms() == {"ya": []}
    assert plugin_i18n.registered_domains()["demo_pf"]["repo_key"] == "ya"
    plugin_i18n.unregister_plugin_i18n("ya")


def test_schema_module_runs_after_discovery(tmp_path, world, monkeypatch):
    from flask import Flask

    from y_web import db  # noqa: F401
    from y_web.src.external_runtime import backend_plugins

    _install(world, tmp_path, key="yschema")
    (world["yschema"].path / "ysocial_platform" / "schema.py").write_text(
        "CALLS = []\ndef migrate(engine):\n    CALLS.append(engine)\n    return True\n"
    )
    _declare(world["yschema"].path, schema_module="ysocial_platform.schema:migrate")
    monkeypatch.setattr(backend_plugins, "_admin_engine", lambda db, app: "engine")
    assert discover_platforms() == {"yschema": []}
    report = discovery.run_platform_schema_migrations(Flask(__name__))
    assert report == {"yschema": {"ok": True, "error": None}}
