"""Several repositories providing one platform (plan, phase F9.1): variants chosen per experiment."""

import json
import types

import pytest

from y_web.platforms import PlatformProvider, discovery, registry
from y_web.platforms.base import HPC, STANDARD


def _provider(key="vdemo", id="", simulator_types=None, **extra):
    attrs = {"key": key, "id": id, "simulator_types": simulator_types, **extra}
    return type("P_" + (id or key), (PlatformProvider,), attrs)()


@pytest.fixture
def clean_registry():
    before, extra = dict(registry._PROVIDERS), dict(registry._EXTRA)
    yield registry
    registry._PROVIDERS.clear()
    registry._PROVIDERS.update(before)
    registry._EXTRA.clear()
    registry._EXTRA.update(extra)


def test_a_provider_without_id_is_identified_by_its_key_and_serves_every_runtime():
    p = _provider()
    assert p.provider_id == "vdemo"
    assert p.serves(STANDARD) and p.serves(HPC) and p.serves(None)


def test_two_repositories_serving_distinct_runtimes_are_variants(clean_registry):
    hpc = registry.register(_provider(id="vhpc", simulator_types=(HPC,)))
    std = registry.register(_provider(id="vstd", simulator_types=(STANDARD,)))
    assert registry.variants("vdemo") == [std, hpc]  # Standard is the preferred one
    assert registry.get("vdemo") is std  # the preferred variant answers get()
    assert registry.by_id("vstd") is std and registry.by_id("vhpc") is hpc
    assert registry.for_simulator("vdemo", STANDARD) is std
    assert registry.for_simulator("vdemo", HPC) is hpc
    assert registry.for_simulator("vdemo", "Other") is None


def test_for_experiment_reads_platform_and_simulator_type(clean_registry):
    hpc = registry.register(_provider(id="vhpc", simulator_types=(HPC,)))
    std = registry.register(_provider(id="vstd", simulator_types=(STANDARD,)))
    exp = types.SimpleNamespace(platform_type="vdemo", simulator_type="Standard")
    assert registry.for_experiment(exp) is std
    exp.simulator_type = "HPC"
    assert registry.for_experiment(exp) is hpc
    assert (
        registry.for_experiment(types.SimpleNamespace(platform_type="nobody")) is None
    )


def test_a_single_provider_answers_for_every_runtime(clean_registry):
    only = registry.register(_provider(id="", simulator_types=None))
    assert registry.for_simulator("vdemo", STANDARD) is only
    assert registry.for_simulator("vdemo", HPC) is only
    assert registry.variants("vdemo") == [only]


@pytest.mark.parametrize(
    "first, second",
    [
        (dict(id="a"), dict(id="b")),  # nobody says what runtime they serve
        (dict(id="a", simulator_types=(HPC,)), dict(id="b")),
        (
            dict(id="a", simulator_types=(HPC,)),
            dict(id="a", simulator_types=(STANDARD,)),
        ),
        (
            dict(id="a", simulator_types=(HPC, STANDARD)),
            dict(id="b", simulator_types=(STANDARD,)),
        ),  # overlap
    ],
)
def test_providers_that_could_answer_for_the_same_experiment_are_refused(
    clean_registry, first, second
):
    registry.register(_provider(**first))
    with pytest.raises(ValueError, match="already provided"):
        registry.register(_provider(**second))
    assert len(registry.variants("vdemo")) == 1


def test_menus_list_each_platform_once_and_all_providers_list_the_variants(
    clean_registry,
):
    registry.register(_provider(id="vhpc", simulator_types=(HPC,)))
    registry.register(_provider(id="vstd", simulator_types=(STANDARD,)))
    assert [p.provider_id for p in registry.providers() if p.key == "vdemo"] == ["vstd"]
    assert {p.provider_id for p in registry.all_providers() if p.key == "vdemo"} == {
        "vhpc",
        "vstd",
    }
    assert registry.keys().count("vdemo") == 1


def _repo(tmp_path, repo_id, runtime):
    repo = tmp_path / repo_id
    package = repo / "ysocial_platform"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "provider.py").write_text(
        "from y_web.platforms.base import PlatformProvider\n"
        "class Demo(PlatformProvider):\n"
        "    key = 'vdemo'\n"
        f"    simulator_types = ({runtime!r},)\n"
    )
    (repo / "meta").mkdir()
    (repo / "meta" / "registry.json").write_text(
        json.dumps(
            {
                "platform": {
                    "key": "vdemo",
                    "id": repo_id,
                    "api_version": "1.0",
                    "provider": "ysocial_platform.provider:Demo",
                }
            }
        )
    )
    return repo


