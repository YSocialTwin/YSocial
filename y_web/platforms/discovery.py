"""Platforms provided by installed repositories.

A simulation repository declares a platform in the ``"platform"`` section of its ``meta/registry.json``::

    "platform": {
        "key": "dating",                       # platform type stored in the experiments
        "api_version": "1.0",                  # PLATFORM_API the provider was written for
        "provider": "ysocial_platform.provider:DatingPlatform"   # PlatformProvider subclass
    }

The provider lives in the repository's ``ysocial_platform/`` folder, which is also its ``package_dir``
(templates, static files, blueprints: see :mod:`y_web.platforms.extension`).

Two optional keys reuse the plugin mechanisms: ``"i18n"`` (``{"domain", "translations"}``, see
:mod:`y_web.src.external_runtime.plugin_i18n`) and ``"schema_module"`` (``"module.path:callable"``, an idempotent
``migrate(engine_admin)`` run after the core migrations, see :func:`run_platform_schema_migrations`).

Discovery runs once at startup, before the extensions are installed. It never raises: a repository whose
declaration is wrong is reported and skipped. A platform installed while the application runs is picked up at the
next start, and :func:`platform_restart_required` tells the plugin manager to ask for it (decision D-5).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from y_web.platforms import registry
from y_web.platforms.base import PlatformProvider
from y_web.sdk.version import PLATFORM_API

# a provider works when it was written for the same major version of PLATFORM_API and a minor one not newer

PACKAGE_FOLDER = "ysocial_platform"
REGISTRY_RELATIVE_PATH = Path("meta") / "registry.json"

_DISCOVERED: Dict[str, str] = (
    {}
)  # repository key -> platform key, for what was registered at startup


def _version(value) -> Tuple[int, int]:
    major, _, minor = str(value or "").partition(".")
    return int(major), int(minor or 0)


def api_problem(api_version) -> Optional[str]:
    """Why a provider written for ``api_version`` cannot run on this core, or ``None``."""
    try:
        wanted, current = _version(api_version), _version(PLATFORM_API)
    except ValueError:
        return f"api_version {api_version!r} is not a version"
    if wanted[0] != current[0] or wanted[1] > current[1]:
        return f"written for platform API {api_version}, this application provides {PLATFORM_API}"
    return None


def read_declaration(repo_path: Path) -> Tuple[Optional[dict], List[str]]:
    """The ``platform`` declaration of a repository and the problems found in it.

    ``(None, [])`` means the repository does not declare a platform.
    """
    path = Path(repo_path) / REGISTRY_RELATIVE_PATH
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, []
    except (OSError, ValueError) as exc:
        return None, [f"{REGISTRY_RELATIVE_PATH}: {exc}"]
    declaration = payload.get("platform") if isinstance(payload, dict) else None
    if declaration is None:
        return None, []
    if not isinstance(declaration, dict):
        return None, ["'platform' must be an object"]
    problems = [
        f"'platform.{name}' is required"
        for name in ("key", "api_version", "provider")
        if not isinstance(declaration.get(name), str) or not declaration[name].strip()
    ]
    if not problems:
        if ":" not in declaration["provider"]:
            problems.append("'platform.provider' must look like 'module.path:Class'")
        problem = api_problem(declaration["api_version"])
        if problem:
            problems.append(problem)
        if not (Path(repo_path) / PACKAGE_FOLDER).is_dir():
            problems.append(f"folder {PACKAGE_FOLDER}/ is missing")
    return (None if problems else declaration), problems


def _load_provider(
    repo_key: str, repo_path: Path, declaration: dict
) -> PlatformProvider:
    from y_web.src.external_runtime.backend_plugins import import_from_suite

    dotted, _, name = declaration["provider"].partition(":")
    provider_class = getattr(import_from_suite(repo_key, dotted), name)
    if not (
        isinstance(provider_class, type)
        and issubclass(provider_class, PlatformProvider)
    ):
        raise TypeError(f"{declaration['provider']} is not a PlatformProvider")
    provider = provider_class()
    if provider.key != declaration["key"]:
        raise ValueError(
            f"provider key {provider.key!r} differs from declared key {declaration['key']!r}"
        )
    provider.package_dir = Path(repo_path) / PACKAGE_FOLDER
    return provider


def _register_i18n(repo_key: str, repo_path: Path, declaration: dict) -> List[str]:
    """Register the translation domain of a platform; a broken one only costs its translations."""
    if "i18n" not in declaration:
        return []
    from y_web.src.external_runtime.plugin_i18n import (
        normalize_i18n_manifest,
        register_plugin_i18n,
    )

    config, problems = normalize_i18n_manifest(
        repo_key, Path(repo_path), declaration["i18n"]
    )
    if config is not None and not register_plugin_i18n(repo_key, config):
        problems.append(f"translation domain {config['domain']!r} is already in use")
    return problems


def discover_platforms() -> Dict[str, List[str]]:
    """Register the platform of every installed repository that declares one.

    Returns ``{repository key: [problems]}`` for the repositories that declare a platform; an empty list means
    the platform is available.
    """
    from y_web.src.external_runtime.registry import supported_repos

    report: Dict[str, List[str]] = {}
    for repo_key, spec in supported_repos().items():
        if not spec.path.exists():
            continue
        declaration, problems = read_declaration(spec.path)
        if declaration is None and not problems:
            continue
        if not problems:
            try:
                provider = _load_provider(repo_key, spec.path, declaration)
                registry.replace_builtin(provider)
                _DISCOVERED[repo_key] = declaration["key"]
                provider.attach_routes()
                problems = _register_i18n(repo_key, spec.path, declaration)
            except (
                Exception
            ) as exc:  # noqa: BLE001 - a bad repository must not stop the application
                problems = [str(exc)]
        report[repo_key] = problems
    return report


def platform_restart_required(repo_key: str) -> bool:
    """Whether an installed repository provides a valid platform that is not live yet (needs a restart)."""
    from y_web.src.external_runtime.registry import supported_repos

    spec = supported_repos().get(repo_key)
    if spec is None or repo_key in _DISCOVERED or not spec.path.exists():
        return False
    declaration, problems = read_declaration(spec.path)
    return (
        declaration is not None
        and not problems
        and registry.get(declaration["key"]) is None
    )


def run_platform_schema_migrations(app) -> Dict[str, dict]:
    """Run the ``schema_module`` of the discovered platforms (idempotent, after the core migrations).

    Never raises: a failing migration is reported and logged, the application and the other platforms go on.
    Returns ``{repository key: {"ok": bool, "error": str | None}}``.
    """
    from y_web import db
    from y_web.src.external_runtime.backend_plugins import (
        _admin_engine,
        import_from_suite,
    )
    from y_web.src.external_runtime.registry import supported_repos

    report: Dict[str, dict] = {}
    for repo_key in list(_DISCOVERED):
        spec = supported_repos().get(repo_key)
        declaration = read_declaration(spec.path)[0] if spec else None
        reference = (declaration or {}).get("schema_module")
        if not reference:
            continue
        try:
            dotted, _, name = reference.partition(":")
            migrate = getattr(import_from_suite(repo_key, dotted), name)
            with app.app_context():
                ok = migrate(_admin_engine(db, app)) is not False
            report[repo_key] = {
                "ok": ok,
                "error": None if ok else "migration reported failure",
            }
        except Exception as exc:  # noqa: BLE001
            report[repo_key] = {"ok": False, "error": str(exc)}
        if report[repo_key]["error"]:
            app.logger.warning(
                "[platform repository %s] schema migration failed: %s",
                repo_key,
                report[repo_key]["error"],
            )
    return report
