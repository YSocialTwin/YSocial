"""YForum is listed with the other HPC runtimes in external/plugins.json (the Plugins admin page reads it)."""

import json
from pathlib import Path

import pytest

PLUGINS = Path(__file__).resolve().parents[2] / "external" / "plugins.json"


def test_yforum_is_listed_next_to_the_other_runtimes():
    entries = {p["plugin_name"]: p for p in json.loads(PLUGINS.read_text())["plugins"]}
    if (
        not entries
    ):  # the file is rewritten from the plugins found in external/: a clean checkout has none
        pytest.skip("no plugin is checked out under external/")
    # the file is regenerated from the plugins found in external/ (sync_plugins_index): the two runtimes of the
    # HPC group must both be there, or the Plugins page does not list them
    # (the microblogging runtime is presented as YMicroblogging by its manifest, YSimulator is its repository name)
    assert "YForum" in entries
    assert {"YSimulator", "YMicroblogging"} & set(entries), sorted(entries)
    forum = entries["YForum"]
    assert forum["group"] == "HPC" and forum["category"] == "Simulation Runtime Stack"
    assert forum["repository_url"] == "https://github.com/YSocialTwin/YForum"
