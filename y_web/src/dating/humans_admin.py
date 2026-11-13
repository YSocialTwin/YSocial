"""What the researcher sees about human participation in a dating run (IR-D-22, IR-D-31).

The list is built from the YWeb users assigned to the experiment (roles user and student, the only ones
who can take part) and, for the accounts that already exist, from the run database read with ``mode=ro``.
A run with people is not reproducible: the page says so.
"""

import os
from typing import Any, Dict, List

from sqlalchemy import select

from y_web import db
from y_web.src.dating import human
from y_web.src.dating.gateway import gateway_status, human_config, human_enabled
from y_web.src.dating.reader import DatingReadError, open_reader
from y_web.src.models import Admin_users, User_Experiment


def _assigned_users(exp) -> List[Admin_users]:
    return list(
        db.session.execute(
            select(Admin_users)
            .join(User_Experiment, User_Experiment.user_id == Admin_users.id)
            .where(
                User_Experiment.exp_id == exp.idexp,
                Admin_users.role.in_(human.PARTICIPANT_ROLES),
            )
            .order_by(Admin_users.username)
        )
        .scalars()
        .all()
    )


def _stats(conn, account_id: str) -> Dict[str, Any]:
    row = conn.execute(
        "SELECT status, left_reason FROM user_mgmt WHERE id = ? AND user_type = 'human'",
        (account_id,),
    ).fetchone()
    if row is None:
        return {"created": False}
    one = lambda sql: conn.execute(sql, (account_id,)).fetchone()[0]  # noqa: E731
    return {
        "created": True,
        "status": row["status"],
        "left_reason": row["left_reason"],
        "swipes": one("SELECT COUNT(*) FROM swipes WHERE swiper_id = ?"),
        "matches": conn.execute(
            "SELECT COUNT(*) FROM matches WHERE user_a = ? OR user_b = ?",
            (account_id, account_id),
        ).fetchone()[0],
        "messages": one("SELECT COUNT(*) FROM messages WHERE sender_id = ?"),
        "reports": one("SELECT COUNT(*) FROM reports WHERE from_id = ?"),
    }


def humans_overview(exp) -> Dict[str, Any]:
    folder = human.experiment_folder(exp)
    if not human_enabled(folder):
        return {
            "enabled": False,
            "config": {},
            "gateway": {"status": "off"},
            "humans": [],
        }
    uid = human.experiment_uid(exp)
    rows = [
        {
            "user": u.username,
            "account_id": human.human_account_id(uid, u.id),
            "created": False,
        }
        for u in _assigned_users(exp)
    ]
    db_path = os.path.join(folder, "database_server.db")
    if os.path.isfile(db_path):
        try:
            with open_reader(db_path) as reader:
                for row in rows:
                    row.update(_stats(reader.c, row["account_id"]))
        except DatingReadError:
            pass
    return {
        "enabled": True,
        "config": human_config(folder),
        "gateway": gateway_status(folder),
        "humans": rows,
    }
