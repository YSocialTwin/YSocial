"""
Phase 11 validation tests.

Verifies that ``y_web/__init__.py`` has been correctly slimmed down by
extracting database initialisation logic into the ``y_web.db_init`` sub-package
while maintaining full backward compatibility.
"""

import importlib
import inspect
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 1. Package structure — db_init sub-package
# ---------------------------------------------------------------------------


def test_db_init_is_a_package():
    """y_web.db_init must be an importable package."""
    pkg = importlib.import_module("y_web.db_init")
    assert hasattr(pkg, "__path__"), "db_init should be a package with __path__"


def test_db_init_sub_modules_exist():
    """All expected sub-modules must be importable."""
    sub_modules = [
        "y_web.db_init.postgresql",
        "y_web.db_init.sqlite",
        "y_web.db_init.migrations",
    ]
    for mod_name in sub_modules:
        mod = importlib.import_module(mod_name)
        assert mod is not None, f"Sub-module {mod_name} could not be imported"


# ---------------------------------------------------------------------------
# 2. Canonical public API on db_init
# ---------------------------------------------------------------------------


def test_db_init_exposes_init_db():
    """y_web.db_init must expose init_db()."""
    pkg = importlib.import_module("y_web.db_init")
    assert callable(getattr(pkg, "init_db", None)), "db_init.init_db must be callable"


def test_db_init_exposes_create_postgresql_db():
    """y_web.db_init must re-export create_postgresql_db."""
    pkg = importlib.import_module("y_web.db_init")
    assert callable(
        getattr(pkg, "create_postgresql_db", None)
    ), "db_init.create_postgresql_db must be callable"


def test_db_init_exposes_create_sqlite_db():
    """y_web.db_init must re-export create_sqlite_db."""
    pkg = importlib.import_module("y_web.db_init")
    assert callable(
        getattr(pkg, "create_sqlite_db", None)
    ), "db_init.create_sqlite_db must be callable"


def test_db_init_exposes_run_migrations():
    """y_web.db_init must re-export run_migrations."""
    pkg = importlib.import_module("y_web.db_init")
    assert callable(
        getattr(pkg, "run_migrations", None)
    ), "db_init.run_migrations must be callable"


def test_db_init_all_list():
    """y_web.db_init.__all__ must declare the public API."""
    pkg = importlib.import_module("y_web.db_init")
    assert hasattr(pkg, "__all__"), "db_init must define __all__"
    for name in (
        "init_db",
        "create_postgresql_db",
        "create_sqlite_db",
        "run_migrations",
    ):
        assert name in pkg.__all__, f"{name!r} missing from db_init.__all__"


# ---------------------------------------------------------------------------
# 3. postgresql sub-module
# ---------------------------------------------------------------------------


def test_postgresql_module_has_create_postgresql_db():
    """y_web.db_init.postgresql must define create_postgresql_db."""
    mod = importlib.import_module("y_web.db_init.postgresql")
    assert callable(
        getattr(mod, "create_postgresql_db", None)
    ), "create_postgresql_db must be callable in db_init.postgresql"


def test_postgresql_function_accepts_app():
    """create_postgresql_db must accept a single positional argument (app)."""
    mod = importlib.import_module("y_web.db_init.postgresql")
    sig = inspect.signature(mod.create_postgresql_db)
    params = list(sig.parameters.keys())
    assert "app" in params, "create_postgresql_db must have an 'app' parameter"


# ---------------------------------------------------------------------------
# 4. sqlite sub-module
# ---------------------------------------------------------------------------


def test_sqlite_module_has_create_sqlite_db():
    """y_web.db_init.sqlite must define create_sqlite_db."""
    mod = importlib.import_module("y_web.db_init.sqlite")
    assert callable(
        getattr(mod, "create_sqlite_db", None)
    ), "create_sqlite_db must be callable in db_init.sqlite"


def test_sqlite_function_accepts_app():
    """create_sqlite_db must accept a single positional argument (app)."""
    mod = importlib.import_module("y_web.db_init.sqlite")
    sig = inspect.signature(mod.create_sqlite_db)
    params = list(sig.parameters.keys())
    assert "app" in params, "create_sqlite_db must have an 'app' parameter"


# ---------------------------------------------------------------------------
# 5. migrations sub-module
# ---------------------------------------------------------------------------


