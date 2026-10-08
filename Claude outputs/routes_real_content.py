"""Scenario Design — Fase 8: modify/delete content that has **already
been published** (piano tecnico §21 gap, resolved in decisions.md
§F8.5/§F8.6 after an explicit user decision -- there is no contract for
this in the piano tecnico, so this route's endpoint shape is this
plugin's own design, authorized before being implemented).

Two endpoints, deliberately the same destructive-operation shapes already
offered for drafts (``routes_threads.py``), applied to real, materialized
rows instead of ``sd_draft_post``:

* ``PUT/DELETE /experiments/<exp_id>/real_posts/<post_id>`` -- edit a
  real post's content/author, or delete a single real post (with no
  descendants check: deleting a post that has replies would leave
  orphaned real children, which is exactly what the subtree endpoint
  below exists to handle instead -- a lone-post delete here is refused
  if it has any descendant).
* ``POST /experiments/<exp_id>/real_posts/<post_id>/delete_subtree`` --
  recursive cascade-delete of a real post and every real descendant
  (piano tecnico §20 full-subtree policy, same as drafts).

Both blocked while ``exp.running`` (same ``experiment_running``/409
convention as ``adapters/*.py``'s publish path) since mutating
already-materialized rows out from under a live simulation run is the
same category of hazard publishing into one would be. Re-parenting
published content is out of scope (see ``real_content.py`` module
docstring) -- only ``content``/``author_user_id`` and deletion.
"""
from __future__ import annotations

from flask import jsonify, request

from .access import require_supported_experiment
from .real_content import RealContentError

API_PREFIX = "/admin/scenario_design/api"


def _error(code: str, message: str, http_status: int):
    return jsonify(ok=False, error={"code": code, "message": message}), http_status


def _ok(payload: dict, http_status: int = 200):
    return jsonify(ok=True, **payload), http_status


def register_routes(bp):
    """Attach the Fase 8 real-content routes to the suite blueprint
    ``bp`` -- called from ``__init__.py`` after every earlier phase's
    routes are registered on the same blueprint."""

    def _blocked_if_running(exp):
        if exp.running:
            return _error(
                "experiment_running",
                "Cannot modify real content while the experiment is running.",
                409,
            )
        return None

    def _requesting_user_id():
        from flask_login import current_user

        return current_user.id if current_user and current_user.is_authenticated else None

    @bp.route(
        f"{API_PREFIX}/experiments/<int:exp_id>/real_posts/<post_id>",
        methods=["PUT", "DELETE"],
    )
    def real_post_item(exp_id, post_id):
        from .real_content import get_real_post, real_thread_edges

        exp, error = require_supported_experiment(exp_id)
        if error is not None:
            return _error(error["code"], error["message"], 409)

        blocked = _blocked_if_running(exp)
        if blocked is not None:
            return blocked

        existing = get_real_post(exp, post_id)
        if existing is None:
            return _error("post_not_found", f"Real post {post_id!r} not found.", 404)
        post_pk, thread_id, _comment_to = existing

        if request.method == "DELETE":
            edges = real_thread_edges(exp, thread_id)
            has_descendants = any(
                parent == post_pk for child, parent in edges.items() if child != post_pk
            )
            if has_descendants:
                return _error(
                    "post_has_descendants",
                    (
                        f"Real post {post_id!r} has replies; use delete_subtree to remove "
                        "it together with its descendants."
                    ),
                    409,
                )

            from .audit import record_audit
            from .real_content import delete_real_post_subtree

            record_audit(
                exp_id=exp_id,
                action="real_post.delete",
                target_type="real_post",
                target_id=post_id,
                actor_user_id=_requesting_user_id(),
            )
            delete_real_post_subtree(exp, post_id)
            return _ok({"deleted": True})

        payload = request.get_json(silent=True) or {}

        from .sanitize import (
            MAX_POST_CONTENT_LENGTH,
            TextTooLongError,
            enforce_length,
            sanitize_free_text,
        )

        update_kwargs = {}
        try:
            if "content" in payload:
                update_kwargs["content"] = sanitize_free_text(
                    enforce_length(payload.get("content", ""), "content", MAX_POST_CONTENT_LENGTH)
                )
        except TextTooLongError as exc:
            return _error(exc.code, exc.message, 400)

        if "author_user_id" in payload:
            author_user_id = payload.get("author_user_id")
            from .access import author_exists

            if not author_exists(exp, author_user_id):
                return _error(
                    "author_not_found",
                    f"author_user_id {author_user_id!r} does not exist for this experiment.",
                    400,
                )
            update_kwargs["author_user_id"] = author_user_id

        from .audit import record_audit
        from .real_content import update_real_post

        result = update_real_post(exp, post_id, **update_kwargs)

        record_audit(
            exp_id=exp_id,
            action="real_post.update",
            target_type="real_post",
            target_id=post_id,
            actor_user_id=_requesting_user_id(),
        )
        return _ok({"post": result})

    @bp.route(
        f"{API_PREFIX}/experiments/<int:exp_id>/real_posts/<post_id>/delete_subtree",
        methods=["POST"],
    )
    def real_post_delete_subtree(exp_id, post_id):
        from .audit import record_audit
        from .real_content import delete_real_post_subtree, get_real_post

        exp, error = require_supported_experiment(exp_id)
        if error is not None:
            return _error(error["code"], error["message"], 409)

        blocked = _blocked_if_running(exp)
        if blocked is not None:
            return blocked

        if get_real_post(exp, post_id) is None:
            return _error("post_not_found", f"Real post {post_id!r} not found.", 404)

        try:
            deleted_count, deleted_ids = delete_real_post_subtree(exp, post_id)
        except RealContentError as exc:
            return _error(exc.code, exc.message, exc.http_status)

        record_audit(
            exp_id=exp_id,
            action="real_post.delete_subtree",
            target_type="real_post",
            target_id=post_id,
            actor_user_id=_requesting_user_id(),
            detail=f"deleted_count={deleted_count}",
        )
        return _ok({"deleted_count": deleted_count, "deleted_ids": [str(i) for i in deleted_ids]})
