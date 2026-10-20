"""The built-in plugins live in ``builtin_plugins.json`` (same data as before)."""

import dataclasses
import json
from pathlib import Path

import pytest

from y_web.src.external_runtime import catalog, registry
from y_web.src.external_runtime.registry import (
    EXTERNAL_DIR,
    SUPPORTED_EXTERNAL_REPOS,
    ExternalRuntimeSpec,
)

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = json.loads(
    (Path(__file__).parent / "data" / "builtin_specs_golden.json").read_text("utf-8")
)


def _normalise(spec: ExternalRuntimeSpec) -> dict:
    data = dataclasses.asdict(spec)
    data["path"] = str(spec.path.relative_to(EXTERNAL_DIR))
    for field in (
        "install_commands",
        "validate_entrypoints",
        "visible_to_usernames",
        "authors",
    ):
        data[field] = json.loads(json.dumps(data[field]))
    return data


def test_built_in_specs_are_identical_to_the_previous_hard_coded_ones():
    """Golden copy of the 12 specs taken before they moved to the JSON file."""
    assert [g["key"] for g in GOLDEN] == list(SUPPORTED_EXTERNAL_REPOS)
    for expected in GOLDEN:
        assert _normalise(SUPPORTED_EXTERNAL_REPOS[expected["key"]]) == expected


def test_every_built_in_plugin_has_a_real_description():
    """Not-installed plugins have no meta/info.json: the list page shows this text."""
    for spec in SUPPORTED_EXTERNAL_REPOS.values():
        assert 20 <= len(spec.description) <= 400, spec.key
        assert not spec.description.lower().startswith(("todo", "tbd", "placeholder"))


def test_built_in_specs_are_official_and_not_from_the_registry():
    for spec in SUPPORTED_EXTERNAL_REPOS.values():
        assert spec.trust == "official" and spec.source == "builtin"


def test_seeded_directories_are_the_simulation_runtimes():
    seeded = [e["directory"] for e in registry._BUILTIN_PAYLOAD if e.get("seed")]
    assert seeded == [
        "YClient",
        "YServer",
        "YClientReddit",
        "YServerReddit",
        "YSimulator",
        "YPhotoSharing",
    ]


def test_json_file_ships_in_the_wheel():
    assert registry.BUILTIN_PLUGINS_FILE.is_file()
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "src/external_runtime/builtin_plugins.json" in pyproject
    check = (ROOT / "scripts" / "packaging" / "check_wheel.py").read_text("utf-8")
    assert "y_web/src/external_runtime/builtin_plugins.json" in check


def test_public_registry_cannot_redefine_any_built_in_plugin():
    for spec in SUPPORTED_EXTERNAL_REPOS.values():
        entry = {
            "id": "other_plugin",
            "name": "x",
            "category": "backend_extensions",
            "repo": "a/b",
        }
        for clash in (
            {"id": spec.key},
            {"repo": spec.github_repo},
            {"directory": spec.path.name},
            {"directory": spec.path.name.upper()},
        ):
            specs, problems = catalog.parse_registry(
                {"schema_version": 1, "plugins": [{**entry, **clash}]}
            )
            assert specs == {} and problems, (spec.key, clash)


def test_every_entry_has_the_fields_the_loader_needs():
    for entry in registry._BUILTIN_PAYLOAD:
        for field in (
            "key",
            "label",
            "group",
            "group_label",
            "category",
            "category_label",
            "directory",
            "repo",
        ):
            assert entry.get(field), (entry.get("key"), field)