def test_migrations_module_has_run_migrations():
    """y_web.db_init.migrations must define run_migrations."""
    mod = importlib.import_module("y_web.db_init.migrations")
    assert callable(
        getattr(mod, "run_migrations", None)
    ), "run_migrations must be callable in db_init.migrations"


def test_migrations_function_signature():
    """run_migrations must accept (app, db_type, db)."""
    mod = importlib.import_module("y_web.db_init.migrations")
    sig = inspect.signature(mod.run_migrations)
    params = list(sig.parameters.keys())
    for required in ("app", "db_type", "db"):
        assert required in params, f"run_migrations must have a '{required}' parameter"


def test_agent_ext_migration_module_exists():
    """The agent_ext migration module must be present."""
    mod = importlib.import_module("y_web.migrations.add_agent_ext_table")
    assert callable(getattr(mod, "migrate_sqlite", None))
    assert callable(getattr(mod, "migrate_postgresql", None))


def test_agent_ext_migration_registered_in_startup_runner():
    """run_migrations must invoke the agent_ext migration."""
    path = Path("/Users/rossetti/PycharmProjects/YWeb/y_web/db_init/migrations.py")
    content = path.read_text(encoding="utf-8")
    assert "add_agent_ext_table" in content
    assert "Failed to run agent_ext table migration" in content


def test_population_pop_type_migration_module_exists():
    """The population pop_type migration module must be present."""
    mod = importlib.import_module("y_web.migrations.add_population_pop_type")
    assert callable(getattr(mod, "migrate_sqlite", None))
    assert callable(getattr(mod, "migrate_postgresql", None))


def test_population_pop_type_migration_registered_in_startup_runner():
    """run_migrations must invoke the population pop_type migration."""
    path = Path("/Users/rossetti/PycharmProjects/YWeb/y_web/db_init/migrations.py")
    content = path.read_text(encoding="utf-8")
    assert "add_population_pop_type" in content
    assert "Failed to run population pop_type migration" in content


# ---------------------------------------------------------------------------
# 6. y_web.__init__ still exposes core symbols
# ---------------------------------------------------------------------------


def test_y_web_still_has_db():
    """y_web must still expose the db SQLAlchemy instance."""
    import y_web

    assert hasattr(y_web, "db"), "y_web.db must still be exported"


def test_y_web_still_has_login_manager():
    """y_web must still expose the login_manager."""
    import y_web

    assert hasattr(y_web, "login_manager"), "y_web.login_manager must still be exported"


def test_y_web_still_has_create_app():
    """y_web must still expose create_app."""
    import y_web

    assert callable(
        getattr(y_web, "create_app", None)
    ), "y_web.create_app must be callable"


def test_y_web_create_postgresql_db_via_db_init():
    """create_postgresql_db must be accessible via the canonical y_web.db_init path."""
    from y_web.db_init import create_postgresql_db

    assert callable(
        create_postgresql_db
    ), "create_postgresql_db must be callable via y_web.db_init"


def test_y_web_init_line_count_reduced():
    """y_web/__init__.py should be well under 700 lines after Phase 11."""
    import os

    import y_web

    init_path = os.path.join(os.path.dirname(y_web.__file__), "__init__.py")
    with open(init_path) as fh:
        lines = fh.readlines()
    assert (
        len(lines) < 700
    ), f"y_web/__init__.py has {len(lines)} lines; expected < 700 after Phase 11 refactor"


# ---------------------------------------------------------------------------
# 7. init_db dispatcher — signature + raises on bad db_type
# ---------------------------------------------------------------------------


def test_init_db_signature():
    """init_db must accept (app, db_type, db)."""
    from y_web.db_init import init_db

    sig = inspect.signature(init_db)
    params = list(sig.parameters.keys())
    for required in ("app", "db_type", "db"):
        assert required in params, f"init_db must have a '{required}' parameter"


def test_init_db_raises_on_bad_db_type():
    """init_db must raise ValueError for unsupported db_type values."""
    from unittest.mock import MagicMock

    from y_web.db_init import init_db

    fake_app = MagicMock()
    fake_db = MagicMock()
    try:
        init_db(fake_app, "oracle", fake_db)
        assert False, "Expected ValueError for unsupported db_type"
    except ValueError as exc:
        assert "unsupported" in str(exc).lower(), f"Unexpected message: {exc}"
