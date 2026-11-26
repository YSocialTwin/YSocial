"""Scenario Design finds the drivers declared by the platforms, and the editor lists what it always listed.

Before SCENARIO_API 1.3 a platform could not import the plugin (it lives in a private namespace), so the driver every
platform declares was silently ``None`` and only the plugin's bundled drivers ever ran. The snapshot in
``data/scenario_design_discovery_snapshot.json`` was recorded in that state: moving a driver to its platform must not
change what the administrator sees nor the capabilities of any (platform, simulator) pair.
"""

import json
from pathlib import Path

import pytest

from y_web.src.external_runtime import registry

SNAPSHOT = json.loads(
    (
        Path(__file__).parent / "data" / "scenario_design_discovery_snapshot.json"
    ).read_text("utf-8")
)

pytestmark = pytest.mark.unit


class _Exp:
    def __init__(self, platform_type, simulator_type="Standard"):
        self.platform_type, self.simulator_type = platform_type, simulator_type


@pytest.fixture
def discovery(app):
    if not registry.runtime_spec("scenario_design").path.exists():
        pytest.skip("the Scenario Design suite is not installed")
    from y_web.src.external_runtime.backend_plugins import import_from_suite

    base = "modules.scenario_editor.backend.drivers"
    module = import_from_suite("scenario_design", f"{base}.discovery")
    module.reset()
    yield module
    module.reset()


def test_the_editor_lists_the_same_platforms_in_the_same_order(discovery):
    assert discovery.available_platforms() == SNAPSHOT["available_platforms"]


def test_the_seed_menu_is_unchanged(discovery):
    from y_web.src.external_runtime.backend_plugins import import_from_suite

    base = import_from_suite(
        "scenario_design", "modules.scenario_editor.backend.drivers.base"
    )
    menu = []
    seen = set()
    for driver in discovery.drivers_for_listing():
        info = driver.info()
        if not info.has(base.CAP_SEED):
            continue
        for key in info.platform_keys:
            for simulator in info.simulator_types or ("Standard", "HPC"):
                if (key, simulator) in seen:
                    continue
                seen.add((key, simulator))
                menu.append(
                    [
                        key,
                        simulator,
                        info.platform_labels[key],
                        info.has(base.CAP_TOPICS),
                    ]
                )
    assert menu == SNAPSHOT["seed_menu"]


@pytest.mark.parametrize("pair", sorted(SNAPSHOT["capabilities"]))
def test_every_pair_keeps_its_capabilities(discovery, pair):
    platform, simulator = pair.split("|")
    driver = discovery.driver_for(
        _Exp(None if platform == "None" else platform, simulator)
    )
    expected = SNAPSHOT["capabilities"][pair]
    if expected is None:
        assert driver is None
    else:
        assert sorted(driver.info().capabilities) == expected


@pytest.mark.parametrize(
    "platform,simulator,module_part",
    [
        ("microblogging", "Standard", "microblogging_server"),
        ("microblogging", "HPC", "hpc_simulator"),
        ("forum", "Standard", "forum_server"),
        ("photo_sharing", "Standard", "photo_sharing"),
        ("instant_messaging", "Standard", "instant_messaging"),
    ],
)
def test_the_driver_of_an_installed_platform_is_the_one_it_declares(
    discovery, platform, simulator, module_part
):
    from y_web.sdk.extensions.platforms import registry as platforms

    if not any(
        p.key == platform and getattr(p, "scenario_design_driver", None) is not None
        for p in platforms.all_providers()
    ):
        pytest.skip(f"no installed platform declares a driver for {platform}")
    driver = discovery.driver_for(_Exp(platform, simulator))
    assert driver is not None
    assert module_part in type(driver).__module__, type(driver).__module__


@pytest.mark.parametrize("platform", ["photo_sharing", "instant_messaging"])
def test_platforms_without_fixed_order_recommenders_do_not_offer_them(
    discovery, platform
):
    """Photo sharing and instant messaging do not serve ``fixed:<name>`` recommenders: the editor hides the choice."""
    for simulator in ("Standard", "HPC"):
        driver = discovery.driver_for(_Exp(platform, simulator))
        assert driver is not None
        assert "fixed_recsys" not in driver.info().capabilities


@pytest.mark.parametrize("simulator", ["Standard", "HPC"])
def test_a_platform_without_a_driver_is_not_offered_and_is_refused_clearly(
    discovery, simulator
):
    """YCreator does not declare a Scenario Design driver (driver contract 1.3, no adapter hook): the editor does not
    list it and publishing for it is refused with the uniform 409, never with a traceback.
    """
    from y_web.src.external_runtime.backend_plugins import import_from_suite

    assert "creator" not in discovery.available_platforms()
    assert all(
        "creator" not in driver.info().platform_keys
        for driver in discovery.drivers_for_listing()
    )
    exp = _Exp("creator", simulator)
    assert discovery.driver_for(exp) is None
    base = import_from_suite(
        "scenario_design", "modules.scenario_editor.backend.adapters.base"
    )
    with pytest.raises(base.MaterializationAdapterError) as error:
        base.get_adapter_for(exp)
    assert error.value.http_status == 409
