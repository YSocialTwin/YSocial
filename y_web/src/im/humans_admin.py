"""What the researcher sees about human participation (plan 5.8): gateway status and the humans of a run."""

import os
from typing import Any, Dict, List

from sqlalchemy import func, select

from y_web import db
from y_web.src.im.engine import ImReadError, im_modules, open_reader
from y_web.src.im.gateway_process import gateway_status, human_config, human_enabled
from y_web.src.im.human_identity import experiment_uid, human_account_id
from y_web.src.models import Admin_users, User_Experiment
from y_web.src.im.participant import experiment_folder


def humans_overview(exp) -> Dict[str, Any]:
    """``{"enabled", "config", "gateway", "humans"}``; ``None``-safe for experiments without humans."""
    folder = experiment_folder(exp)
    if not human_enabled(folder):
        return {"enabled": False, "humans": [], "gateway": {"status": "off"}, "config": {}}
    uid = experiment_uid(exp)
    assigned = db.session.execute(
        select(Admin_users)
        .join(User_Experiment, User_Experiment.user_id == Admin_users.id)
        .where(User_Experiment.exp_id == exp.idexp, Admin_users.role.in_(("user", "student")))
        .order_by(Admin_users.username)
    ).scalars().all()
    rows: List[Dict[str, Any]] = [
        {
            "user": u.username,
            "account_id": human_account_id(uid, u.id),
            "created": False,
            "messages": 0,
            "last_round": None,
        }
        for u in assigned
    ]
    db_path = os.path.join(folder, "database_server.db")
    if os.path.isfile(db_path):
        try:
            models = im_modules()[0]
            with open_reader(db_path) as session:
                for row in rows:
                    if session.get(models.Account, row["account_id"]) is None:
                        continue
                    row["created"] = True
                    row["messages"] = int(
                        session.scalar(
                            select(func.count())
                            .select_from(models.Message)
                            .where(models.Message.sender_account_id == row["account_id"])
                        )
                        or 0
                    )
                    row["last_round"] = session.scalar(
                        select(func.max(models.Message.round_id)).where(
                            models.Message.sender_account_id == row["account_id"]
                        )
                    )
        except ImReadError:
            pass
    return {
        "enabled": True,
        "config": human_config(folder),
        "gateway": gateway_status(folder),
        "humans": rows,
    }
