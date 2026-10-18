"""Static guards for the packaging and distribution files (no build is run)."""

import ast
import pathlib
import re

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = pathlib.Path(__file__).resolve().parents[2]
SPEC = (ROOT / "y_social.spec").read_text(encoding="utf-8")
COMPOSE = ROOT / "deployment" / "docker" / "compose"


def test_spec_is_valid_python():
    ast.parse(SPEC)


def test_spec_ships_files_loaded_from_disk():
    # Alembic lists the revision files of versions/ on disk; translations and prompt files are read as files.
    assert '"y_web", "alembic"' in SPEC
    assert '"y_web", "translations"' in SPEC
    assert "prompts_internal" in SPEC
    assert '"data_schema"' in SPEC


def test_spec_data_sources_exist():
    for source in re.findall(
        r'os\.path\.join\(basedir, ((?:"[^"]+"(?:, )?)+)\), "', SPEC
    ):
        parts = re.findall(r'"([^"]+)"', source)
        if parts[0] in {"config_files", "images", "db"}:  # created or optional
            continue
        assert (ROOT.joinpath(*parts)).exists(), "/".join(parts)


def test_spec_names_real_modules():
    hidden = ast.literal_eval(
        re.search(r"hidden_imports = (\[.*?\n\])", SPEC, re.S).group(1)
    )
    assert "PIL" in hidden and "pillow" not in hidden
    assert "pyautogen" not in hidden  # not a dependency


def test_workflows_reference_existing_files():
    text = (ROOT / ".github" / "workflows" / "build-executables.yml").read_text(
        encoding="utf-8"
    )
    for path in re.findall(r"--entitlements (\S+)", text):
        assert (ROOT / path).exists(), path
    assert "admin@ysocial.com" not in text  # default account is admin@y-not.social


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
