"""Decoupling gate: the core and the platforms/extensions must not grow more tangled.

- a platform repository (YServer, YForum, ...) imports the core through ``y_web.sdk`` only: zero exceptions;
- an extension (ScenarioDesign, TrainingModules, ...) may keep the imports it has today, never add one;
- the core does not name platforms more often than it does today.

The ceilings live in ``tests/data/decoupling_ceiling.json`` and may only be lowered. Repositories that are not
checked out are skipped. The measurements come from ``scripts/metrics/decoupling.py``.
"""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EXTERNAL = ROOT / "external"
CEILING = json.loads(
    (Path(__file__).parent / "data" / "decoupling_ceiling.json").read_text(encoding="utf-8")
)


def _load_metrics():
    spec = importlib.util.spec_from_file_location(
        "decoupling_metrics", ROOT / "scripts" / "metrics" / "decoupling.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


metrics = _load_metrics()


@pytest.mark.parametrize("repo", metrics.PLATFORM_REPOS)
def test_platform_imports_the_core_through_the_sdk_only(repo):
    if not (EXTERNAL / repo).is_dir():
        pytest.skip(f"{repo} is not checked out")
    found = metrics.platform_imports(EXTERNAL)[repo]["items"]
    assert found == [], (
        f"{repo} imports the core outside y_web.sdk: "
        + ", ".join(f"{i['file']} -> {i['module']}" for i in found)
        + ". Add the service to y_web.sdk and import it from there."
    )


@pytest.mark.parametrize("repo", metrics.EXTENSION_REPOS)
def test_extension_does_not_add_core_imports(repo):
    if not (EXTERNAL / repo).is_dir():
        pytest.skip(f"{repo} is not checked out")
    count = metrics.extension_imports(EXTERNAL)[repo]["outside_sdk"]
    ceiling = CEILING["extension_outside_sdk"][repo]
    assert count <= ceiling, (
        f"{repo} has {count} imports of the core outside y_web.sdk (ceiling {ceiling}): "
        "use y_web.sdk, or lower the ceiling if you removed some."
    )


def test_core_does_not_name_platforms_more_often():
    count = metrics.count_mentions(ROOT)["mentions"]
    ceiling = CEILING["platform_mentions_in_core"]
    assert count <= ceiling, (
        f"y_web names platforms {count} times (ceiling {ceiling}): "
        "route platform-specific behaviour through the provider, not through a name check."
    )
