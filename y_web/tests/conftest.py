"""
Pytest configuration and fixtures for y_web tests
"""

import builtins
import os
import tempfile
from pathlib import Path

import pytest
from flask import Flask
from flask_login import LoginManager
from sqlalchemy.pool import NullPool
from werkzeug.security import generate_password_hash

# Use the actual y_web database instance so that all registered models
# (Admin_users, User_mgmt, Exps, …) are included when create_all() runs.
from y_web import db

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LEGACY_ROOT = Path("/Users/rossetti/PycharmProjects/YWeb")
_ORIG_OPEN = builtins.open
_ORIG_PATH_OPEN = Path.open


def _remap_legacy_repo_path(path_like):
    try:
        raw = os.fspath(path_like)
    except Exception:
        return path_like
    if isinstance(raw, str) and raw.startswith(str(_LEGACY_ROOT)):
        suffix = raw[len(str(_LEGACY_ROOT)) :].lstrip("/\\")
        candidate = _REPO_ROOT / suffix
        if candidate.exists():
            return candidate
    return path_like


def _patched_open(file, *args, **kwargs):
    return _ORIG_OPEN(_remap_legacy_repo_path(file), *args, **kwargs)


def _patched_path_open(self, *args, **kwargs):
    remapped = _remap_legacy_repo_path(self)
    if isinstance(remapped, Path):
        return _ORIG_PATH_OPEN(remapped, *args, **kwargs)
    return _ORIG_PATH_OPEN(self, *args, **kwargs)


builtins.open = _patched_open
Path.open = _patched_path_open


def pytest_collection_modifyitems(config, items):
    """
    Skip external-repository contract tests unless explicitly enabled.

    Opt-in:
      YSOCIAL_TEST_EXTERNAL_REPOS=1 pytest ...
    """
    enabled = str(os.environ.get("YSOCIAL_TEST_EXTERNAL_REPOS", "")).strip() == "1"
    if enabled:
        skip_external_marker = None
    else:
        skip_external_marker = pytest.mark.skip(
            reason=(
                "external repository tests are disabled by default; "
                "set YSOCIAL_TEST_EXTERNAL_REPOS=1 to enable"
            )
        )

    ci_skip_jupyter_utils = (
        str(os.environ.get("GITHUB_ACTIONS", "")).strip().lower() == "true"
        and str(os.environ.get("YSOCIAL_TEST_JUPYTER_UTILS", "")).strip() != "1"
    )
    skip_jupyter_utils_marker = pytest.mark.skip(
        reason=(
            "test_system_jupyter_utils.py is skipped by default on GitHub Actions; "
            "set YSOCIAL_TEST_JUPYTER_UTILS=1 to enable"
        )
    )

    for item in items:
        if skip_external_marker is not None and "external_repo" in item.keywords:
            item.add_marker(skip_external_marker)
        if ci_skip_jupyter_utils and "test_system_jupyter_utils.py" in item.nodeid:
            item.add_marker(skip_jupyter_utils_marker)


@pytest.fixture(autouse=True)
def _redirect_create_sqlite_db(monkeypatch):
    """
    Redirect create_sqlite_db() to copy real DB files to temp locations.

    The y_web/db/dashboard.db may have a stale SQLite journal from a previous
    interrupted write, causing disk I/O errors in any test that calls create_app().
    Copying just the .db file (not the journal) to a writable temp location gives
    each test an isolated, journal-free copy with the original seeded data intact.
    """
    import shutil
    import tempfile
    from sqlalchemy.pool import NullPool

    _REPO_ROOT = Path(__file__).resolve().parents[2]
    _DB_DIR = _REPO_ROOT / "y_web" / "db"
    _REAL_DASHBOARD = _DB_DIR / "dashboard.db"
    _REAL_DUMMY = _DB_DIR / "dummy.db"

    handles = []

    def _copy_create_sqlite_db(app):
        fd_admin, path_admin = tempfile.mkstemp(suffix=".db")
        fd_exp, path_exp = tempfile.mkstemp(suffix=".db")
        os.close(fd_admin)
        os.close(fd_exp)

        # Copy real DB files if they exist (preserving seeded data),
        # otherwise leave as empty SQLite files.
        if _REAL_DASHBOARD.exists():
            shutil.copy2(str(_REAL_DASHBOARD), path_admin)
        if _REAL_DUMMY.exists():
            shutil.copy2(str(_REAL_DUMMY), path_exp)

        handles.extend([path_admin, path_exp])
        app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{path_admin}"
        app.config["SQLALCHEMY_BINDS"] = {
            "db_admin": f"sqlite:///{path_admin}",
            "db_exp": f"sqlite:///{path_exp}",
        }
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "connect_args": {"check_same_thread": False},
            "poolclass": NullPool,
        }
        # Required by run_migrations() to locate the SQLite files for direct migrations
        app.config["DASHBOARD_DB_PATH"] = path_admin
        app.config["DUMMY_DB_PATH"] = path_exp

    monkeypatch.setattr("y_web.db_init.create_sqlite_db", _copy_create_sqlite_db)
    monkeypatch.setattr("y_web.db_init.sqlite.create_sqlite_db", _copy_create_sqlite_db)

    yield

    for path in handles:
        try:
            os.unlink(path)
        except Exception:
            pass



