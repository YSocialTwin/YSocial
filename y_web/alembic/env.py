"""Alembic environment for YSocial.

This file is used by Flask-Migrate / Alembic when running migration commands:

    flask --app y_social.py db upgrade   # apply pending migrations
    flask --app y_social.py db migrate   # generate a new migration
    flask --app y_social.py db current   # show current revision
    flask --app y_social.py db stamp <rev>   # mark DB at a given revision

Configuration is injected at runtime by Flask-Migrate via the Flask app
context; no standalone alembic.ini is needed.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from flask import current_app

# Alembic Config object (access to values in alembic.ini, or Flask-Migrate's
# in-memory config equivalent).
config = context.config

# Set up Python logging from the config file when present.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Flask-Migrate injects target_metadata via the Flask app's extensions.
# We fall back to the db object imported directly if the extension is absent.
try:
    target_metadata = current_app.extensions["migrate"].db.metadata
except (RuntimeError, KeyError):
    # Outside Flask application context — used when running alembic directly.
    from y_web import db as _db  # noqa: E402  (import here to avoid circular at top)
    target_metadata = _db.metadata


def _get_url() -> str:
    """Return the database URL from the Flask app config (preferred) or env."""
    try:
        return current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
    except RuntimeError:
        import os
        return os.environ.get("DATABASE_URL", "sqlite:///y_web/db/dashboard.db")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (no live DB connection required)."""
    url = _get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (live DB connection)."""
    # Flask-Migrate may supply the engine directly via connectable.
    connectable = config.attributes.get("connection", None)

    if connectable is None:
        # Fall back to creating an engine from the app config URL.
        from sqlalchemy import engine_from_config, pool

        connectable = engine_from_config(
            {"sqlalchemy.url": _get_url()},
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
