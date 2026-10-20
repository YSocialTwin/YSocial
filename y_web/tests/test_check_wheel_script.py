import importlib.util
import zipfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "packaging" / "check_wheel.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("check_wheel", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_check_wheel_detects_missing_and_forbidden(tmp_path):
    mod = _load()
    whl = tmp_path / "x.whl"
    with zipfile.ZipFile(whl, "w") as z:
        z.writestr("y_social.py", "")
        z.writestr("y_web/tests/test_a.py", "")
    problems = mod.check(str(whl))
    assert any("y_web/db_init/__init__.py" in p for p in problems)
    assert any(p.startswith("forbidden") for p in problems)


def test_check_wheel_accepts_complete(tmp_path):
    mod = _load()
    whl = tmp_path / "ok.whl"
    with zipfile.ZipFile(whl, "w") as z:
        for r in mod.REQUIRED:
            z.writestr(r, "")
        z.writestr("y_web/templates/a.html", "")
        z.writestr("data_schema/migrations/env.py", "")
    assert mod.check(str(whl)) == []
