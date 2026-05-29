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
        return
    skip_marker = pytest.mark.skip(
        reason=(
            "external repository tests are disabled by default; "
            "set YSOCIAL_TEST_EXTERNAL_REPOS=1 to enable"
        )
    )
    for item in items:
        if "external_repo" in item.keywords:
            item.add_marker(skip_marker)


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
            return User_mgmt.query.get(int(user_id))

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
