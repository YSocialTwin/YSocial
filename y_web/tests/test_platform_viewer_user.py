"""The ``viewer_user`` hook: who a platform says is looking at a page, for extensions that act on their behalf."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from y_web.platforms.base import PlatformProvider

ANNOTATION = (
    Path(__file__).resolve().parents[2]
    / "external"
    / "frontend_adds-on"
    / "modules"
    / "post_annotation"
    / "backend"
    / "__init__.py"
)


def test_a_platform_without_its_own_viewers_answers_none():
    assert PlatformProvider().viewer_user(SimpleNamespace(idexp=1)) is None


@pytest.mark.skipif(not ANNOTATION.exists(), reason="frontend_adds-on is not installed")
def test_annotations_ask_the_platform_who_the_viewer_is(monkeypatch, app):
    spec = importlib.util.spec_from_file_location(
        "_post_annotation_backend", ANNOTATION
    )
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # the plugin needs its own surroundings
        pytest.skip(f"annotation backend not importable here: {exc}")

    viewer = object()
    provider = SimpleNamespace(viewer_user=lambda exp: viewer)
    exp = SimpleNamespace(platform_type="photo_sharing")
    from y_web.sdk.extensions.platforms import registry

    monkeypatch.setattr(module, "_experiment_platform", lambda exp_id: "photo_sharing")
    monkeypatch.setattr(module.db.session, "get", lambda model, key: exp, raising=False)
    monkeypatch.setattr(registry, "for_experiment", lambda e: provider)
    assert module._resolve_experiment_user(7) is viewer
