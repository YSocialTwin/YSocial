"""Fixed-order content recommenders: an experiment author lists the posts of the feed and their order.

The definition lives in the experiment database (written by ScenarioDesign when the scenario is published):

``fixed_recsys_order(recsys_name TEXT, position INTEGER, post_id TEXT)``

A participant uses it when its ``recsys_type`` is ``fixed:<name>``. The feed shows ONLY the posts listed under that
name, in ``position`` order; every other post is hidden. Ids are stored as text so the table serves both integer
(Standard) and UUID (HPC) post ids.
"""

from sqlalchemy import Integer, text

from y_web.sdk.models import Post, db

FIXED_PREFIX = "fixed:"
TABLE = "fixed_recsys_order"


def is_fixed_mode(mode):
    """Whether a stored/UI value names a fixed-order recommender (``fixed:`` plus a non-empty name)."""
    return (
        isinstance(mode, str)
        and mode.strip().lower().startswith(FIXED_PREFIX)
        and bool(mode.strip()[len(FIXED_PREFIX):].strip())
    )


def fixed_name(mode):
    """The recommender name of a ``fixed:<name>`` value (case and spaces inside the name are kept)."""
    return mode.strip()[len(FIXED_PREFIX):].strip()


def canonical(mode):
    """The canonical spelling ``fixed:<name>`` of a fixed mode value."""
    return FIXED_PREFIX + fixed_name(mode)


def fixed_recsys_names():
    """Names of the fixed recommenders defined in the current experiment database (empty when there are none)."""
    try:
        rows = db.session.execute(
            text(f"SELECT DISTINCT recsys_name FROM {TABLE} ORDER BY recsys_name")
        ).all()
    except Exception:
        db.session.rollback()
        return []
    return [r[0] for r in rows]


def ordered_post_ids(name):
    """Ids (as stored, text) of the posts of the fixed recommender ``name``, in display order."""
    try:
        rows = db.session.execute(
            text(f"SELECT post_id FROM {TABLE} WHERE recsys_name = :n ORDER BY position"),
            {"n": name},
        ).all()
    except Exception:
        db.session.rollback()
        return []
    return [str(r[0]) for r in rows]


def _coerce_ids(ids):
    """Convert text ids to the type of the post primary key (integer for Standard, string for HPC)."""
    if isinstance(Post.id.type, Integer):
        out = []
        for i in ids:
            try:
                out.append(int(i))
            except (TypeError, ValueError):
                continue
        return out
    return list(ids)


def fixed_posts(mode, page, per_page, make_pagination):
    """One page of the fixed feed of ``mode`` (``fixed:<name>``): the listed root posts only, in the author's order."""
    ids = _coerce_ids(ordered_post_ids(fixed_name(mode)))
    found = {}
    if ids:
        for p in Post.query.filter(Post.id.in_(ids)).all():
            if p.comment_to in (None, -1):
                found[p.id] = p
    ranked = [found[i] for i in ids if i in found]
    page = max(1, page)
    start = (page - 1) * per_page
    return make_pagination(ranked[start:start + per_page], page, per_page, len(ranked))
