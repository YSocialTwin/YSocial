"""Agents dashboard: no categories; each resource is tagged with the installed platforms it can be deployed on."""

import pytest
from flask import Flask

import y_web.i18n as i18n
import importlib

module = importlib.import_module("y_web.routes.admin.sub.agents")


@pytest.fixture
def app():
    flask_app = Flask("y_web")
    flask_app.config.update(TESTING=True, SECRET_KEY="t", SUPPORTED_LANGUAGES=("en", "it"))
    i18n.init_i18n(flask_app)
    return flask_app


CARDS = [
    {"title": "Agents", "deployment_tags": ["microblogging", "forum", "photo_sharing", "instant_messaging"]},
    {"title": "RSS", "deployment_tags": ["forum", "instant_messaging"]},
    {"title": "Images", "deployment_tags": ["forum"]},
    {"title": "Pages", "deployment_tags": ["microblogging", "instant_messaging"]},
]


def tags(app, installed):
    with app.test_request_context("/"):
        out = module._tag_agent_resource_cards(CARDS, installed)
    return {c["title"]: [t["label"] for t in c["platform_tags"]] for c in out}


def test_a_resource_for_every_installed_platform_is_tagged_all(app):
    result = tags(app, ["microblogging", "forum", "instant_messaging"])
    assert result["Agents"] == ["All"]
    assert result["RSS"] == ["Forum", "IM"]
    assert result["Images"] == ["Forum"]
    assert result["Pages"] == ["Microblogging", "IM"]


def test_tags_only_name_installed_platforms_and_hide_unusable_resources(app):
    # IM not installed: the forum RSS feeds carry only the forum tag
    assert tags(app, ["microblogging", "forum"])["RSS"] == ["Forum"]
    # forum not installed: forum-only resources disappear
    result = tags(app, ["microblogging", "instant_messaging"])
    assert "Images" not in result and result["RSS"] == ["IM"] and result["Pages"] == ["All"]


def test_a_single_installed_platform_is_named_not_all(app):
    assert tags(app, ["forum"]) == {"Agents": ["Forum"], "RSS": ["Forum"], "Images": ["Forum"]}


def test_nothing_installed_shows_nothing(app):
    assert tags(app, []) == {}


def test_platforms_installed_follow_the_runtimes(monkeypatch):
    present = {"microblogging_server", "microblogging_client", "instant_messaging", "forum_server"}
    monkeypatch.setattr(module, "_runtime_installed", lambda key: key in present)
    assert module._installed_platforms() == ["microblogging", "instant_messaging"]  # forum needs server and client
    monkeypatch.setattr(module, "_runtime_installed", lambda key: key == "hpc_simulator")
    assert module._installed_platforms() == ["microblogging"]
