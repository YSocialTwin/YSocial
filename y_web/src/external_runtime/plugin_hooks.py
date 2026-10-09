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
``experiment_user_provisioned(exp, account_id, exp_user_id, created) -> None``
    Event emitted by ``ensure_experiment_user``.

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
