"""Modify/delete content that has **already been published** (piano di
implementazione, Fase 8: "operare in due modalità equivalenti: su righe
di bozza e su righe reali già presenti nel db_exp").

Scope deliberately narrower than the draft editor (``routes_threads.py``):
this module only supports editing a real post's ``content``/author, and
recursive subtree deletion -- the same two destructive-operation shapes
already offered for drafts, applied to already-materialized rows. It does
**not** support re-parenting a published post (changing its place in the
thread graph): unlike a draft, a published post's ``thread_id``/
``comment_to`` may already be referenced by other systems (analytics,
exports, a running simulation's own memory of what it posted) built on
the assumption that published structure is stable once written --
re-parenting live content is a materially bigger risk than fixing a typo
or removing a post, and was not asked for; narrowing scope here rather
than guessing at it is the explicit, documented choice (decisions.md
§F8.5/§F8.6).

Family-aware throughout (Standard: the already-active ``db_exp`` bind's
core models; HPC: ``hpc_session.py``'s independent session and
YSimulator's own models, same split as the rest of this plugin since
Fase 7) -- never a bare ``if hpc`` scattered through route code.
"""
from __future__ import annotations


class RealContentError(Exception):
    """Raised with a machine-readable ``code`` (piano tecnico §15 uniform
    error envelope), same convention as every other error type in this
    plugin."""

    def __init__(self, code: str, message: str, http_status: int = 404):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


# (model_name, foreign_key_column_name) for every satellite table that can
# reference a post, for each family -- verified by reading both schemas
# directly (y_web/src/models/experiment.py and
# external/YSimulator/YSimulator/YServer/classes/models.py), not assumed
# to be structurally identical just because the column names happen to
# match closely.
_STANDARD_SATELLITES = [
    ("Post_emotions", "post_id"),
    ("Post_hashtags", "post_id"),
    ("Mentions", "post_id"),
    ("Reactions", "post_id"),
    ("Reported", "to_post"),
    ("Post_topics", "post_id"),
    ("Post_Sentiment", "post_id"),
    ("Post_Toxicity", "post_id"),
    ("Agent_Opinion", "id_post"),
]
_HPC_SATELLITES = [
    ("PostEmotion", "post_id"),
    ("PostHashtag", "post_id"),
    ("Mention", "post_id"),
    ("Reaction", "post_id"),
    ("Reported", "to_post"),
    ("PostTopic", "post_id"),
    ("PostSentiment", "post_id"),
    ("PostToxicity", "post_id"),
    ("Agent_Opinion", "id_post"),
]


def _is_hpc(exp) -> bool:
    return (getattr(exp, "simulator_type", None) or "Standard") != "Standard"


def _standard_post_model():
    from y_web.src.models import Post

    return Post


def _hpc_post_model():
    from YSimulator.YServer.classes.models import Post as HpcPost

    return HpcPost


def get_real_post(exp, post_id):
    """Return the real ``Post`` row (core ORM for Standard, YSimulator's
    own model for HPC) for *post_id*, or ``None``. Opens its own
    short-lived session for HPC -- callers that need to then mutate it
    use ``with_real_session`` instead."""
    if _is_hpc(exp):
        from .hpc_session import hpc_session

        with hpc_session(exp) as session:
            post = session.get(_hpc_post_model(), str(post_id))
            if post is None:
                return None
            return post.id, post.thread_id, post.comment_to

    from y_web import db

    post = db.session.get(_standard_post_model(), post_id)
    if post is None:
        return None
    return post.id, post.thread_id, post.comment_to


def real_thread_edges(exp, thread_id) -> dict:
    """Return ``{post_id: comment_to}`` for every real post sharing
    *thread_id* -- the same shape ``compute_descendants`` expects, built
    from already-materialized data instead of ``sd_draft_post`` rows."""
    if _is_hpc(exp):
        from .hpc_session import hpc_session

        HpcPost = _hpc_post_model()
        with hpc_session(exp) as session:
            rows = session.query(HpcPost.id, HpcPost.comment_to).filter(
                HpcPost.thread_id == thread_id
            ).all()
            return {row[0]: row[1] for row in rows}

    from y_web import db

    Post = _standard_post_model()
    rows = (
        db.session.query(Post.id, Post.comment_to).filter(Post.thread_id == thread_id).all()
    )
    return {row[0]: row[1] for row in rows}


