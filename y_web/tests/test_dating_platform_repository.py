"""The dating platform provided by the YDating repository (phase F4: Dating lives outside the core).

Skipped when YDating is not installed or does not declare its platform.
"""

from pathlib import Path

import pytest

from y_web.platforms import discovery, registry

REPO = Path(__file__).resolve().parents[2] / "external" / "YDating"

pytestmark = pytest.mark.unit

INSTALLED = (REPO / "meta" / "registry.json").exists()
needs_repository = pytest.mark.skipif(
    not INSTALLED, reason="YDating with its platform declaration is not installed"
)


@pytest.fixture
def provider():
    before = dict(registry._PROVIDERS)
    discovery._DISCOVERED.pop("dating", None)
    registry._PROVIDERS.pop("dating", None)
    discovery.discover_platforms()
    found = registry.get("dating")
    yield found
    registry._PROVIDERS.clear()
    registry._PROVIDERS.update(before)


def test_without_the_repository_dating_is_not_a_platform_of_the_core():
    from y_web.platforms import builtin

    assert "dating" not in {p.key for p in (builtin.Microblogging(),)}
    assert not hasattr(builtin, "Dating")


@needs_repository
def test_the_repository_provider_is_registered(provider):
    assert provider is not None and provider.package_dir == REPO / "ysocial_platform"
    assert (provider.key, provider.order, provider.icon) == ("dating", 50, "heart")
    assert provider.observer_url(7) == "/7/dating"
    assert provider.owns_database and provider.marker_table == "dating_profile"


@needs_repository
def test_the_decisions_the_core_asks_for(provider):
    for simulator in ("Standard", "HPC"):
        rules = provider.creation_rules(simulator)
        assert rules.database == "own"
        assert rules.forced["opinion_dynamics_enabled"] is False
        assert provider.clients_page(simulator) == "clientsr.clients_dating"
    assert provider.resolve_simulator("HPC", {"dating": True})[1] is None
    assert provider.resolve_simulator("HPC", {"dating": False})[1] is not None


@needs_repository
def test_the_library_and_the_views_come_from_the_repository(provider):
    population = registry.library("dating", "population")
    assert population.__name__.endswith("ysocial_platform.dating.population")
    assert callable(population.has_dating_fields)
