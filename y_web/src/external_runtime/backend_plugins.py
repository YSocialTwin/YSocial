"""Discovery, validation and loading of "backend settings" plugin suites.

A "backend settings" suite is structurally parallel to a "frontend plugins"
suite (:mod:`y_web.src.external_runtime.frontend_plugins` /
:mod:`y_web.src.external_runtime.plugin_loader`) but serves a different
purpose: it is an **admin-only authoring tool** (e.g. Scenario Design), not a
widget injected into pages seen by experiment participants.

Structural differences from a frontend plugin suite, by design:

* Repos in this family are registered with ``group="backend_settings"``
  (vs. ``"frontend_plugins"``).
* Their manifest declares a top-level ``"backend_plugins"`` list (vs.
  ``"frontend_plugins"``) — a distinct schema key, even though the shape of
  each module entry is otherwise the same, because a backend module has no
  participant-facing ``frontend_entry``/``surfaces`` concept.
* A backend suite is **always active once installed and valid** — there is
  no per-experiment enable/disable table (no ``*ExpModuleSettings``
  equivalent) and no entry in ``/admin/frontend_settings``.

Every public function here is defensive, exactly like its frontend
counterpart: it never raises out to its caller, so a broken/misconfigured
backend suite can never prevent YWeb from starting or break unrelated pages.
"""

from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path

from y_web.src.external_runtime.registry import (
    ROOT,
    SUPPORTED_EXTERNAL_REPOS,
    runtime_spec,
)

REGISTRY_RELATIVE_PATH = Path("meta") / "registry.json"
INFO_RELATIVE_PATH = Path("meta") / "info.json"

REQUIRED_MODULE_FIELDS = ("module_id", "display_name", "version")

_REGISTERED_SUITES: dict[str, dict] = (
    {}
)  # repo_key -> {"modules": {module_id: manifest}}


def _app_version() -> str | None:
    try:
        version_file = ROOT / "VERSION"
        if version_file.exists():
            return version_file.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return None


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = []
    for chunk in str(value or "").strip().split("."):
        try:
            parts.append(int(chunk))
        except ValueError:
            parts.append(0)
    return tuple(parts) or (0,)


def _version_in_range(app_version: str | None, min_v, max_v) -> bool:
    if app_version is None:
        return True  # can't determine — don't block, just skip the check
    current = _version_tuple(app_version)
    if min_v and current < _version_tuple(min_v):
        return False
    if max_v and current > _version_tuple(max_v):
        return False
    return True


def backend_plugin_repo_keys() -> list[str]:
    """All registry keys belonging to the 'backend_settings' group."""
    return [
        key
        for key, spec in SUPPORTED_EXTERNAL_REPOS.items()
        if spec.group == "backend_settings"
    ]


def _load_json(path: Path) -> tuple[dict | list | None, str | None]:
    if not path.exists():
        return None, f"missing file: {path.name}"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"invalid JSON in {path.name}: {exc}"


def validate_backend_suite(repo_key: str) -> dict:
    """Full validation report for the backend suite installed at *repo_key*.

    Same report shape as :func:`frontend_plugins.validate_frontend_suite`,
    applied to the ``"backend_plugins"`` manifest key instead of
    ``"frontend_plugins"``. Never raises.
    """
    report = {
        "installed": False,
        "valid": False,
        "suite": None,
        "modules": [],
        "errors": [],
        "warnings": [],
    }

    try:
        spec = runtime_spec(repo_key)
    except KeyError:
        report["errors"].append(f"unknown runtime key: {repo_key}")
        return report

    if not spec.path.exists():
        return report  # not installed — not an error, just unavailable

    report["installed"] = True
    app_version = _app_version()

    info_payload, info_err = _load_json(spec.path / INFO_RELATIVE_PATH)
    if info_err:
        report["warnings"].append(f"meta/info.json: {info_err}")

    registry_payload, registry_err = _load_json(spec.path / REGISTRY_RELATIVE_PATH)
    if registry_err:
        report["errors"].append(f"meta/registry.json: {registry_err}")
        return report
    if not isinstance(registry_payload, dict):
        report["errors"].append("meta/registry.json: top-level value must be an object")
        return report

    suite_meta = registry_payload.get("suite")
    if not isinstance(suite_meta, dict) or not suite_meta.get("suite_id"):
        report["errors"].append("meta/registry.json: missing or invalid 'suite' object")
        return report
    report["suite"] = suite_meta

    if not _version_in_range(
        app_version,
        suite_meta.get("min_app_version"),
        suite_meta.get("max_app_version"),
    ):
        report["errors"].append(
            f"suite requires app version between {suite_meta.get('min_app_version')} "
            f"and {suite_meta.get('max_app_version') or '∞'}, current app version is {app_version}"
        )

    raw_modules = registry_payload.get("backend_plugins")
    if not isinstance(raw_modules, list):
        report["errors"].append("meta/registry.json: 'backend_plugins' must be a list")
        return report

    seen_ids: set[str] = set()
    for entry in raw_modules:
        module_report = dict(entry) if isinstance(entry, dict) else {}
        errors = []

        if not isinstance(entry, dict):
            errors.append("module entry must be an object")
            report["modules"].append({"valid": False, "errors": errors})
            continue

        for field in REQUIRED_MODULE_FIELDS:
            if not str(entry.get(field) or "").strip():
                errors.append(f"missing required field '{field}'")

        module_id = str(entry.get("module_id") or "").strip()
        if module_id and module_id in seen_ids:
            errors.append(f"duplicate module_id '{module_id}' in this suite")
        elif module_id:
            seen_ids.add(module_id)

        if not _version_in_range(
            app_version, entry.get("min_app_version"), entry.get("max_app_version")
        ):
            errors.append(
                f"module requires app version between {entry.get('min_app_version')} "
                f"and {entry.get('max_app_version') or '∞'}, current app version is {app_version}"
            )

        backend_blueprint = entry.get("backend_blueprint")
        if backend_blueprint:
            if ":" not in str(backend_blueprint):
                errors.append(
                    f"backend_blueprint must be in 'dotted.module:attr' form, got '{backend_blueprint}'"
                )
            else:
                dotted, _, _attr = str(backend_blueprint).partition(":")
                backend_path = spec.path / Path(*dotted.split("."))
                if not (
                    backend_path.with_suffix(".py").exists()
                    or (backend_path / "__init__.py").exists()
                ):
                    errors.append(
                        f"backend_blueprint module not found on disk: {dotted}"
                    )
        else:
            errors.append("missing required field 'backend_blueprint'")

        module_report["valid"] = not errors
        module_report["errors"] = errors
        report["modules"].append(module_report)

    report["valid"] = not report["errors"] and all(
        m.get("valid") for m in report["modules"]
    )
    return report


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