def test_discovery_registers_two_repositories_of_one_key_under_their_ids(
    tmp_path, clean_registry, monkeypatch
):
    from y_web.src.external_runtime import backend_plugins  # noqa: F401
    from y_web.src.external_runtime import registry as runtime_registry

    specs = {
        "ysocial_hpc": types.SimpleNamespace(path=_repo(tmp_path, "ysocial_hpc", HPC)),
        "ysocial_std": types.SimpleNamespace(
            path=_repo(tmp_path, "ysocial_std", STANDARD)
        ),
    }
    monkeypatch.setattr(runtime_registry, "supported_repos", lambda: specs)
    monkeypatch.setattr(discovery, "_DISCOVERED", {})
    assert discovery.discover_platforms() == {"ysocial_hpc": [], "ysocial_std": []}
    assert {p.provider_id for p in registry.variants("vdemo")} == {
        "ysocial_hpc",
        "ysocial_std",
    }
    assert registry.for_simulator("vdemo", STANDARD).provider_id == "ysocial_std"
    assert all(not discovery.platform_restart_required(r) for r in specs)


def test_a_wrong_id_is_reported(tmp_path):
    repo = _repo(tmp_path, "x", HPC)
    path = repo / "meta" / "registry.json"
    payload = json.loads(path.read_text())
    payload["platform"]["id"] = 3
    path.write_text(json.dumps(payload))
    declaration, problems = discovery.read_declaration(repo)
    assert declaration is None and any("platform.id" in p for p in problems)


# --- namespaces of the templates and static files: the id of the repository ----------------------------------------


def _with_package(tmp_path, name, **attrs):
    from flask import Flask  # noqa: F401

    package = tmp_path / name / "ysocial_platform"
    (package / "templates" / "slots").mkdir(parents=True)
    (package / "static").mkdir()
    (package / "templates" / "hello.html").write_text(f"{name} says hi")
    (package / "templates" / "slots" / "top.html").write_text(name)
    (package / "static" / "app.js").write_text(f"/* {name} */")
    provider = _provider(**attrs)
    provider.package_dir = package
    return provider


def _namespaced_app(tmp_path):
    from flask import Flask

    from y_web.platforms.extension import install_platform_extensions

    app = Flask(__name__, template_folder=str(tmp_path))
    install_platform_extensions(app)
    return app


@pytest.fixture
def only_these(clean_registry):
    """The platforms of repositories found by an application started earlier are not part of these tests."""
    for key, provider in list(registry._PROVIDERS.items()):
        if provider.package_dir is not None:
            del registry._PROVIDERS[key]
    yield


def test_a_single_repository_answers_to_its_id_and_to_its_key(tmp_path, only_these):
    from flask import render_template

    registry.register(_with_package(tmp_path, "solo", key="vsolo", id="ysolo"))
    app = _namespaced_app(tmp_path)
    client = app.test_client()
    with app.test_request_context():
        assert render_template("@ysolo/hello.html") == "solo says hi"
        assert render_template("@vsolo/hello.html") == "solo says hi"
    assert client.get("/platform-static/ysolo/app.js").status_code == 200
    assert client.get("/platform-static/vsolo/app.js").status_code == 200


def test_with_several_repositories_for_a_key_only_the_ids_are_namespaces(
    tmp_path, only_these
):
    from flask import render_template
    from jinja2 import TemplateNotFound

    from y_web.platforms.extension import platform_slots

    registry.register(
        _with_package(tmp_path, "hpc", key="vmulti", id="yhpc", simulator_types=(HPC,))
    )
    registry.register(
        _with_package(
            tmp_path, "std", key="vmulti", id="ystd", simulator_types=(STANDARD,)
        )
    )
    app = _namespaced_app(tmp_path)
    client = app.test_client()
    with app.test_request_context():
        assert render_template("@yhpc/hello.html") == "hpc says hi"
        assert render_template("@ystd/hello.html") == "std says hi"
        with pytest.raises(TemplateNotFound):
            render_template("@vmulti/hello.html")  # which repository would that be?
        assert platform_slots("top") == ["@yhpc/slots/top.html", "@ystd/slots/top.html"]
    assert client.get("/platform-static/yhpc/app.js").data == b"/* hpc */"
    assert client.get("/platform-static/ystd/app.js").data == b"/* std */"
    assert client.get("/platform-static/vmulti/app.js").status_code == 404


def test_asset_v_finds_the_static_file_of_a_repository_by_id_or_key(
    tmp_path, only_these
):
    from flask import Flask

    from y_web.src.system.template_context import register_template_context

    registry.register(_with_package(tmp_path, "av", key="vav", id="yav"))
    app = Flask(__name__)
    register_template_context(app)
    asset_v = app.jinja_env.globals["asset_v"]
    assert asset_v("@yav/app.js") > 0 and asset_v("@vav/app.js") > 0
    assert asset_v("@nobody/app.js") == 0 and asset_v("@yav/missing.js") == 0
