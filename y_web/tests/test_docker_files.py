from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

D = Path(__file__).resolve().parents[2] / "docker"


def test_dockerfile_builds_from_wheel_on_python312():
    text = (D / "Dockerfile").read_text()
    assert text.count("python:3.12-slim") == 2
    assert "python -m build --wheel" in text
    assert "YSOCIAL_HOME=/data" in text
    assert "ollama" not in text.lower()


def test_entrypoint_uses_ysocial_command():
    text = (D / "entrypoint.sh").read_text()
    assert "exec ysocial" in text and text.startswith("#!/bin/sh")


def test_compose_profiles():
    cfg = yaml.safe_load((D / "compose.yml").read_text())
    assert cfg["services"]["postgres"]["profiles"] == ["postgres"]
    assert "profiles" not in cfg["services"]["ysocial"]
    assert "ysocial-data:/data" in cfg["services"]["ysocial"]["volumes"]


def test_release_workflow_is_draft_only_and_tag_triggered():
    wf = (D.parent / ".github/workflows/release-packaging.yml").read_text()
    assert 'tags: ["v*"]' in wf
    assert "--draft" in wf
    assert 'python-version: "3.12"' in wf
