from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from flask import current_app
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from y_web import db
from y_web.src.experiment.schema import ensure_experiment_schema_for_uri
from y_web.src.models import Exps, User_mgmt

BASE_DIR = Path(__file__).resolve().parents[1]


def get_experiment_uid_from_db_name(db_name: str) -> Optional[str]:
    """
    Extract the experiment UID (folder name) from the db_name field.
    """
    if not db_name:
        return None

    if db_name.startswith("experiments_"):
        return db_name.replace("experiments_", "")
    if db_name.startswith("experiments/") or db_name.startswith("experiments\\"):
        parts = re.split(r"[/\\\\]", db_name)
        if len(parts) >= 2:
            return parts[1]
    return None


@dataclass
class SimulationClock:
    day: int
    hour: int
    is_running: bool
    source: str

    @property
    def hour_str(self) -> str:
        return f"{self.hour:02d}"

    @property
    def label(self) -> str:
        return f"Day {self.day} · {self.hour_str}:00"

    @property
    def status_text(self) -> str:
        return "Running" if self.is_running else "Stopped"

    @property
    def status_class(self) -> str:
        return "is-success" if self.is_running else "is-danger"

    def to_dict(self) -> Dict[str, object]:
        return {
            "day": self.day,
            "hour": self.hour,
            "hour_str": self.hour_str,
            "label": self.label,
            "status_text": self.status_text,
            "status_class": self.status_class,
            "is_running": self.is_running,
            "source": self.source,
        }


def get_experiment_dir(experiment: Exps) -> Path:
    """
    Locate the on-disk directory that stores experiment artifacts.
    """
    db_name = experiment.db_name.replace("\\", os.sep)

    if os.sep in db_name:
        relative = Path(db_name).parent
        return BASE_DIR / relative

    folder = db_name.removeprefix("experiments_")
    return BASE_DIR / "experiments" / folder


def _experiment_engine_uri(experiment: Exps) -> Optional[str]:
    """
    Build a SQLAlchemy engine URI pointing at the experiment database.
    Returns None if the backend is unsupported.
    """
    base_uri = current_app.config["SQLALCHEMY_DATABASE_URI"]

    if base_uri.startswith("sqlite"):
        db_path = (BASE_DIR / experiment.db_name).resolve()
        return f"sqlite:///{db_path}"

    if base_uri.startswith("postgresql"):
        prefix, _ = base_uri.rsplit("/", 1)
        return f"{prefix}/{experiment.db_name}"

    return None


def get_experiment_engine_uri(experiment: Exps) -> Optional[str]:
    """
    Public wrapper returning the database URI for an experiment.
    """
    return _experiment_engine_uri(experiment)


def open_experiment_session(experiment: Exps):
    """
    Open an isolated SQLAlchemy session bound to the experiment database.

    This avoids mutating Flask-SQLAlchemy's global bind map and guarantees the
    schema exists before callers issue ORM queries or inserts.
    """
    uri = _experiment_engine_uri(experiment)
    if not uri:
        return None, None

    ensure_experiment_schema_for_uri(uri)
    engine = create_engine(uri, pool_pre_ping=True)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    return session, engine


def ensure_experiment_user(
    experiment: Exps,
    *,
    user_id,
    username: str,
    email: str,
    password: str,
    cover_image: str = "",
    user_type: str = "user",
    leaning: str = "neutral",
    age: int = 0,
    recsys_type: str = "default",
    frecsys_type: str = "default",
    language: str = "en",
    round_actions: int = 1,
    toxicity: str = "no",
    joined_on: int = 0,
):
    """
    Ensure a participant row exists in the experiment database.

    Returns a tuple ``(user, created)`` where ``user`` is the ORM instance
    loaded from the experiment database session.
    """
    session, engine = open_experiment_session(experiment)
    if session is None or engine is None:
        return None, False

    try:
        user = session.query(User_mgmt).filter_by(username=username).first()
        if user is not None:
            return user, False

        new_user = User_mgmt(
            id=user_id,
            email=email,
            username=username,
            password=password,
            user_type=user_type,
            leaning=leaning,
            age=age,
            recsys_type=recsys_type,
            language=language,
            frecsys_type=frecsys_type,
            round_actions=round_actions,
            toxicity=toxicity,
            joined_on=joined_on,
            cover_image=cover_image,
        )
        session.add(new_user)
        session.commit()
        session.refresh(new_user)
        return new_user, True
    finally:
        session.close()
        engine.dispose()


