#!/usr/bin/env python3
"""Check that the production code imports without the test-only aliases (no conftest, no ``_platform_alias``).

The tests of the core alias some platform modules (``y_web.src.im.*``, ``y_web.src.dating.*``): a module missing in
production can pass them unnoticed. This script runs in a plain interpreter and

1. imports every non-test module of ``y_web``;
2. discovers the installed platforms and fails on any problem they report;
3. imports every module of the ``ysocial_platform`` package of each installed repository.

Exit code 0 when all pass; prints the failures otherwise. Usage: python scripts/dev/check_production_imports.py
"""

import importlib
import json
import pkgutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKIP_PARTS = ("tests", "test_", "alembic", "migrations")
# modules that by design import only once the Scenario Design extension has handed its support to the platform
NEEDS_EXTENSION = {"ysocial_platform.scenario_adapter"}


def _skip(name: str) -> bool:
    return any(part in name.split(".") or f".{part}" in name for part in SKIP_PARTS)


def check_core(failures: list) -> int:
    count = 0
    pkg = importlib.import_module("y_web")
    for info in pkgutil.walk_packages(pkg.__path__, "y_web."):
        if _skip(info.name):
            continue
        count += 1
        try:
            importlib.import_module(info.name)
        except BaseException as exc:  # noqa: BLE001
            failures.append(f"core {info.name}: {exc!r}"[:300])
    return count


def check_platforms(failures: list) -> int:
    from y_web.platforms.discovery import discover_platforms
    from y_web.src.external_runtime.backend_plugins import import_from_suite
    from y_web.src.external_runtime.registry import supported_repos

    report = discover_platforms()
    for repo_key, problems in report.items():
        for problem in problems:
            failures.append(f"discovery {repo_key}: {problem}"[:300])
    count = 0
    for repo_key, spec in supported_repos().items():
        package = Path(spec.path) / "ysocial_platform"
        if not package.is_dir() or repo_key not in report:
            continue
        for path in sorted(package.rglob("*.py")):
            rel = path.relative_to(Path(spec.path)).with_suffix("")
            parts = list(rel.parts)
            if parts[-1] == "__init__":
                parts = parts[:-1]
            if _skip(".".join(parts)) or ".".join(parts) in NEEDS_EXTENSION:
                continue
            count += 1
            try:
                import_from_suite(repo_key, ".".join(parts))
            except BaseException as exc:  # noqa: BLE001
                failures.append(f"{repo_key} {'.'.join(parts)}: {exc!r}"[:300])
    return count


def main() -> int:
    sys.path.insert(0, str(ROOT))
    failures: list = []
    core = check_core(failures)
    platforms = check_platforms(failures)
    print(
        json.dumps(
            {"core_modules": core, "platform_modules": platforms, "failures": failures},
            indent=2,
        )
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