@pytest.fixture(autouse=True)
def _patch_db_schema_guard(monkeypatch):
    """
    Suppress ensure_population_username_type_column() during tests.

    This function inspects the real on-disk dashboard.db to add a schema column.
    It is irrelevant to unit/integration tests that use temp or in-memory databases,
    and fails with a disk I/O error when the real DB has a stale SQLite journal.
    """
    monkeypatch.setattr(
        "y_web.src.agents.platform.ensure_population_username_type_column",
        lambda: None,
    )



@pytest.fixture
def app():
    """Create and configure a new app instance for each test."""
    # Use separate temporary databases for each SQLAlchemy bind to avoid
    # SQLite write-lock conflicts when multiple engines target the same file.
    db_fd, db_path = tempfile.mkstemp()
    db_fd_admin, db_path_admin = tempfile.mkstemp()
    db_fd_exp, db_path_exp = tempfile.mkstemp()

    # Create minimal Flask app
    app = Flask(__name__)
    app.config.update(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "SECRET_KEY": "test-secret-key",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
            "SQLALCHEMY_BINDS": {
                "db_admin": f"sqlite:///{db_path_admin}",
                "db_exp": f"sqlite:///{db_path_exp}",
            },
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            # NullPool closes connections immediately after use, preventing
            # "database is locked" errors when y_web.db is re-initialised across
            # multiple test apps in the same pytest session.
            "SQLALCHEMY_ENGINE_OPTIONS": {
                "connect_args": {"check_same_thread": False},
                "poolclass": NullPool,
            },
        }
    )

    # Initialize extensions
    db.init_app(app)
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    with app.app_context():
        from y_web.src.models import Admin_users, User_mgmt

        # Import models before create_all so SQLAlchemy metadata includes all tables.
        # Explicitly initialize all binds; some CI environments do not auto-create
        # non-default bind tables when create_all() is called without bind args.
        try:
            db.create_all(bind_key="__all__")
        except TypeError:
            # Older Flask-SQLAlchemy variants without bind_key support.
            db.create_all()

        # Create test admin user
        admin_user = Admin_users(
            username="admin",
            email="admin@test.com",
            password=generate_password_hash("admin123"),
            role="admin",
            last_seen="2023-01-01",
        )
        db.session.add(admin_user)

        # Create test regular user
        regular_user = User_mgmt(
            username="testuser",
            email="testuser@test.com",
            password=generate_password_hash("test123"),
            joined_on=1234567890,
        )
        db.session.add(regular_user)

        db.session.commit()

        # Set up user loader for flask-login
        @login_manager.user_loader
        def load_user(user_id):
            return db.session.get(User_mgmt, int(user_id))

    yield app

    os.close(db_fd)
    os.unlink(db_path)
    os.close(db_fd_admin)
    os.unlink(db_path_admin)
    os.close(db_fd_exp)
    os.unlink(db_path_exp)


@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """A test runner for the app's Click commands."""
    return app.test_cli_runner()


@pytest.fixture
def auth(client):
    """Authentication helper for tests."""

    class AuthActions:
        def __init__(self, client):
            self._client = client

        def login(self, username="admin", password="admin123"):
            return self._client.post(
                "/login", data={"email": "admin@test.com", "password": password}
            )

        def logout(self):
            return self._client.get("/logout")

    return AuthActions(client)
