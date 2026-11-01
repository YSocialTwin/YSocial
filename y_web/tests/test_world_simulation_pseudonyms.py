"""P5: the pseudonyms switch of the World Simulation forms reaches federation.json."""

import json
import os

import importlib

from y_web.src.federation import service
from y_web.tests.test_federation_service import world  # noqa: E402,F401  (fixture)

ws = importlib.import_module("y_web.routes.admin.sub.world_simulation")


def test_the_form_switch_becomes_the_pseudonyms_block():
    assert ws._options_from_form({"pseudonyms_enabled": "on"}).get("pseudonyms") == {"enabled": True}
    assert "pseudonyms" not in ws._options_from_form({})


def test_the_block_is_written_to_federation_json(world):  # noqa: F811
    app, exps, tmp = world
    fed = service.create_federation("p", list(exps.values()), owner="admin", seed=3, options={"pseudonyms": {"enabled": True}})
    with open(os.path.join(fed.folder, "federation.json")) as fh:
        assert json.load(fh)["pseudonyms"] == {"enabled": True}


def test_the_forms_and_the_italian_catalog_carry_the_option():
    root = os.path.join(os.path.dirname(__file__), "..")
    for name in ("new.html", "detail.html"):
        text = open(os.path.join(root, "templates", "admin", "world_simulation", name)).read()
        assert 'name="pseudonyms_enabled"' in text and "Use pseudonyms for authors in cross-posts" in text
    po = open(os.path.join(root, "translations", "it", "LC_MESSAGES", "messages.po")).read()
    assert 'msgid "Use pseudonyms for authors in cross-posts"' in po
