"""Static guards for the packaging and distribution files (no build is run)."""

import pathlib
import re

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = pathlib.Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "deployment" / "docker" / "compose"


def test_release_upload_only_on_release_events():
    text = (ROOT / ".github" / "workflows" / "release_package.yml").read_text(
        encoding="utf-8"
    )
    assert "github.event_name == 'release'" in text


@pytest.mark.parametrize("name", sorted(p.name for p in COMPOSE.glob("*.yml")))
def test_compose_files_parse(name):
    data = yaml.safe_load((COMPOSE / name).read_text(encoding="utf-8"))
    assert "services" in data and "ysocial" in data["services"]


@pytest.mark.parametrize(
    "name", ["docker-compose-postgresql.yml", "docker-compose-postgresql_gpu.yml"]
)
def test_postgres_compose_is_consistent(name):
    services = yaml.safe_load((COMPOSE / name).read_text(encoding="utf-8"))["services"]
    db_env = services["db"]["environment"]
    assert db_env.get(
        "POSTGRES_PASSWORD"
    ), "the postgres image refuses to start without it"
    app_env = {e.split("=", 1)[0] for e in services["ysocial"]["environment"]}
    assert {
        "PG_HOST",
        "PG_USER",
        "PG_PASSWORD",
        "PG_DBNAME",
    } <= app_env  # read by y_web/db_init/postgresql.py
    assert "ysocial" in services and services["ysocial"]["depends_on"]


def test_dockerignore_keeps_context_small():
    ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8").split()
    assert ".git" in ignored


def test_one_python_version_in_ci_build_and_docker():
    """E0: CI, release packaging, formatter and Docker base agree on Python 3.12 / Ubuntu 24.04."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    for name in ("ci-tests.yml", "format-code.yml", "release-packaging.yml"):
        text = (root / ".github" / "workflows" / name).read_text()
        versions = set(re.findall(r"python-version:\s*\[?.([\d.]+).", text))
        assert versions == {"3.12"}, (name, versions)
    froms = [
        line
        for line in (root / "Dockerfile").read_text().splitlines()
        if line.startswith("FROM ")
    ]
    assert froms and all(line.startswith("FROM ubuntu:24.04") for line in froms)
