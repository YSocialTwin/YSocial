"""Discovery and validation of Frontend Adds-on-style frontend plugin suites.

Mirrors the live-manifest-read pattern already used for agent plugins
(``y_web.routes.admin.sub.agents._plugin_agent_specs`` /
``_discover_plugin_agent_types``, reading ``meta/registry.json`` from
``y_agents_plugins``): manifests are parsed on demand, never cached in the
database, so editing/updating an installed suite's repo takes effect on the
next request without any migration or restart.

A "frontend plugin suite" is any repo registered in
``SUPPORTED_EXTERNAL_REPOS`` whose ``group`` is ``"frontend_plugins"`` and
whose ``meta/registry.json`` declares a top-level ``"frontend_plugins"``
list. Frontend Adds-on is the first (and, today, only) such suite.
"""

from __future__ import annotations

import json
from pathlib import Path

from y_web.src.external_runtime.registry import (
    ROOT,
    SUPPORTED_EXTERNAL_REPOS,
    runtime_spec,
)

REGISTRY_RELATIVE_PATH = Path("meta") / "registry.json"
INFO_RELATIVE_PATH = Path("meta") / "info.json"

REQUIRED_MODULE_FIELDS = ("module_id", "display_name", "version")


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


def frontend_plugin_repo_keys() -> list[str]:
    """All registry keys belonging to the 'frontend_plugins' group."""
    return [
        key
        for key, spec in SUPPORTED_EXTERNAL_REPOS.items()
        if spec.group == "frontend_plugins"
    ]


def _load_json(path: Path) -> tuple[dict | list | None, str | None]:
    if not path.exists():
        return None, f"missing file: {path.name}"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"invalid JSON in {path.name}: {exc}"


def discover_frontend_modules(repo_key: str) -> list[dict]:
    """Return the (unvalidated, best-effort) list of module manifests for *repo_key*.

    Used by request-time consumers (admin box, annotation blueprint config
    resolution) that just need the manifest data and don't care about full
    validation diagnostics — malformed entries are silently skipped.
    """
    try:
        spec = runtime_spec(repo_key)
    except KeyError:
        return []

    if not spec.path.exists():
        return []

    payload, _err = _load_json(spec.path / REGISTRY_RELATIVE_PATH)
    if not isinstance(payload, dict):
        return []

    modules = []
    for entry in payload.get("frontend_plugins", []) or []:
        if not isinstance(entry, dict):
            continue
        module_id = str(entry.get("module_id") or "").strip()
        if not module_id:
            continue
        modules.append(entry)
    return modules


def validate_frontend_suite(repo_key: str) -> dict:
    """Full validation report for the suite installed at *repo_key*.

    Returns a dict:
        {
          "installed": bool,
          "valid": bool,
          "suite": {...} | None,
          "modules": [ {..manifest.., "valid": bool, "errors": [...]} ],
          "errors": [...],     # suite-level errors (missing/invalid manifest)
          "warnings": [...],
        }

    Never raises: any unexpected exception is captured as an error entry so
    a single broken suite installation can never take down the admin pages
    that call this (frontend_settings, external_runtimes).
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

    raw_modules = registry_payload.get("frontend_plugins")
    if not isinstance(raw_modules, list):
        report["errors"].append("meta/registry.json: 'frontend_plugins' must be a list")
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

        frontend_entry = entry.get("frontend_entry")
        if frontend_entry and not (spec.path / frontend_entry).exists():
            errors.append(f"frontend_entry not found: {frontend_entry}")

        frontend_style = entry.get("frontend_style")
        if frontend_style and not (spec.path / frontend_style).exists():
            errors.append(f"frontend_style not found: {frontend_style}")

        backend_blueprint = entry.get("backend_blueprint")
        if backend_blueprint:
            if ":" not in str(backend_blueprint):
                errors.append(
                    f"backend_blueprint must be in 'dotted.module:attr' form, got '{backend_blueprint}'"
                )
            else:
                dotted, _, _attr = str(backend_blueprint).partition(":")
                backend_path = spec.path / Path(*dotted.split("."))
                # accept either a package (dir + __init__.py) or a bare module file
                if not (
                    backend_path.with_suffix(".py").exists()
                    or (backend_path / "__init__.py").exists()
                ):
                    errors.append(
                        f"backend_blueprint module not found on disk: {dotted}"
                    )

        for param in entry.get("parameters", []) or []:
            if not isinstance(param, dict) or not str(param.get("name") or "").strip():
                errors.append("a parameter entry is missing its 'name'")
                continue
            if param.get("type") == "enum" and not param.get("options"):
                errors.append(
                    f"parameter '{param.get('name')}': type 'enum' requires 'options'"
                )

        module_report["valid"] = not errors
        module_report["errors"] = errors
        report["modules"].append(module_report)

    report["valid"] = not report["errors"] and all(
        m.get("valid") for m in report["modules"]
    )
    return report
