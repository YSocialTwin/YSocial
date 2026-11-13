"""Files that live in the repository of a platform, for the tests that read them from disk.

A test that needs one is skipped where the repository is not installed (it is a private plugin).
"""

from pathlib import Path

import pytest

EXTERNAL = Path(__file__).resolve().parents[2] / "external"


def platform_template(repo: str, relative: str) -> str:
    """Text of a template under ``<repo>/ysocial_platform/templates``; skips the test when it is not there."""
    path = EXTERNAL / repo / "ysocial_platform" / "templates" / relative
    if not path.is_file():
        pytest.skip(f"{repo} with its platform pages is not installed")
    return path.read_text(encoding="utf-8")


def _moved():
    import json

    return json.loads(
        (Path(__file__).parent / "data" / "platform_baseline" / "moved.json").read_text(
            "utf-8"
        )
    )["templates"]


def moved_template_path(old_name: str):
    """File of a template that left the core (``old_name`` is its former name), ``None`` where its repository is absent."""
    spec = _moved().get(old_name)
    if spec is None:
        return None
    path = (
        EXTERNAL
        / spec["repo"]
        / "ysocial_platform"
        / "templates"
        / spec["to"].split("/", 1)[1]
    )
    return path if path.is_file() else None


def namespaced_template_path(name: str):
    """File behind a ``@<platform>/<path>`` template name, ``None`` where its repository is absent."""
    for old, spec in _moved().items():
        if spec["to"] == name:
            return moved_template_path(old)
    return None


def platform_static_path(repo: str, relative: str) -> Path:
    """File under ``<repo>/ysocial_platform/static``; skips the test when it is not there."""
    path = EXTERNAL / repo / "ysocial_platform" / "static" / relative
    if not path.is_file():
        pytest.skip(f"{repo} with its platform files is not installed")
    return path
