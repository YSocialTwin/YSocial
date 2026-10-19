"""Verify the contents of a built ysocial wheel (E1 gate).

Usage: python scripts/packaging/check_wheel.py dist/ysocial-*.whl
"""

import sys
import zipfile

REQUIRED = [
    "y_social.py",
    "y_web/__init__.py",
    "y_web/db_init/__init__.py",
    "y_web/db_init/sqlite.py",
    "y_web/db_init/migrations.py",
    "y_web/src/system/path_utils.py",
    "y_web/translations/it/LC_MESSAGES/messages.mo",
    "y_web/prompts_internal.json",
    "y_web/src/external_runtime/builtin_plugins.json",
]
FORBIDDEN_PREFIXES = (
    "y_web/tests/",
    "y_web/experiments/",
    "external/",
    "y_web/static/assets/img/users/",
)


def check(path):
    names = zipfile.ZipFile(path).namelist()
    problems = [f"missing: {r}" for r in REQUIRED if r not in names]
    problems += [f"forbidden: {n}" for n in names if n.startswith(FORBIDDEN_PREFIXES)]
    if not any(n.startswith("y_web/templates/") for n in names):
        problems.append("missing: y_web/templates/*")
    if not any(n.startswith("data_schema/migrations/") for n in names):
        problems.append("missing: data_schema/migrations/*")
    return problems


if __name__ == "__main__":
    probs = check(sys.argv[1])
    for p in probs:
        print(p)
    print("OK" if not probs else f"{len(probs)} problem(s)")
    sys.exit(1 if probs else 0)
