"""Characterization snapshots for the zero-dependency plan (phase 0).

They pin what the decoupling must not change: the admin tutorial texts. The URL map, the database schema, the template list and the Italian catalogue are
pinned by ``test_platform_baseline.py``; the prompts by ``docs/prompt-hashes.json``.
A phase that moves code but keeps the behaviour leaves them identical; one that changes them on purpose
regenerates the file with ``UPDATE_CHARACTERIZATION=1 pytest <this file>`` and the diff is reviewed.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(__file__).parent / "data" / "characterization"
UPDATE = bool(os.environ.get("UPDATE_CHARACTERIZATION"))


def _check(name: str, current):
    path = DATA / name
    if UPDATE or not path.exists():
        DATA.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(current, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        if not UPDATE:
            pytest.fail(f"{name} did not exist: created, commit it")
        return
    assert current == json.loads(
        path.read_text(encoding="utf-8")
    ), f"{name} changed: if intended, regenerate with UPDATE_CHARACTERIZATION=1 and review the diff"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.skipif(
    not all(
        (ROOT / "external" / r / "ysocial_platform/static/js/tutorials.js").exists()
        for r in ("YDating", "YInstantMessaging", "YForum", "YServerReddit")
    ),
    reason="the snapshot is taken with the platforms that own tutorial steps checked out",
)
def test_admin_tutorial_texts_are_unchanged():
    """The core's tutorial steps plus the ones the installed platforms add: moving a step must not change it."""
    scripts = [ROOT / "y_web/static/assets/js/admin-pages-tutorial.js"] + sorted(
        (ROOT / "external").glob("*/ysocial_platform/static/js/tutorials.js")
    )
    script = (
        "global.window={};"
        "process.argv.slice(1).forEach(function(f){require(f)});"
        "process.stdout.write(JSON.stringify({pages:window.YS_PAGE_TUTORIALS,fallback:window.YS_PAGE_TUTORIAL_FALLBACK}));"
    )
    out = subprocess.run(
        ["node", "-e", script, *map(str, scripts)],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    ).stdout
    _check("tutorials.json", json.loads(out))
