"""Translation support for plugins (plan F1-7).

A plugin opts in with an ``i18n`` object in its ``meta/registry.json``::

    "i18n": {"domain": "training_modules", "translations": "translations"}

* ``domain``: gettext/JS domain name (``[a-z][a-z0-9_]{1,63}``, default: the repo key).
* ``translations``: directory, inside the plugin, holding the catalogs
  (default ``translations``): ``<dir>/<lang>/LC_MESSAGES/<domain>.mo`` for Python and
  templates, ``<dir>/js/<domain>/<lang>.json`` for browser code.

The core never edits a plugin catalog. A plugin without ``i18n``, with a missing or
broken catalog, or a language it does not translate simply shows English: nothing
here can break a page.

Plugin templates use ``{{ plugin_gettext('domain', 'English text') }}``, plugin Python
code ``plugin_gettext(domain, text, **vars)``; manifest strings (names, labels) are
resolved with ``{{ 'Modules'|plugin_text('training_modules') }}``.
"""

from __future__ import annotations

import re
from pathlib import Path

from flask_babel import Domain

DOMAIN_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
DEFAULT_TRANSLATIONS_DIR = "translations"

# domain -> {"repo_key", "path" (translations dir), "domain"}
_DOMAINS: dict[str, dict] = {}
_BABEL_DOMAINS: dict[str, Domain] = {}


def normalize_i18n_manifest(
    repo_key: str, plugin_path: Path, value
) -> tuple[dict | None, list[str]]:
    """Validate the manifest ``i18n`` value; return ``(config, problems)``."""
    if value is None:
        return None, []
    if not isinstance(value, dict):
        return None, ["'i18n' must be an object {domain, translations}"]
    problems = []
    domain = value.get("domain", repo_key)
    if not isinstance(domain, str) or not DOMAIN_RE.match(domain):
        problems.append(
            f"i18n.domain must match [a-z][a-z0-9_]{{1,63}}, got {domain!r}"
        )
    rel = value.get("translations", DEFAULT_TRANSLATIONS_DIR)
    if (
        not isinstance(rel, str)
        or not rel.strip()
        or rel.startswith(("/", "\\"))
        or ".." in Path(rel).parts
        or ":" in rel
    ):
        problems.append(
            f"i18n.translations must be a relative path inside the plugin, got {rel!r}"
        )
    if problems:
        return None, problems
    return {
        "domain": domain,
        "translations": rel,
        "path": str(Path(plugin_path) / rel),
    }, []


def register_plugin_i18n(repo_key: str, config: dict) -> bool:
    """Register a plugin domain (idempotent). Returns False on a domain clash."""
    domain = config["domain"]
    existing = _DOMAINS.get(domain)
    if existing and existing["repo_key"] != repo_key:
        return False
    _DOMAINS[domain] = {"repo_key": repo_key, "path": config["path"], "domain": domain}
    _BABEL_DOMAINS.pop(domain, None)
    return True


def unregister_plugin_i18n(repo_key: str) -> None:
    """Forget the domains of a plugin (used when a plugin is switched off or in tests)."""
    for domain in [d for d, c in _DOMAINS.items() if c["repo_key"] == repo_key]:
        _DOMAINS.pop(domain, None)
        _BABEL_DOMAINS.pop(domain, None)


def registered_domains() -> dict[str, dict]:
    """Return a copy of the registered plugin domains."""
    return {k: dict(v) for k, v in _DOMAINS.items()}


def _babel_domain(domain: str) -> Domain | None:
    config = _DOMAINS.get(domain)
    if config is None:
        return None
    cached = _BABEL_DOMAINS.get(domain)
    if cached is None:
        cached = Domain(translation_directories=[config["path"]], domain=domain)
        _BABEL_DOMAINS[domain] = cached
    return cached


def _interpolate(text: str, variables: dict) -> str:
    if not variables:
        return text
    try:
        return text % variables
    except (KeyError, ValueError, TypeError):
        return text


def plugin_gettext(domain: str, message: str, /, **variables) -> str:
    """Translate *message* with the catalog of plugin *domain* (English fallback)."""
    babel_domain = _babel_domain(domain)
    if babel_domain is None:
        return _interpolate(message, variables)
    try:
        return babel_domain.gettext(message, **variables)
    except Exception:  # a broken catalog must never break a page
        return _interpolate(message, variables)


def plugin_ngettext(
    domain: str, singular: str, plural: str, n: int, /, **variables
) -> str:
    """Plural-aware variant of :func:`plugin_gettext`."""
    fallback_vars = {"num": n, **variables}
    babel_domain = _babel_domain(domain)
    if babel_domain is None:
        return _interpolate(singular if n == 1 else plural, fallback_vars)
    try:
        # Domain.ngettext adds ``num`` itself and takes it as a positional argument.
        return babel_domain.ngettext(singular, plural, n, **variables)
    except Exception:
        return _interpolate(singular if n == 1 else plural, fallback_vars)


def plugin_js_catalog_dir(domain: str) -> Path | None:
    """Directory with the JS catalogs of a plugin domain, if registered."""
    config = _DOMAINS.get(domain)
    if config is None:
        return None
    return Path(config["path"]) / "js" / domain


def init_plugin_i18n(app) -> None:
    """Expose the helpers to Jinja (called from ``init_i18n``)."""
    app.jinja_env.globals["plugin_gettext"] = plugin_gettext
    app.jinja_env.globals["plugin_ngettext"] = plugin_ngettext
    app.jinja_env.filters["plugin_text"] = lambda text, domain: plugin_gettext(
        domain, text
    )
