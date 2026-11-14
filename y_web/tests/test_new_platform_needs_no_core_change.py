"""A platform nobody in the core has heard of is recognised from what its repository declares (gate G8).

The repository below is written to a temporary external folder and only declares a platform: no catalog lists it,
no core file names it. The test checks every place where the core used to carry a list of platforms.
"""

import json
import sys
from types import SimpleNamespace

import pytest

KEY = "zplat"
REPO = "ZPlatform"

PROVIDER = """
from y_web.sdk import HPC, N_, PlatformProvider


class ZPlat(PlatformProvider):
    key = "zplat"
    label = N_("Z platform")
    icon = "star"
    order = 900
    simulator_types = (HPC,)
    runtime_keys = ("zplatform",)
    tag_runtime_sets = (("zplatform",),)
    server_label = "ZPlatform"
    hpc_launch = {"runtime_repo": "ZPlatform", "supports_gunicorn": False}
"""


@pytest.fixture
def new_platform(tmp_path, monkeypatch):
    from y_web.platforms import discovery, registry
    from y_web.src.external_runtime import registry as runtime_registry

    external = tmp_path / "external"
    repo = external / REPO
    (repo / "meta").mkdir(parents=True)
    (repo / "ysocial_platform").mkdir()
    (repo / "ysocial_platform" / "__init__.py").write_text("")
    (repo / "ysocial_platform" / "provider.py").write_text(PROVIDER)
    (repo / "meta" / "registry.json").write_text(
        json.dumps(
            {
                "platform": {
                    "key": KEY,
                    "label": "Z platform",
                    "api_version": "1.0",
                    "provider": "ysocial_platform.provider:ZPlat",
                }
            }
        )
    )

    saved = (
        dict(registry._PROVIDERS),
        {k: list(v) for k, v in registry._EXTRA.items()},
        dict(discovery._DISCOVERED),
    )
    monkeypatch.setattr(runtime_registry, "EXTERNAL_DIR", external)
    # only this folder is searched: the repositories of the checkout are not touched
    monkeypatch.setattr(
        runtime_registry, "supported_repos", lambda: dict(runtime_registry._LOCAL_SPECS)
    )
    registry._PROVIDERS.clear()
    registry._EXTRA.clear()
    problems = discovery.discover_platforms()
    try:
        yield SimpleNamespace(problems=problems, repo=repo)
    finally:
        runtime_registry.remove_local_specs()
        registry._PROVIDERS.clear()
        registry._PROVIDERS.update(saved[0])
        registry._EXTRA.clear()
        registry._EXTRA.update(saved[1])
        discovery._DISCOVERED.clear()
        discovery._DISCOVERED.update(saved[2])
        for name in [n for n in sys.modules if "zplat" in n.lower()]:
            sys.modules.pop(name, None)


def test_it_is_found_and_registered_without_any_catalog(new_platform):
    from y_web.platforms import registry
    from y_web.src.external_runtime import registry as runtime_registry

    assert new_platform.problems == {"zplatform": []}
    provider = registry.get(KEY)
    assert provider is not None and provider.label == "Z platform"
    assert KEY in registry.keys()
    spec = runtime_registry._LOCAL_SPECS["zplatform"]
    assert (spec.group, spec.category, spec.trust, spec.source) == (
        KEY,
        "simulation_runtimes",
        "community",
        "local",
    )


def test_the_plugin_list_shows_it_with_the_platforms(new_platform):
    from y_web.platforms.discovery import provider_of_repo
    from y_web.routes.admin.sub.experiments import _external_runtimes as er
    from y_web.src.external_runtime import registry as runtime_registry

    spec = runtime_registry._LOCAL_SPECS["zplatform"]
    assert provider_of_repo(spec).key == KEY
    entry = {
        "key": "zplatform",
        "paired": False,
        "members": [{"key": "zplatform", "category": spec.category}],
    }
    sections = er._plugin_sections([entry])
    assert [(s["key"], [e["key"] for e in s["entries"]]) for s in sections] == [
        ("platforms", ["zplatform"])
    ]


