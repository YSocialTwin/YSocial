"""The dating provider shipped by the YDating repository behaves like the one built into the core (phase F4).

While the core still carries a built-in copy, both must stay the same, so that moving the code changes nothing.
Skipped when YDating is not installed or does not declare its platform yet.
"""

import inspect
from pathlib import Path

import pytest

from y_web.platforms import discovery, registry
from y_web.platforms.builtin import Dating as BuiltinDating

REPO = Path(__file__).resolve().parents[2] / "external" / "YDating"

pytestmark = pytest.mark.unit

INSTALLED = (REPO / "meta" / "registry.json").exists()
needs_repository = pytest.mark.skipif(
    not INSTALLED, reason="YDating with its platform declaration is not installed"
)


@pytest.fixture
def repository_provider():
    before = dict(registry._PROVIDERS)
    discovery.discover_platforms()
    provider = registry.get("dating")
    yield provider
    registry._PROVIDERS.clear()
    registry._PROVIDERS.update(before)


@needs_repository
def test_the_repository_provider_is_the_one_registered(repository_provider):
    assert repository_provider.package_dir == REPO / "ysocial_platform"
    assert not isinstance(repository_provider, BuiltinDating)


@needs_repository
def test_same_values_and_hooks(repository_provider):
    builtin = BuiltinDating()
    for name, value in vars(BuiltinDating).items():
        if name.startswith("__"):
            continue
        other = vars(type(repository_provider)).get(name)
        assert other is not None, f"{name} is missing in the repository provider"
        if inspect.isfunction(value):
            assert inspect.getsource(other) == inspect.getsource(value), name
        else:
            assert other == value, name
    assert repository_provider.key == builtin.key
    assert repository_provider.order == builtin.order


@needs_repository
def test_decisions_that_need_no_experiment(repository_provider):
    builtin = BuiltinDating()
    for simulator in ("Standard", "HPC"):
        assert repository_provider.creation_rules(simulator) == builtin.creation_rules(
            simulator
        )
        assert repository_provider.clients_page(simulator) == builtin.clients_page(
            simulator
        )
    for available in ({"dating": True}, {"dating": False}, {}):
        assert repository_provider.resolve_simulator(
            "HPC", available
        ) == builtin.resolve_simulator("HPC", available)
    assert repository_provider.observer_url(7) == builtin.observer_url(7)
