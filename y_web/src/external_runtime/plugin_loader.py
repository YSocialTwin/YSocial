"""Runtime loader for Frontend Adds-on-style frontend plugin suites.

Responsible for the parts of the "zero impact when not installed/active"
guarantee that happen at Flask app-startup and per-request time:

* Dynamically importing a suite module's backend Python package from inside
  its external git repo (e.g. ``external/frontend_adds-on/modules/post_annotation``)
  WITHOUT adding that repo to ``sys.path`` — this avoids polluting the global
  import namespace and avoids collisions between top-level package names
  used by different suites (many suites may reasonably have a top-level
  ``modules`` package). This is done via a synthetic namespace package
  registered in ``sys.modules`` under a private, suite-scoped name, whose
  ``__path__`` points at the suite's repo root.
* Registering each module's Flask blueprint — but ONLY once, at startup,
  and ONLY for suites that pass :func:`validate_frontend_suite`. If the
  suite is not installed at all, none of this runs and the blueprint's
  routes simply do not exist (a real 404, not a conditional check) — this
  is what delivers "zero impact when not installed" at the routing layer.
* A tiny static-file blueprint serving each module's frontend_entry/
  frontend_style assets, registered under the same installed+valid guard.
* Just-in-time, per-experiment schema migration for a module's own tables,
  run once when an admin enables that module for a specific experiment
  (see ``y_web.routes.admin.sub.experiments._frontend_settings``).

Every public function here is defensive: it never raises out to its caller.
A broken/misconfigured suite must never prevent YWeb from starting or
prevent unrelated experiments/pages from rendering.
"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

from y_web.src.external_runtime.frontend_plugins import (
    discover_frontend_modules,
    frontend_plugin_repo_keys,
    validate_frontend_suite,
)
from y_web.src.external_runtime.registry import runtime_spec

_REGISTERED_SUITES: dict[str, dict] = (
    {}
)  # repo_key -> {"modules": {module_id: manifest}}


def _namespace_root_name(repo_key: str) -> str:
    return f"_ysocial_ext__{repo_key}"


def _ensure_namespace_root(repo_key: str, repo_path: Path) -> str:
    root_name = _namespace_root_name(repo_key)
    existing = sys.modules.get(root_name)
    if existing is not None and getattr(existing, "__path__", None) == [str(repo_path)]:
        return root_name
    module = types.ModuleType(root_name)
    module.__path__ = [str(repo_path)]
    module.__package__ = root_name
    sys.modules[root_name] = module
    return root_name


def _import_from_suite(repo_key: str, dotted_path: str):
    """Import ``dotted_path`` (e.g. 'modules.post_annotation.backend') from
    inside the *repo_key* suite's repo, via the synthetic namespace package.
    """
    spec = runtime_spec(repo_key)
    root_name = _ensure_namespace_root(repo_key, spec.path)
    full_name = f"{root_name}.{dotted_path}"
    if full_name in sys.modules:
        return sys.modules[full_name]
    return importlib.import_module(full_name)


def _import_blueprint(repo_key: str, backend_blueprint: str):
    dotted, _, attr = backend_blueprint.partition(":")
    module = _import_from_suite(repo_key, dotted)
    return getattr(module, attr)


def register_frontend_plugin_suites(app) -> dict:
    """Register blueprints for every installed+valid frontend plugin suite.

    Called once from ``create_app()``. Returns a small diagnostics dict
    (used in tests and optionally surfaced in admin diagnostics); never
    raises.
    """
    report = {"suites": {}}

    for repo_key in frontend_plugin_repo_keys():
        suite_report = {
            "installed": False,
            "valid": False,
            "registered_modules": [],
            "errors": [],
        }
        try:
            validation = validate_frontend_suite(repo_key)
        except Exception as exc:
            suite_report["errors"].append(f"validation crashed: {exc}")
            report["suites"][repo_key] = suite_report
            continue

        suite_report["installed"] = validation["installed"]
        suite_report["valid"] = validation["valid"]
        suite_report["errors"] = list(validation.get("errors", []))

        if not validation["installed"] or not validation["valid"]:
            report["suites"][repo_key] = suite_report
            continue

        modules_by_id = {}
        for module_manifest in validation["modules"]:
            if not module_manifest.get("valid"):
                continue
            module_id = module_manifest.get("module_id")
            backend_blueprint = module_manifest.get("backend_blueprint")
            modules_by_id[module_id] = module_manifest

            if not backend_blueprint:
                continue  # module has no backend (frontend-only decoration) — fine
            try:
                bp = _import_blueprint(repo_key, backend_blueprint)
                app.register_blueprint(bp)
                suite_report["registered_modules"].append(module_id)
            except Exception as exc:
                # A broken module must never break the others or the app.
                app.logger.warning(
                    "[frontend_adds_on] failed to load backend for module '%s' in suite '%s': %s",
                    module_id,
                    repo_key,
                    exc,
                )
                suite_report["errors"].append(
                    f"module '{module_id}' backend import failed: {exc}"
                )

        _REGISTERED_SUITES[repo_key] = {"modules": modules_by_id}

        try:
            _register_static_blueprint(app, repo_key)
        except Exception as exc:
            app.logger.warning(
                "[frontend_adds_on] failed to register static assets route for '%s': %s",
                repo_key,
                exc,
            )

        report["suites"][repo_key] = suite_report

    return report


def _register_static_blueprint(app, repo_key: str) -> None:
    """Serve each module's frontend_entry/frontend_style files.

    These files live inside the suite's repo (outside y_web/static), so they
    need their own tiny, tightly-scoped route rather than Flask's default
    static handler. Path traversal is prevented by resolving the requested
    file and checking it stays under the suite's repo root.
    """
    from flask import Blueprint, abort, send_from_directory

    endpoint_name = f"frontend_adds_on_static_{repo_key}"
    if endpoint_name in app.blueprints:
        return

    spec = runtime_spec(repo_key)
    static_bp = Blueprint(endpoint_name, __name__)

    @static_bp.route(f"/plugins/{repo_key}/<module_id>/static/<path:filename>")
    def _serve(module_id, filename):
        suite_state = _REGISTERED_SUITES.get(repo_key)
        if not suite_state or module_id not in suite_state["modules"]:
            abort(404)
        try:
            requested = (spec.path / filename).resolve()
            if (
                spec.path.resolve() not in requested.parents
                and requested != spec.path.resolve()
            ):
                abort(404)
        except Exception:
            abort(404)
        return send_from_directory(str(spec.path), filename)

    app.register_blueprint(static_bp)


def registered_suite_modules(repo_key: str) -> dict:
    """Modules actually registered (installed+valid+imported) for *repo_key*."""
    return dict(_REGISTERED_SUITES.get(repo_key, {}).get("modules", {}))


def is_module_available(repo_key: str, module_id: str) -> bool:
    """True if the module's backend was successfully registered at startup.

    This reflects install+validation+import success — NOT whether any
    experiment has enabled the module (that's a separate, per-experiment
    check against FrontendAddsOnExpModuleSettings).
    """
    return module_id in registered_suite_modules(repo_key)


def _experiment_db_path(exp_id: int) -> str | None:
    import os as _os

    from y_web import db
    from y_web.src.models import Exps
    from y_web.src.system.path_utils import get_writable_path

    exp = db.session.get(Exps, exp_id)
    if exp is None or not exp.db_name:
        return None
    return get_writable_path(_os.path.join("y_web", exp.db_name))


def ensure_module_schema(
    repo_key: str, module_id: str, exp_id: int, quiet: bool = True
) -> bool:
    """Run the module's own JIT migration against exp_id's database, if any.

    Called by the admin "enable module for experiment" handler, right
    before flipping ``enabled=True`` in ``FrontendAddsOnExpModuleSettings``. A
    module without a ``migrations_module`` entry (nothing to create) is a
    no-op success. Never raises — returns False on any failure so the
    caller can surface a clear "could not enable" error instead of a 500.
    """
    manifest = registered_suite_modules(repo_key).get(module_id)
    if manifest is None:
        # Fall back to a live (unregistered-at-startup) manifest lookup —
        # covers the case where the suite was installed after app startup.
        for entry in discover_frontend_modules(repo_key):
            if entry.get("module_id") == module_id:
                manifest = entry
                break
    if manifest is None:
        return False

    migrations_module = manifest.get("migrations_module")
    if not migrations_module:
        return True  # nothing to migrate

    db_path = _experiment_db_path(exp_id)
    if not db_path:
        return False

    try:
        module = _import_from_suite(repo_key, migrations_module)
        return bool(module.migrate_sqlite_server(db_path, quiet=quiet))
    except Exception:
        return False


def active_modules_context(exp_id: int) -> list[dict]:
    """Build the per-request context consumed by the frontend loader template.

    Returns a list of ``{module_id, api_base, frontend_entry, frontend_style,
    config}`` dicts — one per module that is (a) registered at startup for
    an installed+valid suite, and (b) enabled for *exp_id*. Empty list (zero
    template/JS overhead) whenever no suite is installed or no experiment
    has anything enabled — this is the single choke point that guarantees
    "no impact when Frontend Adds-on is absent or inactive".
    """
    if not _REGISTERED_SUITES:
        return []

    try:
        from y_web import db
        from y_web.src.models import FrontendAddsOnExpModuleSettings
    except Exception:
        return []

    results = []
    for repo_key, state in _REGISTERED_SUITES.items():
        modules = state.get("modules", {})
        if not modules:
            continue
        try:
            rows = (
                db.session.query(FrontendAddsOnExpModuleSettings)
                .filter_by(exp_id=exp_id, enabled=True)
                .all()
            )
        except Exception:
            rows = []

        for row in rows:
            manifest = modules.get(row.module_id)
            if manifest is None:
                continue
            import json as _json

            try:
                saved_cfg = _json.loads(row.config_json or "{}")
            except Exception:
                saved_cfg = {}
            cfg = {p["name"]: p.get("default") for p in manifest.get("parameters", [])}
            cfg.update(saved_cfg)

            frontend_entry = manifest.get("frontend_entry")
            frontend_style = manifest.get("frontend_style")
            results.append(
                {
                    "module_id": row.module_id,
                    "exp_id": exp_id,
                    "api_base": f"/{exp_id}/api/plugins/{repo_key}/{row.module_id}",
                    "frontend_entry": (
                        f"/plugins/{repo_key}/{row.module_id}/static/{frontend_entry}"
                        if frontend_entry
                        else None
                    ),
                    "frontend_style": (
                        f"/plugins/{repo_key}/{row.module_id}/static/{frontend_style}"
                        if frontend_style
                        else None
                    ),
                    "config": cfg,
                }
            )
    return results


def get_hidden_user_ids(exp_id: int, viewer_user_id: int) -> set[int]:
    """Union of user ids that installed frontend-plugin suites want hidden
    from *viewer_user_id* (and their content's descendant subtree pruned)
    when rendering *exp_id* for a human.

    Generic over ``_REGISTERED_SUITES`` exactly like ``active_modules_context``:
    a suite opts in by adding a ``"visibility_filter": "<dotted.module>:<func>"``
    key to a module's manifest entry. The referenced callable is resolved via
    ``_import_from_suite`` (never imported by a hardcoded suite name) and
    invoked as ``func(exp_id, viewer_user_id) -> Iterable[int]``.

    Returns an empty set with zero overhead when no suite is installed, and
    silently skips (contributing nothing) any suite whose manifest omits this
    key, whose callable can't be resolved, or whose call raises -- exactly the
    "a broken/misconfigured suite must never prevent unrelated pages from
    rendering" contract every other function in this module already follows.
    This is the single choke point that guarantees "no impact when no suite
    registers this capability", the same way ``active_modules_context`` is for
    frontend-widget metadata.
    """
    if not _REGISTERED_SUITES:
        return set()

    hidden: set[int] = set()
    for repo_key, state in _REGISTERED_SUITES.items():
        modules = state.get("modules", {})
        for module_id, manifest in modules.items():
            filter_path = manifest.get("visibility_filter")
            if not filter_path or ":" not in filter_path:
                continue
            try:
                dotted, _, func_name = filter_path.partition(":")
                module = _import_from_suite(repo_key, dotted)
                func = getattr(module, func_name)
                ids = func(exp_id, viewer_user_id)
                if ids:
                    hidden.update(int(i) for i in ids)
            except Exception:
                continue
    return hidden
