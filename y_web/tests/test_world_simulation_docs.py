"""F7.4: the World Simulation documentation exists, is linked from the site navigation and the analytics mapping
equals what the ETL generates."""

import re
from pathlib import Path

from y_web.src.federation import analytics_etl

ROOT = Path(__file__).resolve().parents[2]


def test_the_analytics_mapping_is_the_generated_one():
    text = (ROOT / "docs" / "world-simulation-analytics-mapping.md").read_text()
    assert text.endswith(analytics_etl.render_field_map() + "\n")


def test_the_guides_are_in_the_navigation_and_their_links_exist():
    nav = (ROOT / "mkdocs.yml").read_text()
    for page in ("world-simulation.md", "reference/world-simulation-configuration.md"):
        assert page in nav and (ROOT / "docs" / page).is_file()
    for page in (
        "world-simulation.md",
        "reference/world-simulation-configuration.md",
        "multi-platform-simulations.md",
    ):
        base = (ROOT / "docs" / page).parent
        for target in re.findall(
            r"\]\(([^)#]+\.md)", (ROOT / "docs" / page).read_text()
        ):
            assert (base / target).resolve().is_file(), (page, target)


def test_the_configuration_reference_lists_every_default_of_the_coordinator():
    import json

    from ysocial_federation.coordinator import allocator, discovery, leave

    text = (
        ROOT / "docs" / "reference" / "world-simulation-configuration.md"
    ).read_text()
    for module in (allocator, discovery, leave):
        for key in module.DEFAULTS:
            assert f"`{key}`" in text, (module.__name__, key)
    for key in json.loads(json.dumps(discovery.DEFAULTS["beta"])):
        assert f"`{key}`" in text
