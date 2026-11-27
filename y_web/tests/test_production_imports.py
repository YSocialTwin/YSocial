"""The production code must import without the aliases the tests install (no conftest, plain interpreter).

A module that exists only through ``y_web/tests/_platform_alias.py`` passes every other test and breaks in
production (the Instant Messaging scenario publishing was broken that way). This runs the check in a fresh process.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_production_modules_import_without_test_aliases(tmp_path):
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT), str(ROOT / "external")])
    env["YSOCIAL_HOME"] = str(ROOT)
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "dev" / "check_production_imports.py")],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert proc.stdout, proc.stderr[-2000:]
    report = json.loads(proc.stdout)
    assert report["failures"] == [], "\n".join(report["failures"])
    assert report["core_modules"] > 100
