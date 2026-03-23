"""
Database initialisation sub-package for YSocial.

Public API
----------
init_db(app, db_type)
    Configure SQLAlchemy on *app* for the requested backend and run all
    pending schema migrations.

create_postgresql_db(app)
    Low-level PostgreSQL setup (re-exported for backward compatibility).

create_sqlite_db(app)
    Low-level SQLite setup (re-exported for backward compatibility).

run_migrations(app, db_type, db)
    Apply all incremental schema migrations.
"""

from .migrations import run_migrations
from .postgresql import create_postgresql_db
from .sqlite import create_sqlite_db


def init_db(app, db_type, db):
    """
    Configure the database engine on *app* and run all migrations.

    Dispatches to :func:`create_sqlite_db` or :func:`create_postgresql_db`
    based on *db_type*, then calls :func:`run_migrations`.

    Args:
        app:     Configured Flask application instance.
        db_type: ``"sqlite"`` or ``"postgresql"``.
        db:      The Flask-SQLAlchemy :class:`~flask_sqlalchemy.SQLAlchemy`
                 instance (needed by the migration runner for ``db.create_all()``).

    Raises:
        ValueError: If *db_type* is not ``"sqlite"`` or ``"postgresql"``.
    """
    if db_type == "sqlite":
        create_sqlite_db(app)
    elif db_type == "postgresql":
        create_postgresql_db(app)
    else:
        raise ValueError("Unsupported db_type, use 'sqlite' or 'postgresql'")

    run_migrations(app, db_type, db)


__all__ = [
    "init_db",
    "create_postgresql_db",
    "create_sqlite_db",
    "run_migrations",
]
