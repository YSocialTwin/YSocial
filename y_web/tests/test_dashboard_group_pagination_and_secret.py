"""Dashboard boxes paginate by group; the dev secret key survives restarts."""

import ast
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_config():
    spec = importlib.util.spec_from_file_location(
        "ys_config", ROOT / "y_web" / "config.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _helpers():
    src = (ROOT / "y_web/routes/admin/dashboard.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    wanted = {"_sorted_group_names", "_page_of_groups"}
    code = "\n".join(
        ast.get_source_segment(src, n)
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name in wanted
    )
    ns = {}
    exec(code, ns)
    return ns


def test_pages_hold_whole_groups():
    h = _helpers()
    names = ["b", "A", "c", "d", "e", "f", "g"]
    page1, pages = h["_page_of_groups"](names, 1, 5)
    page2, _ = h["_page_of_groups"](names, 2, 5)
    assert pages == 2
    assert page1 == ["A", "b", "c", "d", "e"] and page2 == ["f", "g"]
    assert h["_page_of_groups"]([], 3, 5) == ([], 1)
    assert h["_page_of_groups"](names, 99, 5)[0] == page2  # clamped


def test_endpoint_and_js_paginate_groups():
    py = (ROOT / "y_web/routes/admin/dashboard.py").read_text(encoding="utf-8")
    js = (ROOT / "y_web/static/assets/js/admin-dashboard.js").read_text(
        encoding="utf-8"
    )
    assert (
        '"groups": groups' in py
        and "paginated_experiments = [e for g in page_groups" in py
    )
    assert "renderGroupsFromData" in js and "loadExperimentPage" in js
    assert "completed: 5, stopped: 5" in js  # groups per page


def test_secret_key_is_persisted(tmp_path):
    cfg = _load_config()
    path = tmp_path / ".ysocial_secret_key"
    first = cfg.load_or_create_secret_key(str(path))
    assert first and len(first) >= 32
    assert cfg.load_or_create_secret_key(str(path)) == first
    assert (path.stat().st_mode & 0o777) == 0o600
