"""Read-only access to an IM experiment database (plan, 4.4, 6.5, DEC-07).

The observer frontend never writes and never uses the YSocial ``db_exp`` bind. The database is opened with
``mode=ro`` and ``query_only``; when SQLite cannot open a live WAL file read-only (no ``-shm``, read-only
folder) a snapshot copy is made with the online backup API and cached by the mtime of the files.

The row models and ``visibility.can_read`` are the ones of the installed IM runtime, imported from its
repository folder: they are plain SQLAlchemy and Python and do not import Ray [E, checked in Phase 7].
"""

import hashlib
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
from contextlib import contextmanager
from typing import Iterator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

_snapshot_lock = threading.Lock()


class ImReadError(RuntimeError):
    """The IM database cannot be read (message is safe to show to the researcher)."""


class ImSchemaTooNew(ImReadError):
    """The database was written by a newer runtime than the installed one."""


def ensure_im_importable(repo_dir: Optional[str] = None) -> None:
    """Make ``yinstantmessaging`` importable (its repository folder goes on ``sys.path``)."""
    try:
        import yinstantmessaging  # noqa: F401

        return
    except ImportError:
        pass
    if repo_dir is None:
        from y_web.src.system.path_utils import get_external_repo_dir

        repo_dir = get_external_repo_dir("YInstantMessaging")
    if repo_dir and repo_dir not in sys.path:
        sys.path.insert(0, repo_dir)
    try:
        import yinstantmessaging  # noqa: F401
    except ImportError as exc:
        raise ImReadError("The instant messaging runtime is not installed.") from exc


def im_modules():
    """``(models, visibility, views, schema_migrations)`` of the installed runtime."""
    ensure_im_importable()
    from yinstantmessaging.server.db import models, schema_migrations
    from yinstantmessaging.server.services import views, visibility

    return models, visibility, views, schema_migrations


def _ro_url(path: str) -> str:
    return f"sqlite:///file:{path}?mode=ro&uri=true"


def _make_engine(path: str):
    engine = create_engine(_ro_url(path), future=True)

    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _query_only(dbapi_connection, _record):  # pragma: no cover - trivial
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA query_only=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    return engine


def snapshot_dir() -> str:
    return os.path.join(tempfile.gettempdir(), "yweb_im_snapshots")


def _signature(path: str) -> str:
    parts = []
    for suffix in ("", "-wal"):
        try:
            stat = os.stat(path + suffix)
        except OSError:
            parts.append("-")
            continue
        # an empty -wal appears when a reader opens the file: it is not a change of the data
        parts.append("-" if suffix and stat.st_size == 0 else f"{stat.st_mtime_ns}:{stat.st_size}")
    return "|".join(parts)


def snapshot_copy(path: str) -> str:
    """A consistent copy of the database made with the SQLite backup API, cached by file signature."""
    key = hashlib.sha1(os.path.abspath(path).encode()).hexdigest()[:16]
    folder = os.path.join(snapshot_dir(), key)
    target = os.path.join(folder, hashlib.sha1(_signature(path).encode()).hexdigest()[:16] + ".db")
    with _snapshot_lock:
        if os.path.isfile(target):
            return target
        shutil.rmtree(folder, ignore_errors=True)  # older signatures of this database
        os.makedirs(folder, exist_ok=True)
        tmp = target + ".part"
        try:
            src = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
        except sqlite3.Error:
            src = sqlite3.connect(path, timeout=5)  # a folder where even ro opening fails
        try:
            dst = sqlite3.connect(tmp)
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
        os.replace(tmp, target)
    return target


def check_schema(session: Session) -> int:
    """The schema version of the database; refuse a newer one than the installed runtime knows.

    Raises ``OperationalError`` when SQLite cannot read the file (the caller tries a snapshot copy).
    """
    *_rest, schema_migrations = im_modules()
    tables = {
        row[0]
        for row in session.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    }
    if not {"run_info", "schema_version"} <= tables:
        raise ImReadError("The database is not an instant messaging database.")
    found = session.execute(text("SELECT MAX(version) FROM schema_version")).scalar()
    if found is None:
        raise ImReadError("The database is not an instant messaging database.")
    if found > schema_migrations.LATEST_VERSION:
        raise ImSchemaTooNew(
            f"The database schema (version {found}) is newer than the installed runtime "
            f"(version {schema_migrations.LATEST_VERSION}); update the instant messaging runtime."
        )
    return int(found)


def _open(path: str):
    engine = _make_engine(path)
    session = Session(engine)
    try:
        check_schema(session)
    except BaseException:
        session.close()
        engine.dispose()
        raise
    return engine, session


@contextmanager
def open_reader(db_path: str) -> Iterator[Session]:
    """A read-only session on ``db_path`` (a snapshot copy when the live file cannot be opened read-only)."""
    if not os.path.isfile(db_path):
        raise ImReadError("The experiment database does not exist yet.")
    try:
        engine, session = _open(db_path)
    except OperationalError:
        try:
            engine, session = _open(snapshot_copy(db_path))
        except (sqlite3.Error, OperationalError) as exc:
            raise ImReadError("The experiment database cannot be read right now.") from exc
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
