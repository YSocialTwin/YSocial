"""YDating is registered like the other simulation runtimes (IR-D-01, IR-D-02, IR-D-03)."""

from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit


def test_dating_spec_is_a_private_official_runtime():
    from y_web.src.external_runtime import registry

    spec = registry.runtime_spec("dating")
    assert spec.github_repo == "YSocialTwin/YDating"
    assert spec.path.name == "YDating"
    assert spec.category == "simulation_runtimes"
    assert spec.group == "dating"
    assert spec.is_private is True
    assert spec.validate_import == "YDating"
    assert tuple(spec.validate_entrypoints) == (
        "run_server.py",
        "run_client.py",
        "requirements.txt",
    )


def test_dating_group_is_listed_after_instant_messaging():
    from y_web.src.external_runtime import registry

    keys = [g[0] for g in registry.grouped_runtime_specs()]
    assert keys.index("dating") == keys.index("instant_messaging") + 1


def test_dating_description_is_translatable():
    from y_web.src.external_runtime import registry

    spec = registry.runtime_spec("dating")
    assert spec.description in registry.RUNTIME_TEXTS


def test_dating_is_one_row_of_the_hpc_platform_table():
    from y_web.src.hpc.platforms import find_hpc_platform, get_hpc_platform

    spec = get_hpc_platform("dating")
    assert spec.runtime_repo == "YDating"
    assert spec.server_repo == "YDating"
    assert spec.orchestrator_actor == "Orchestrator"
    assert find_hpc_platform("nope") is None


def test_the_other_platform_rows_are_unchanged():
    from y_web.src.hpc.platforms import HPC_PLATFORMS

    assert set(HPC_PLATFORMS) == {
        "microblogging",
        "photo_sharing",
        "instant_messaging",
        "dating",
    }
    assert HPC_PLATFORMS["instant_messaging"].validates_config is True
    assert HPC_PLATFORMS["photo_sharing"].prompts_filename == "prompts_ygram.json"


def test_dating_is_a_valid_population_type():
    from y_web.src.agents.platform import (
        VALID_POPULATION_TYPES,
        normalize_population_username_type,
    )

    assert "dating" in VALID_POPULATION_TYPES
    assert normalize_population_username_type("Dating") == "dating"
    assert normalize_population_username_type("unknown") == "microblogging"


def test_active_dating_experiments_block_runtime_mutation(monkeypatch):
    from y_web.routes.admin.sub.experiments import _external_runtimes as er

    seen = {}

    class _Query:
        def filter(self, *conds):
            seen.setdefault("filters", []).append(conds)
            return self

        def all(self):
            return []

    fake = MagicMock()
    fake.query = _Query()
    monkeypatch.setattr(er, "Exps", fake)
    assert er._runtime_group_active_experiments("dating") == []
    assert len(seen["filters"]) == 3  # not remote, platform, running or active


def test_the_builtin_copy_lists_dating():
    import json
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "external_runtime"
        / "builtin_plugins.json"
    )
    keys = [p["key"] for p in json.loads(path.read_text())["plugins"]]
    assert "dating" in keys
    assert keys.index("dating") == keys.index("instant_messaging") + 1
