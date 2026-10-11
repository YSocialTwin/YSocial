"""Generic, opt-in extension hooks that backend plugin suites can declare.

A suite declares hooks in ``meta/registry.json``::

    "hooks": {"post_login": "dotted.module:callable", ...}

(validated by :func:`backend_plugins.validate_backend_suite`). The core calls
them at well-defined points through the helpers below. Contract for every hook:

* hooks are optional: with no suite declaring one, the core flow is unchanged;
* exceptions raised by a hook are logged and swallowed, never interrupting the
  core flow;
* the first hook (in registry order) returning a non-``None`` value wins for
  hooks that return a decision (:func:`call_first_non_null`); event-style hooks
  are broadcast to every declaring suite (:func:`emit_hook`).

Supported hook names:

``post_login(admin_user) -> redirect_url | None``
    Called for participant roles right after the password check, before the
    experiment selection. A returned local URL (starting with ``/``) replaces
    the default flow.
``experiment_access_guard(account_id, exp_id) -> None | redirect``
    See :func:`y_web.src.experiment.context.setup_experiment_context`.
``staff_experiment_access(user, exp_id) -> True | None``
    Asked when a staff session that may not view an experiment tries to enter it (``/admin/join_experiment``), and by
    the teacher gate (:mod:`y_web.src.system.role_gate`) for every experiment URL. ``True`` lets the session in;
    ``None`` leaves the decision to the core. ``exp_id`` is ``None`` for the feed pages that carry no experiment id.
``experiment_user_provisioned(exp, account_id, exp_user_id, created) -> None``
    Event emitted by ``ensure_experiment_user``.

``experiment_page_widget(account_id, exp_id) -> html | None``
    Called while a microblogging page of an experiment is rendered for a participant session. A returned string
    (trusted HTML, so the plugin must escape everything it did not write) is placed at the end of the page header,
    for example a floating button. See :func:`experiment_page_widgets`.

Never raises to the caller.
"""

from __future__ import annotations

import logging

from y_web.src.external_runtime import backend_plugins

logger = logging.getLogger(__name__)


def iter_hooks(name: str):
    """Yield ``(repo_key, callable)`` for every valid suite declaring hook *name*."""
    for repo_key in backend_plugins.backend_plugin_repo_keys():
        try:
            report = backend_plugins.validate_backend_suite(repo_key)
            ref = (report.get("hooks") or {}).get(name)
            if not (report.get("valid") and ref):
                continue
            if not backend_plugins.plugin_enabled(repo_key):
                continue  # disabled suites receive no hook calls
            dotted, _, attr = ref.partition(":")
            yield repo_key, getattr(
                backend_plugins._import_from_suite(repo_key, dotted), attr
            )
        except Exception as exc:  # broken suite must not break the core flow
            logger.warning("plugin hook '%s' of '%s' unavailable: %s", name, repo_key, exc)


def call_first_non_null(name: str, *args, **kwargs):
    """Return the first non-``None`` result of the declared hooks, else ``None``."""
    for repo_key, hook in iter_hooks(name):
        try:
            result = hook(*args, **kwargs)
        except Exception as exc:
            logger.warning("plugin hook '%s' of '%s' raised: %s", name, repo_key, exc)
            continue
        if result is not None:
            return result
    return None


def emit_hook(name: str, *args, **kwargs) -> None:
    """Broadcast an event to every declaring suite (best effort)."""
    for repo_key, hook in iter_hooks(name):
        try:
            hook(*args, **kwargs)
        except Exception as exc:
            logger.warning("plugin hook '%s' of '%s' raised: %s", name, repo_key, exc)


def is_local_redirect(url) -> bool:
    """Only same-site absolute paths are accepted as hook redirect targets."""
    return (
        isinstance(url, str)
        and url.startswith("/")
        and not url.startswith("//")
        and "\\" not in url
    )


def experiment_page_widgets(exp_id) -> str:
    """HTML added by the ``experiment_page_widget`` hooks to an experiment page (``""`` for anyone but a participant).

    Only sessions carrying ``platform_account_id`` (participants entered through the login flow) get widgets; every
    suite declaring the hook contributes, in registry order. A hook that fails or returns something else than a
    string contributes nothing.
    """
    from flask import session

    account_id = session.get("platform_account_id")
    try:
        exp_id = int(exp_id)
    except (TypeError, ValueError):
        return ""
    if account_id is None:
        return ""
    parts = []
    for repo_key, hook in iter_hooks("experiment_page_widget"):
        try:
            html = hook(account_id, exp_id)
        except Exception as exc:
            logger.warning("plugin hook 'experiment_page_widget' of '%s' raised: %s", repo_key, exc)
            continue
        if isinstance(html, str) and html:
            parts.append(html)
    return "".join(parts)
