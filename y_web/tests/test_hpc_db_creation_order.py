"""An HPC experiment database must end up consistent whichever side creates it first.

The web app may touch the (still empty) database before the HPC server starts, e.g. when a page of the experiment
is opened during setup; the server then adds the tables it owns. Afterwards both sides must find every column
they use (regression: ``no such column post.image_post_id`` and ``user_mgmt has no column last_active_day``, which
left the user's feed empty).
"""

import logging
import sqlite3
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.external_repo

YSIMULATOR = Path(__file__).resolve().parents[2] / "external" / "YSimulator"
if not (YSIMULATOR / "YSimulator" / "YServer" / "service_factory.py").exists():
    pytest.skip("YSimulator is not installed", allow_module_level=True)


@pytest.fixture()
def server_side(monkeypatch):
    monkeypatch.syspath_prepend(str(YSIMULATOR))
    for name in [m for m in sys.modules if m == "YSimulator" or m.startswith("YSimulator.")]:
        monkeypatch.delitem(sys.modules, name)
    logging.disable(logging.CRITICAL)
    yield
    logging.disable(logging.NOTSET)


def _columns(path):
    conn = sqlite3.connect(path)
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    found = {t: {r[1] for r in conn.execute(f"PRAGMA table_info({t})")} for t in tables}
    conn.close()
    return found


def _missing(path):
    from YSimulator.YServer.classes import models as server_models

    import y_web.src.models.experiment as web_models
    from y_web import db

    expected = {}
    for table in server_models.Base.metadata.sorted_tables:
        expected.setdefault(table.name, set()).update(c.name for c in table.columns)
    for mapper in db.Model.registry.mappers:
        if getattr(mapper.class_, "__bind_key__", None) == "db_exp":
            expected.setdefault(mapper.local_table.name, set()).update(c.name for c in mapper.local_table.columns)
    have = _columns(path)
    problems = []
    for table, columns in expected.items():
        if table not in have:
            problems.append(f"table {table} missing")
        elif columns - have[table]:
            problems.append(f"{table} lacks {sorted(columns - have[table])}")
    return problems


def _create_server_tables(directory):
    from YSimulator.YServer.service_factory import create_database_engine

    create_database_engine({"type": "sqlite", "path": "database_server.db"}, config_path=str(directory)).dispose()


@pytest.mark.parametrize(
    "order",
    [
        ["server", "web"],
        ["web", "server", "web"],
        ["web", "web", "web", "server", "web"],
    ],
    ids=lambda o: "-".join(o),
)
def test_database_is_consistent_whatever_creates_it_first(server_side, tmp_path, order):
    from y_web.src.experiment import schema

    schema._ENSURED_SCHEMAS.clear()
    path = tmp_path / "database_server.db"
    uri = f"sqlite:///{path}"
    for step in order:
        if step == "web":
            schema.ensure_experiment_schema_for_uri(uri)
        else:
            _create_server_tables(tmp_path)
    assert _missing(str(path)) == []
