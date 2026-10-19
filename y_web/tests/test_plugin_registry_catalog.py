"""Public plugin registry client (``external_runtime/catalog.py``)."""

import json
from pathlib import Path

import pytest

from y_web.src.external_runtime import catalog
from y_web.src.external_runtime.registry import (
    SUPPORTED_EXTERNAL_REPOS,
    grouped_runtime_specs,
    runtime_spec,
    set_catalog_specs,
    supported_repos,
)

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]


def _entry(**over):
    entry = {
        "id": "sentiment_lab",
        "name": "Sentiment Lab",
        "description": "Sentiment tools.",
        "category": "backend_extensions",
        "repo": "someone/sentiment-lab",
        "branch": "main",
        "recipe": "pip-editable",
        "trust": "community",
    }
    entry.update(over)
    return entry


def _registry(*entries):
    return {"schema_version": 1, "plugins": list(entries)}


@pytest.fixture(autouse=True)
def _reset(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog, "cache_path", lambda: tmp_path / "cache.json")
    set_catalog_specs({})
    yield
    set_catalog_specs({})


def test_valid_entry_becomes_a_spec():
    specs, problems = catalog.parse_registry(_registry(_entry()))
    assert problems == []
    spec = specs["sentiment_lab"]
    assert spec.repo_url == "https://github.com/someone/sentiment-lab.git"
    assert spec.github_repo == "someone/sentiment-lab"
    assert spec.group == "backend_settings" and spec.source == "registry"
    assert spec.install_commands == (("python", "-m", "pip", "install", "-e", "."),)
    assert spec.path.name == "sentiment-lab"
    assert spec.trust == "community" and spec.is_private is False


def test_official_trust_only_for_official_owners():
    ok = _entry(id="own_plugin", repo="YSocialTwin/own", trust="official")
    fake = _entry(id="fake_official", repo="mallory/own2", trust="official")
    specs, _ = catalog.parse_registry(_registry(ok, fake))
    assert specs["own_plugin"].trust == "official"
    assert specs["fake_official"].trust == "community"


@pytest.mark.parametrize(
    "bad",
    [
        {"id": "Bad-Id"},
        {"repo": "https://evil.example/x/y"},
        {"repo": "owner/name/extra"},
        {"recipe": "curl | sh"},
        {"category": "nope"},
        {"branch": "../../etc"},
        {"directory": "../escape"},
        {"name": ""},
        {"import_name": "os; import sys"},
        {"min_ysocial_version": "latest"},
        {"min_ysocial_version": "99.0.0"},
        {"id": "microblogging_client"},  # built-in key
        {"repo": "YSocialTwin/YClient"},  # built-in repository
        {"directory": "YServer"},  # built-in directory
    ],
)
def test_bad_entries_are_skipped(bad):
    specs, problems = catalog.parse_registry(_registry(_entry(**bad)), "4.0.0")
    assert specs == {}
    assert problems


def test_one_bad_entry_does_not_hide_the_good_ones():
    specs, problems = catalog.parse_registry(
        _registry(_entry(recipe="x"), _entry(id="good_one", repo="a/good"))
    )
    assert list(specs) == ["good_one"] and len(problems) == 1


def test_duplicate_id_directory_and_repo_are_rejected():
    first = _entry()
    dup_dir = _entry(id="other_one", repo="x/sentiment-lab")
    specs, problems = catalog.parse_registry(_registry(first, dup_dir))
    assert list(specs) == ["sentiment_lab"] and problems


@pytest.mark.parametrize(
    "payload", [[], {"plugins": []}, {"schema_version": 2, "plugins": []}]
)
def test_unsupported_files_yield_nothing(payload):
    specs, problems = catalog.parse_registry(payload)
    assert specs == {} and problems


def test_merge_never_shadows_built_in_plugins():
    specs, _ = catalog.parse_registry(_registry(_entry()))
    set_catalog_specs({**specs, "forum_client": specs["sentiment_lab"]})
    merged = supported_repos()
    assert merged["forum_client"] is SUPPORTED_EXTERNAL_REPOS["forum_client"]
    assert runtime_spec("sentiment_lab").label == "Sentiment Lab"
    groups = {key: [s.key for s in items] for key, _, items in grouped_runtime_specs()}
    assert "sentiment_lab" in groups["backend_settings"]
    set_catalog_specs({})
    assert "sentiment_lab" not in supported_repos()


def test_refresh_from_file_applies_and_caches(tmp_path, monkeypatch):
    source = tmp_path / "registry.json"
    source.write_text(json.dumps(_registry(_entry())), encoding="utf-8")
    monkeypatch.setenv(catalog.REGISTRY_URL_ENV, str(source))
    assert catalog.refresh_catalog() is True
    assert "sentiment_lab" in supported_repos()
    assert catalog.catalog_report()["source"] == "remote"
    assert (tmp_path / "cache.json").exists()

    set_catalog_specs({})
    assert catalog.load_cached_catalog() is True
    assert "sentiment_lab" in supported_repos()
    assert catalog.catalog_report()["source"] == "cache"


def test_failed_fetch_keeps_what_is_loaded(tmp_path, monkeypatch):
    source = tmp_path / "registry.json"
    source.write_text(json.dumps(_registry(_entry())), encoding="utf-8")
    monkeypatch.setenv(catalog.REGISTRY_URL_ENV, str(source))
    assert catalog.refresh_catalog()
    monkeypatch.setenv(catalog.REGISTRY_URL_ENV, str(tmp_path / "missing.json"))
    assert catalog.refresh_catalog() is False
    assert "sentiment_lab" in supported_repos()
    assert catalog.catalog_report()["problems"]


def test_invalid_remote_file_does_not_replace_a_good_one(tmp_path, monkeypatch):
    source = tmp_path / "registry.json"
    source.write_text(json.dumps(_registry(_entry())), encoding="utf-8")
    monkeypatch.setenv(catalog.REGISTRY_URL_ENV, str(source))
    assert catalog.refresh_catalog()
    source.write_text(json.dumps({"schema_version": 9, "plugins": []}), "utf-8")
    assert catalog.refresh_catalog() is False
    assert "sentiment_lab" in supported_repos()


def test_registry_can_be_disabled(monkeypatch):
    monkeypatch.setenv(catalog.REGISTRY_URL_ENV, "off")
    assert catalog.registry_url() is None
    assert catalog.refresh_catalog() is False


def test_default_registry_url_points_to_the_official_repository(monkeypatch):
    monkeypatch.delenv(catalog.REGISTRY_URL_ENV, raising=False)
    assert "YSocialTwin/plugin-registry" in catalog.registry_url()


def test_recipes_are_fixed_and_have_no_shell():
    for commands in catalog.RECIPES.values():
        for command in commands:
            assert command[:3] == ("python", "-m", "pip")


def test_community_install_needs_server_side_confirmation():
    route = (
        ROOT / "y_web/routes/admin/sub/experiments/_external_runtimes.py"
    ).read_text(encoding="utf-8")
    assert '"confirm_community"' in route and "_COMMUNITY_CONFIRM_ACTIONS" in route
    page = (ROOT / "y_web/templates/admin/external_runtime_detail.html").read_text(
        encoding="utf-8"
    )
    assert "confirm_community" in page
