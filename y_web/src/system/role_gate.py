"""Deny-by-default gate for the ``teacher`` role.

A teacher is an ``Admin_users`` account that works only inside the Training Modules area (see the plugin's
``access.py``). Most pages of the administration check the role by calling ``check_privileges`` and several of them
discard its answer, so a role that is not admin or researcher cannot be kept out of them page by page. This gate
closes everything for a teacher except what is listed here, before any view runs:

* the plugin's own pages and APIs (``/admin/training``), whose routes enforce what a teacher may do;
* the participant pages of a module rehearsal (``/training``);
* static files, the login and logout pages;
* an experiment (any URL that carries ``exp_id``, and the few feed pages that carry none) only while a plugin
  hook (``staff_experiment_access``) says this session is rehearsing a module that uses that experiment.

Nothing here grants anything to a role other than ``teacher``.
"""

from __future__ import annotations

from flask import abort, redirect, request, session
from flask_login import current_user

TEACHER_ROLE = "teacher"
HOME = "/admin/training/modules"

OPEN_PREFIXES = ("/static/", "/plugins/", "/uploads/", "/admin/training", "/training")
OPEN_PATHS = ("/login", "/logout")
# pages of an experiment that carry no exp_id: they follow the session's current experiment
REHEARSAL_PATHS = ("/feed", "/rfeed", "/photo/feed", "/rnotifications", "/profile")


def is_teacher(user=None) -> bool:
    user = user if user is not None else current_user
    return bool(getattr(user, "is_authenticated", False)) and getattr(user, "role", None) == TEACHER_ROLE


def _rehearsing(exp_id) -> bool:
    from y_web.src.external_runtime.plugin_hooks import call_first_non_null

    if exp_id is None and session.get("tm_preview_run") is None:
        return False
    return call_first_non_null("staff_experiment_access", current_user, exp_id) is True


def teacher_gate():
    """``before_request`` handler: ``None`` to go on, otherwise the response that closes the request."""
    if not is_teacher():
        return None
    path = request.path
    if path in OPEN_PATHS or path.startswith(OPEN_PREFIXES):
        return None
    exp_id = (request.view_args or {}).get("exp_id")
    if exp_id is not None or path in REHEARSAL_PATHS:
        if _rehearsing(exp_id if isinstance(exp_id, int) else None):
            return None
    if request.method == "GET" and "text/html" in request.accept_mimetypes:
        return redirect(HOME)
    abort(403)
