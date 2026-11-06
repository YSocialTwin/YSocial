"""YForum is listed with the other HPC runtimes in external/plugins.json (the Plugins admin page reads it)."""

import json
from pathlib import Path

PLUGINS = Path(__file__).resolve().parents[2] / "external" / "plugins.json"


def test_yforum_is_listed_next_to_the_other_runtimes():
    entries = {p["plugin_name"]: p for p in json.loads(PLUGINS.read_text())["plugins"]}
    for name in ("YSimulator", "YForum", "YFederation", "YDating", "YInstantMessaging"):
        assert name in entries, name
    forum = entries["YForum"]
    assert forum["group"] == "HPC" and forum["category"] == "Simulation Runtime Stack"
    assert forum["repository_url"] == "https://github.com/YSocialTwin/YForum"
    assert entries["YFederation"]["group"] == "World Simulation"