def update_real_post(exp, post_id, *, content=None, author_user_id=None) -> dict:
    """Update ``content``/``user_id`` on an already-published post.
    Raises ``RealContentError`` (``post_not_found``) if it does not
    exist. Caller is responsible for author existence validation
    (``access.author_exists``) and sanitization/length limits
    (``sanitize.py``) before calling this -- this function only writes
    whatever it is given."""
    if _is_hpc(exp):
        from .hpc_session import hpc_session

        HpcPost = _hpc_post_model()
        with hpc_session(exp) as session:
            post = session.get(HpcPost, str(post_id))
            if post is None:
                raise RealContentError("post_not_found", f"Real post {post_id!r} not found.")
            if content is not None:
                post.tweet = content
            if author_user_id is not None:
                post.user_id = str(author_user_id)
            session.commit()
            return {"id": post.id, "content": post.tweet, "author_user_id": post.user_id}

    from y_web import db

    Post = _standard_post_model()
    post = db.session.get(Post, post_id)
    if post is None:
        raise RealContentError("post_not_found", f"Real post {post_id!r} not found.")
    if content is not None:
        post.tweet = content
    if author_user_id is not None:
        post.user_id = author_user_id
    db.session.commit()
    return {"id": post.id, "content": post.tweet, "author_user_id": post.user_id}


def delete_real_post_subtree(exp, post_id):
    """Recursively delete *post_id* and every real descendant (piano
    tecnico §20: full-subtree policy, same as drafts), cascading across
    every satellite table that references a deleted post, within one
    transaction. Returns ``(deleted_count, deleted_ids)``. Raises
    ``RealContentError`` (``post_not_found``) if *post_id* does not
    exist."""
    from .thread_invariants import compute_descendants

    if _is_hpc(exp):
        from .hpc_session import hpc_session

        HpcPost = _hpc_post_model()
        with hpc_session(exp) as session:
            post = session.get(HpcPost, str(post_id))
            if post is None:
                raise RealContentError("post_not_found", f"Real post {post_id!r} not found.")

            edges = {
                row[0]: row[1]
                for row in session.query(HpcPost.id, HpcPost.comment_to)
                .filter(HpcPost.thread_id == post.thread_id)
                .all()
            }
            descendants = compute_descendants(edges, str(post_id))

            import YSimulator.YServer.classes.models as hpc_models

            for model_name, fk_column in _HPC_SATELLITES:
                model_cls = getattr(hpc_models, model_name)
                column = getattr(model_cls, fk_column)
                session.query(model_cls).filter(column.in_(descendants)).delete(
                    synchronize_session=False
                )
            session.query(HpcPost).filter(HpcPost.id.in_(descendants)).delete(
                synchronize_session=False
            )
            session.commit()
            return len(descendants), sorted(descendants)

    from y_web import db
    import y_web.src.models as core_models

    Post = _standard_post_model()
    post = db.session.get(Post, post_id)
    if post is None:
        raise RealContentError("post_not_found", f"Real post {post_id!r} not found.")

    edges = {
        row[0]: row[1]
        for row in db.session.query(Post.id, Post.comment_to)
        .filter(Post.thread_id == post.thread_id)
        .all()
    }
    descendants = compute_descendants(edges, post_id)

    for model_name, fk_column in _STANDARD_SATELLITES:
        model_cls = getattr(core_models, model_name)
        column = getattr(model_cls, fk_column)
        db.session.query(model_cls).filter(column.in_(descendants)).delete(
            synchronize_session=False
        )
    db.session.query(Post).filter(Post.id.in_(descendants)).delete(synchronize_session=False)
    db.session.commit()
    return len(descendants), sorted(descendants)