def test_its_plugin_group_is_never_dropped_from_the_status_page(new_platform):
    from y_web.src.external_runtime import registry as runtime_registry

    # the groups of the built-in platforms are listed first; one the list does not know follows them
    keys = [g for g, _label, _specs in runtime_registry.grouped_runtime_specs()]
    assert keys == [KEY]  # supported_repos is narrowed to the folder searched here


class _Column:
    """Stands in for a model column: any comparison or ``|`` gives another column."""

    def __eq__(self, _other):
        return self

    def __or__(self, _other):
        return self


def test_running_experiments_block_the_removal_of_its_runtime(
    new_platform, monkeypatch
):
    from y_web.routes.admin.sub.experiments import _external_runtimes as er
    from y_web.src.external_runtime import registry as runtime_registry

    monkeypatch.setattr(
        er, "supported_repos", lambda: dict(runtime_registry._LOCAL_SPECS)
    )
    rows = [
        SimpleNamespace(platform_type=KEY, simulator_type="HPC"),
        SimpleNamespace(platform_type="other", simulator_type="Standard"),
    ]

    class _Query:
        def filter(self, *_conditions):
            return self

        def all(self):
            return rows

    fake = SimpleNamespace(
        query=_Query(), is_remote=_Column(), running=_Column(), exp_status=_Column()
    )
    monkeypatch.setattr(er, "Exps", fake)
    assert er._runtime_group_active_experiments(KEY) == [rows[0]]
    assert er._runtime_group_active_experiments("no_such_group") == []


def test_its_hpc_launch_row_comes_from_the_provider(new_platform):
    from y_web.src.hpc.platforms import find_hpc_platform, get_hpc_platform

    spec = get_hpc_platform(KEY)
    assert (spec.key, spec.runtime_repo, spec.supports_gunicorn) == (
        KEY,
        "ZPlatform",
        False,
    )
    assert find_hpc_platform(KEY) is spec


def test_it_is_a_population_type_and_an_agents_tag_and_has_a_label(
    new_platform, monkeypatch
):
    import importlib

    agents = importlib.import_module("y_web.routes.admin.sub.agents")
    from y_web.src.agents.platform import (
        VALID_POPULATION_TYPES,
        normalize_population_username_type,
    )
    from y_web.src.experiment.platform_labels import (
        group_experiments_by_platform,
        platform_label,
    )

    assert KEY in VALID_POPULATION_TYPES
    assert normalize_population_username_type("ZPlat") == KEY
    assert agents._platforms()[KEY][1] == (("zplatform",),)
    monkeypatch.setattr(agents, "_runtime_installed", lambda key: key == "zplatform")
    assert agents._installed_platforms() == [KEY]
    assert str(platform_label(KEY)) == "Z platform"
    groups = group_experiments_by_platform(
        [SimpleNamespace(platform_type=KEY, exp_name="e")]
    )
    assert [g["type"] for g in groups] == [KEY]


def test_the_public_registry_can_list_a_platform_too():
    from y_web.src.external_runtime.catalog import parse_registry

    specs, problems = parse_registry(
        {
            "schema_version": 1,
            "plugins": [
                {
                    "id": "zplat_runtime",
                    "name": "ZPlatform",
                    "repo": "someone/ZPlatformRepo",
                    "category": "simulation_runtimes",
                    "platform": KEY,
                    "platform_label": "Z platform",
                }
            ],
        }
    )
    assert problems == []
    spec = specs["zplat_runtime"]
    assert (spec.group, spec.group_label, spec.category) == (
        KEY,
        "Z platform",
        "simulation_runtimes",
    )
    _, problems = parse_registry(
        {
            "schema_version": 1,
            "plugins": [
                {
                    "id": "nameless",
                    "name": "X",
                    "repo": "someone/X",
                    "category": "simulation_runtimes",
                }
            ],
        }
    )
    assert problems and "platform" in problems[0]
