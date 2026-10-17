"""Every admin page has a guided tour that works and is translatable."""

import json
import pathlib
import re
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
ADMIN = ROOT / "templates/admin"
JS = ROOT / "static/assets/js"
CATALOG = ROOT / "translations/js/tutorials"

# not pages: layout partials, or wrappers around another page
PARTIALS = {
    "head",
    "footer",
    "dash_head",
    "_flash_messages",
    "_prompt_language",
    "prompts_forum",
    "experiment_details_photo",
    "select_experiment_unused",
}


def _pages():
    return sorted(p.stem for p in ADMIN.glob("*.html") if p.stem not in PARTIALS)


def _registry():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not available")
    script = (
        "global.window={};const fs=require('fs');"
        "eval(fs.readFileSync(process.argv[1],'utf8'));"
        "console.log(JSON.stringify({pages:window.YS_PAGE_TUTORIALS,fallback:window.YS_PAGE_TUTORIAL_FALLBACK}))"
    )
    out = subprocess.run(
        [node, "-e", script, str(JS / "admin-pages-tutorial.js")],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(out.stdout)


def test_every_admin_page_has_a_tutorial():
    uncovered = []
    for page in _pages():
        src = (ADMIN / f"{page}.html").read_text(encoding="utf-8")
        if (
            re.search(r"tutorials/[a-z_]+_tutorial\.html", src)
            or "data-tutorial-page=" in src
        ):
            continue
        uncovered.append(page)
    assert uncovered == []


def test_registry_selectors_exist_in_their_templates():
    registry = _registry()["pages"]
    problems = []
    for page, steps in registry.items():
        if (
            page == "prompts_forum"
        ):  # wrapper: it includes prompts.html, which carries the markers
            continue
        src = (ADMIN / f"{page}.html").read_text(encoding="utf-8")
        assert f'data-tutorial-page="{page}"' in src
        for step in steps:
            selector = step["selector"]
            token = (
                re.search(r'data-tut="([^"]+)"', selector)
                or re.search(r"#([A-Za-z][\w-]*)", selector)
                or re.search(r"\.([A-Za-z][\w-]*)", selector)
            )
            if "^=" in selector:
                continue
            if token is None or token.group(1) not in src:
                problems.append((page, selector))
    assert problems == []


def test_registry_texts_are_in_both_catalogs():
    data = _registry()
    texts = set()
    for steps in data["pages"].values():
        for step in steps:
            texts.add(step["description"])
            if step["title"] != "@heading":
                texts.add(step["title"])
    texts.update(data["fallback"].values())
    en = json.loads((CATALOG / "en.json").read_text(encoding="utf-8"))
    it = json.loads((CATALOG / "it.json").read_text(encoding="utf-8"))
    assert [t for t in texts if t not in en] == []
    assert [t for t in texts if not it.get(t)] == []


def test_training_pages_have_a_tour():
    base = next(
        ROOT.parent.glob(
            "external/TrainingModules/modules/training_editor/backend/templates/training/admin"
        ),
        None,
    )
    if base is None or not base.exists():
        pytest.skip("TrainingModules is not installed")
    missing = []
    for template in sorted(base.glob("*.html")):
        text = template.read_text(encoding="utf-8")
        if template.stem.startswith("_") or template.stem in ("base", "panel_unused"):
            continue
        if "{% extends" in text and "{% block tour %}" not in text:
            missing.append(template.name)
    assert missing == []
