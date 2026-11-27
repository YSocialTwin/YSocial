"""Canary platform: a platform nobody wrote into the core works with no change to the core.

The repository is built in a temporary folder from the plain pieces of the platform model (a ``meta/registry.json``
declaration, a ``ysocial_platform`` package with a provider, a template, a static tour script and a prompt folder)
and found by discovery alone. If the core ever needs a list or a branch that names a platform, this test is the one
that stops: nothing here is registered anywhere but through the SDK declaration.
"""

import json
import types
from pathlib import Path

import pytest

from y_web import prompt_store
from y_web.platforms import discovery, extension, registry

pytestmark = pytest.mark.unit

CANARY_KEY = "canary_zz"

PROVIDER = """
from pathlib import Path

from y_web.platforms.base import PlatformProvider


class Canary(PlatformProvider):
    key = "canary_zz"
    label = "Canary"

    def prompt_pack_roots(self):
        return (Path(__file__).parent / "prompts",)

    def tutorial_scripts(self):
        return ("js/tutorials.js",)
"""


def _canary_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "YCanary"
    package = repo / "ysocial_platform"
    (package / "prompts").mkdir(parents=True)
    (package / "templates" / "admin").mkdir(parents=True)
    (package / "static" / "js").mkdir(parents=True)
    (repo / "meta").mkdir()
    (package / "__init__.py").write_text("")
    (package / "provider.py").write_text(PROVIDER)
    (package / "templates" / "admin" / "canary_page.html").write_text("<p>canary</p>")
    (package / "static" / "js" / "tutorials.js").write_text("// canary tour")
    (package / "prompts" / "prompts_internal.json").write_text(
        json.dumps({"canary__greeting": "Hello {name}"})
    )
    (repo / "meta" / "registry.json").write_text(
        json.dumps(
            {
                "platform": {
                    "key": CANARY_KEY,
                    "api_version": "1.6",
                    "provider": "ysocial_platform.provider:Canary",
                }
            }
        )
    )
    return repo


@pytest.fixture
def canary(tmp_path, monkeypatch):
    from y_web.src.external_runtime import backend_plugins  # noqa: F401
    from y_web.src.external_runtime import registry as runtime_registry

    specs = {"ycanary": types.SimpleNamespace(path=_canary_repo(tmp_path))}
    monkeypatch.setattr(runtime_registry, "supported_repos", lambda: specs)
    monkeypatch.setattr(discovery, "_DISCOVERED", {})
    before = dict(registry._PROVIDERS)
    prompt_store._cache.clear()
    assert discovery.discover_platforms() == {"ycanary": []}
    yield registry.get(CANARY_KEY)
    registry._PROVIDERS.clear()
    registry._PROVIDERS.update(before)
    prompt_store._cache.clear()


def test_discovery_alone_registers_the_platform(canary):
    assert canary is not None and canary.key == CANARY_KEY
    assert canary.package_dir.name == "ysocial_platform"
    assert registry.resolve(CANARY_KEY) is canary


def test_its_templates_and_tour_are_served_without_the_core_knowing_it(canary):
    name = extension.provider_template(CANARY_KEY, "admin/canary_page.html")
    assert name.endswith("admin/canary_page.html") and name != "admin/canary_page.html"
    assert canary.tutorial_scripts() == ("js/tutorials.js",)
    assert (canary.package_dir / "static" / "js" / "tutorials.js").is_file()


def test_its_internal_prompts_are_read_through_the_prompt_store(canary):
    assert prompt_store.get("canary__greeting", "en") == "Hello {name}"


def test_no_list_of_the_core_names_the_canary():
    core = Path(__file__).resolve().parents[1]
    for path in core.rglob("*"):
        if path.suffix not in {".py", ".html", ".js", ".json"} or "tests" in path.parts:
            continue
        assert CANARY_KEY not in path.read_text(encoding="utf-8", errors="ignore"), path