def register_backend_plugin_suites(app) -> dict:
    """Register blueprints for every installed+valid backend settings suite.

    Called once from ``create_app()``, alongside
    :func:`plugin_loader.register_frontend_plugin_suites`. Returns a small
    diagnostics dict; never raises. Unlike the frontend equivalent, there is
    no per-experiment enable/disable step: a valid suite's blueprint is
    simply always registered.
    """
    report = {"suites": {}}

    for repo_key in backend_plugin_repo_keys():
        suite_report = {
            "installed": False,
            "valid": False,
            "registered_modules": [],
            "errors": [],
        }
        try:
            validation = validate_backend_suite(repo_key)
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

            try:
                bp = _import_blueprint(repo_key, backend_blueprint)
                app.register_blueprint(bp)
                suite_report["registered_modules"].append(module_id)
            except Exception as exc:
                app.logger.warning(
                    "[backend_settings] failed to load backend for module '%s' in suite '%s': %s",
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
                "[backend_settings] failed to register static assets route for '%s': %s",
                repo_key,
                exc,
            )

        report["suites"][repo_key] = suite_report

    return report


def _register_static_blueprint(app, repo_key: str) -> None:
    """Serve each module's static assets (admin-only editor JS/CSS).

    Same path-traversal protection as the frontend plugin static route.
    """
    from flask import Blueprint, abort, send_from_directory

    endpoint_name = f"backend_settings_static_{repo_key}"
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


def backend_suite_availability() -> dict[str, bool]:
    """Cheap, request-time map of ``{repo_key: installed_and_valid}`` for every
    registered backend settings suite.

    Intended for template context processors that need to conditionally
    show/hide a sidebar entry for a backend suite (there is no existing
    precedent for this in ``head.html`` — "Frontend Settings"/"External
    Runtimes" are unconditional core pages, not gated on any suite's
    validity) — this is new, generic infrastructure, reusable by any future
    backend suite, not specific to Scenario Design.
    """
    availability: dict[str, bool] = {}
    for repo_key in backend_plugin_repo_keys():
        try:
            availability[repo_key] = bool(validate_backend_suite(repo_key).get("valid"))
        except Exception:
            availability[repo_key] = False
    return availability


def inject_backend_plugin_visibility() -> dict:
    """Context-processor body: inject installed+valid status of backend
    settings suites, plus the resolved Scenario Design sidebar URL.

    Generic, reusable by any backend settings suite (not Scenario
    Design-specific): a template conditions a sidebar entry on
    ``backend_suites_available.get('<repo_key>')`` rather than the suite
    being unconditionally visible (unlike "Frontend Settings"/"External
    Runtimes", which are unconditional core pages, not gated on any
    suite's validity — there was no pre-existing template pattern for
    this kind of conditional visibility to mirror).

    Lives here (not inline in ``y_web/__init__.py``) so the create_app()
    factory only needs one line (``app.context_processor(
    inject_backend_plugin_visibility)``) to wire it in -- kept out of
    ``__init__.py`` specifically to not grow that file's line count (see
    ``y_web/tests/test_phase11_db_init_package.py::
    test_y_web_init_line_count_reduced``, a Phase 11 refactor guard this
    function's body would otherwise have pushed over its threshold).
    """
    try:
        from flask import url_for
        from werkzeug.routing import BuildError

        availability = backend_suite_availability()
        # Resolve the sidebar URL defensively: a suite can pass manifest
        # validation yet still fail blueprint registration at startup
        # (e.g. an import error inside the module) — url_for() on an
        # endpoint that was never actually registered would otherwise
        # raise BuildError and break rendering for every page, not just
        # the sidebar. Hiding the link (None) is the safe degradation.
        scenario_design_url = None
        if availability.get("scenario_design"):
            try:
                scenario_design_url = url_for("scenario_design.app_shell")
            except BuildError:
                scenario_design_url = None
        return dict(
            backend_suites_available=availability,
            scenario_design_sidebar_url=scenario_design_url,
        )
    except Exception:
        return dict(backend_suites_available={}, scenario_design_sidebar_url=None)
