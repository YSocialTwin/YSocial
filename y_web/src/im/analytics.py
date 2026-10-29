"""What the YSocial analytics pages need to run on an instant messaging experiment (plan 4.7, 5.7).

The pages resolve one database per experiment; for IM it is the derived ``analytics_im.db`` built by
``analytics_etl``. IM's own database is only read, and only through ``engine.open_reader``.
"""

import os
from typing import Any, Dict, Optional

from y_web.src.im import analytics_etl as etl

#: annotation switches that the pages look for in ``Exps.annotations`` and the derived table proving them
_ANNOTATION_TABLES = {
    "opinions": "agent_opinion",
    "sentiment": "post_sentiment",
    "emotion": "post_emotions",
    "toxicity": "post_toxicity",
}


def experiment_folder(exp) -> str:
    from y_web.src.system.path_utils import get_writable_path

    parts = str(exp.db_name).replace("\\", "/").split("/")
    return os.path.join(get_writable_path(), "y_web", "experiments", parts[1])


def source_path(exp) -> str:
    return os.path.join(experiment_folder(exp), "database_server.db")


def derived_db_name(exp) -> str:
    """Relative name in the form the YSocial helpers use (``experiments/<uid>/analytics_im.db``)."""
    parts = str(exp.db_name).replace("\\", "/").split("/")
    return f"experiments/{parts[1]}/{etl.ANALYTICS_FILE}"


def is_derived_db_name(db_name) -> bool:
    return (
        str(db_name or "").replace("\\", "/").rsplit("/", 1)[-1] == etl.ANALYTICS_FILE
    )


def ensure_derived(exp, force: bool = False) -> Dict[str, Any]:
    """Bring the derived database up to date (cheap when the source has not changed) and sync the annotation flags."""
    result = etl.refresh(experiment_folder(exp), source_path(exp), force=force)
    if result.get("rebuilt"):
        _sync_annotations(exp, result.get("counts") or {})
    return result


def _sync_annotations(exp, counts: Dict[str, int]) -> None:
    """Make ``Exps.annotations`` list what the derived database holds, so the opinion page's own check passes."""
    try:
        from y_web import db

        present = {
            tok for tok, table in _ANNOTATION_TABLES.items() if counts.get(table)
        }
        current = [t for t in (exp.annotations or "").split(",") if t]
        missing = [t for t in sorted(present) if t not in current]
        if missing:
            exp.annotations = ",".join(current + missing)
            db.session.commit()
    except Exception:
        try:
            from y_web import db

            db.session.rollback()
        except Exception:
            pass


def state(exp) -> Dict[str, Any]:
    return etl.read_state(experiment_folder(exp))


def derived_tables(exp) -> set:
    import sqlite3

    path = os.path.join(experiment_folder(exp), etl.ANALYTICS_FILE)
    if not os.path.isfile(path):
        return set()
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
            return {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
    except sqlite3.Error:
        return set()


def cards(exp) -> Dict[str, Any]:
    """Which analytics cards the details page offers: the same table-presence rule the pages use."""
    tables = derived_tables(exp)
    return {
        "toxicity": {"post_toxicity", "post", "rounds"} <= tables,
        "sentiment": {"post_sentiment", "rounds"} <= tables,
        "emotion": {"post_emotions", "emotions", "post", "rounds"} <= tables,
        "stress_reward": {"stress_reward", "rounds"} <= tables,
        "recsys": "recommendations" in tables,
        "state": state(exp),
    }


def annotation_problem(exp, prefix: str) -> str:
    """Why an annotation page has no data: the error the annotator reported in IM's database (empty when none).

    Annotator errors (a missing library, an unreachable model) are stored on the annotation rows, not shown anywhere
    else; the first distinct message of the method family is returned.
    """
    import json
    import sqlite3

    path = source_path(exp)
    if not os.path.isfile(path):
        return ""
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
            rows = conn.execute(
                "SELECT value FROM annotations WHERE status = 'error' AND method_ref LIKE ? LIMIT 20",
                (prefix + "%",),
            ).fetchall()
    except sqlite3.Error:
        return ""
    for (raw,) in rows:
        try:
            message = json.loads(raw).get("error")
        except (TypeError, ValueError, AttributeError):
            message = None
        if message:
            return str(message)
    return ""
