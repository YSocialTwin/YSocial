"""What the core needs to know to run a Standard runtime comes from the platform, with the usual names as defaults."""

from types import SimpleNamespace

import pytest

from y_web.platforms import registry
from y_web.platforms.base import StandardRuntime

pytestmark = pytest.mark.unit


def test_a_runtime_that_declares_nothing_gets_the_legacy_names_and_a_warning():
    with pytest.warns(DeprecationWarning):
        runtime = StandardRuntime(
            server_repo="S", client_repo="C", fake_agent_module="m"
        )
    assert runtime.server_script == "y_server_run.py"
    assert runtime.server_app_module == "y_server"
    assert runtime.client_class_path == "y_client.clients:YClientWeb"
    assert runtime.client_federation_module is None


def test_a_runtime_that_declares_everything_gets_no_warning(recwarn):
    runtime = StandardRuntime(
        server_repo="S",
        client_repo="C",
        fake_agent_module="m",
        server_script="run.py",
        server_app_module="srv",
        client_class_path="cli:Client",
        client_federation_module="cli.fed",
    )
    assert not [w for w in recwarn if w.category is DeprecationWarning]
    assert (runtime.server_script, runtime.server_app_module) == ("run.py", "srv")
    assert runtime.client_class_path == "cli:Client"
    assert runtime.client_federation_module == "cli.fed"


def test_the_installed_standard_platforms_declare_their_runtime(recwarn):
    from y_web.platforms import registry

    for provider in registry.providers():
        runtime = getattr(provider, "standard_runtime", None)
        if runtime is not None:
            assert runtime.server_script and runtime.server_app_module
            assert runtime.client_class_path
    assert not [
        w
        for w in recwarn
        if w.category is DeprecationWarning and "StandardRuntime" in str(w.message)
    ]


def test_server_config_file_follows_the_runtime_kind_and_the_platform(monkeypatch):
    standard = SimpleNamespace(platform_type="x", simulator_type="Standard")
    hpc = SimpleNamespace(platform_type="x", simulator_type="HPC")
    plain = SimpleNamespace(server_config_name=None)
    monkeypatch.setattr(registry, "resolve", lambda experiment: plain)
    assert registry.server_config_file(standard) == registry.STANDARD_SERVER_CONFIG
    assert registry.server_config_file(hpc) == registry.HPC_SERVER_CONFIG
    own = SimpleNamespace(server_config_name="my_server.json")
    monkeypatch.setattr(registry, "resolve", lambda experiment: own)
    assert registry.server_config_file(standard) == "my_server.json"
    assert registry.server_config_file(hpc) == "my_server.json"


def test_a_platform_names_its_own_entry_script(monkeypatch):
    from y_web.src.simulation import server

    runtime = StandardRuntime(
        server_repo="NewRepo",
        client_repo="NewClient",
        fake_agent_module="m",
        server_script="run_it.py",
        server_app_module="srv",
        client_class_path="cli:Client",
    )
    provider = SimpleNamespace(standard_runtime=runtime)
    monkeypatch.setattr(server.registry, "resolve", lambda *a, **k: provider)
    monkeypatch.setattr(
        server, "resolve_external_repo", lambda base, repo: f"/x/{repo}"
    )
    directory, script = server._resolve_server_runtime_paths("/base", "anything")
    assert directory == "/x/NewRepo" and script == "/x/NewRepo/run_it.py"


def test_the_federation_module_is_the_one_the_client_declares():
    from y_web.src.simulation import federation_hooks

    federation_hooks.use_federation_module(None)
    try:
        assert federation_hooks.federation_module() is None
        federation_hooks.use_federation_module("a_module_that_does_not_exist")
        assert federation_hooks.federation_module() is None
    finally:
        federation_hooks.use_federation_module(None)