def _fetch_round_from_engine(engine: Engine) -> Optional[Dict[str, int]]:
    stmt = text("SELECT id, day, hour FROM rounds ORDER BY id DESC LIMIT 1")
    with engine.connect() as conn:
        row = conn.execute(stmt).mappings().first()
        if row is None:
            return None
        return {"id": int(row["id"]), "day": int(row["day"]), "hour": int(row["hour"])}


def _fetch_round_by_id(engine: Engine, round_id: int) -> Optional[Dict[str, int]]:
    stmt = text("SELECT id, day, hour FROM rounds WHERE id = :rid LIMIT 1")
    with engine.connect() as conn:
        row = conn.execute(stmt, {"rid": round_id}).mappings().first()
        if row is None:
            return None
        return {"id": int(row["id"]), "day": int(row["day"]), "hour": int(row["hour"])}


def _fetch_latest_post_round(engine: Engine) -> Optional[int]:
    stmt = text("SELECT MAX(round) AS max_round FROM post")
    with engine.connect() as conn:
        row = conn.execute(stmt).mappings().first()
        if row is None or row["max_round"] is None:
            return None
        return int(row["max_round"])


def _bind_engine_for_experiment(experiment: Exps) -> tuple[Optional[Engine], bool]:
    """
    Return an engine pointing at the experiment database.
    Tuple = (engine, should_dispose_engine)
    """
    if experiment.status == 1:
        try:
            engine = db.get_engine(bind="db_exp")
            bind_uri = current_app.config["SQLALCHEMY_BINDS"].get("db_exp")
            target_uri = _experiment_engine_uri(experiment)
            if bind_uri and target_uri and bind_uri == target_uri:
                return engine, False
        except Exception:
            pass

    uri = _experiment_engine_uri(experiment)
    if not uri:
        return None, False

    return create_engine(uri), True


def fetch_simulation_clock(experiment: Exps) -> Dict[str, object]:
    """
    Retrieve the last recorded round (day/hour) for the given experiment.
    """
    default = SimulationClock(
        day=0, hour=0, is_running=bool(experiment.running), source="none"
    )

    engine, dispose_engine = _bind_engine_for_experiment(experiment)
    engine_source: Optional[str] = None
    if engine is not None and not dispose_engine and experiment.status == 1:
        engine_source = "db_exp"

    latest_round = None
    if engine is not None:
        try:
            latest_round = _fetch_round_from_engine(engine)
            latest_post_round_id = _fetch_latest_post_round(engine)
            if latest_post_round_id:
                post_round = _fetch_round_by_id(engine, latest_post_round_id)
                if post_round and (
                    latest_round is None or post_round["id"] > latest_round["id"]
                ):
                    latest_round = post_round
        except SQLAlchemyError:
            latest_round = None
        finally:
            if dispose_engine and engine is not None:
                engine.dispose()

    if latest_round is None and experiment.status == 1:
        uri = _experiment_engine_uri(experiment)
        if uri:
            engine = None
            try:
                engine = create_engine(uri)
                latest_round = _fetch_round_from_engine(engine)
                latest_post_round_id = _fetch_latest_post_round(engine)
                if latest_post_round_id:
                    post_round = _fetch_round_by_id(engine, latest_post_round_id)
                    if post_round and (
                        latest_round is None or post_round["id"] > latest_round["id"]
                    ):
                        latest_round = post_round
                engine_source = uri
            except SQLAlchemyError:
                latest_round = None
            finally:
                if engine is not None:
                    engine.dispose()

    if not latest_round:
        return default.to_dict()

    clock = SimulationClock(
        day=latest_round["day"],
        hour=latest_round["hour"],
        is_running=bool(experiment.running),
        source=engine_source or _experiment_engine_uri(experiment) or "unknown",
    )
    return clock.to_dict()


def active_simulation_clock() -> Optional[Dict[str, object]]:
    """
    Helper to fetch the clock for the currently active experiment, if any.
    """
    active = Exps.query.filter_by(status=1).first()
    if not active:
        return None
    return fetch_simulation_clock(active)
