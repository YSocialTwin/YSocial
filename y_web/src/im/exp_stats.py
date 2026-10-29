"""``Exp_stats`` for instant messaging experiments.

The other platforms fill ``Exp_stats`` (rounds, agents, posts, reactions, mentions) from their client logs. IM
keeps everything in its own run database, so the counts are read from there, read-only, and written to the same
row so that pages and helpers that look at ``Exp_stats`` see an IM experiment as having data once it has some.
"""

import os
from typing import Dict

from sqlalchemy import func, select

from y_web import db
from y_web.src.im.engine import ImReadError, im_modules, open_reader
from y_web.src.im.participant import experiment_folder
from y_web.src.models import Exp_stats

FIELDS = ("rounds", "agents", "posts", "reactions", "mentions")


def count_run(db_path: str) -> Dict[str, int]:
    """Counts of an IM run database (zeros when it does not exist yet or cannot be read)."""
    zero = {f: 0 for f in FIELDS}
    if not os.path.isfile(db_path):
        return zero
    m = im_modules()[0]
    try:
        with open_reader(db_path) as s:

            def n(col, *where):
                q = select(func.count()).select_from(col)
                return int(s.scalar(q.where(*where) if where else q) or 0)

            return {
                "rounds": int(s.scalar(select(func.max(m.Round.id))) or 0),
                "agents": n(m.Account, m.Account.kind == "agent"),
                "posts": n(m.Message),
                "reactions": n(m.Reaction),
                "mentions": n(m.Mention),
            }
    except ImReadError:
        return zero


def refresh_exp_stats(exp) -> Dict[str, int]:
    """Recompute the counts of an IM experiment and store them in its ``Exp_stats`` row (created when missing)."""
    counts = count_run(os.path.join(experiment_folder(exp), "database_server.db"))
    row = db.session.scalars(select(Exp_stats).filter_by(exp_id=exp.idexp)).first()
    if row is None:
        row = Exp_stats(exp_id=exp.idexp)
        db.session.add(row)
    for field, value in counts.items():
        setattr(row, field, value)
    db.session.commit()
    return counts
