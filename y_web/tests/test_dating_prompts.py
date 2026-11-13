"""Dating prompts page model (S5): packs, overrides, validation and the runtime's field syntax."""

import importlib.util
import json
from pathlib import Path

import pytest

from y_web.src.dating import prompts_admin as pa

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2] / "external" / "YDating"
needs_runtime = pytest.mark.skipif(not REPO.exists(), reason="YDating is not present")


@needs_runtime
def test_every_prompt_of_the_package_is_in_a_section():
    base = pa.base_templates("en", str(REPO))
    grouped = {k for _, _, _, keys in pa.GROUPS for k in keys}
    assert grouped == set(
        base
    ), "a prompt of the package has no section (or a section names a missing one)"
    assert [s["id"] for s in pa.sections(base, {})][-1] != "other"


@needs_runtime
def test_languages_and_italian_layering():
    assert pa.languages(str(REPO)) == ["en", "it"]
    en, it = pa.base_templates("en", str(REPO)), pa.base_templates("it", str(REPO))
    assert set(en) == set(it) and en["opener"] != it["opener"]


@needs_runtime
def test_field_syntax_matches_the_runtime_store():
    spec = importlib.util.spec_from_file_location(
        "prompt_store_rt", REPO / "YDating" / "prompt_store.py"
    )
    store = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(store)
    for lang in ("en", "it"):
        for text in pa.base_templates(lang, str(REPO)).values():
            assert pa.fields_of(text) == store.fields_of(text)


@needs_runtime
def test_form_writes_only_changed_keys_and_refuses_new_fields(tmp_path):
    base = pa.base_templates("en", str(REPO))
    form = {f"{pa.PREFIX}{k}": v for k, v in base.items()}
    assert pa.parse_form(form, base) == ({}, [])
    form[f"{pa.PREFIX}unspecified"] = "n/a"
    override, errors = pa.parse_form(form, base)
    assert override == {"unspecified": "n/a"} and errors == []
    form[f"{pa.PREFIX}opener"] = "hello {not_a_field}"
    form[f"{pa.PREFIX}reply"] = "  "
    _, errors = pa.parse_form(form, base)
    assert len(errors) == 2

    pa.save(str(tmp_path), "en", override)
    assert json.loads((tmp_path / "prompts_dating.json").read_text()) == override
    item = next(
        i
        for s in pa.sections(base, pa.custom_templates(str(tmp_path), "en"))
        for i in s["items"]
        if i["key"] == "unspecified"
    )
    assert item["modified"] and item["hash"] == pa.digest("n/a")[:12]
    pa.save(str(tmp_path), "en", {})
    assert not (tmp_path / "prompts_dating.json").exists()


@needs_runtime
def test_template_compiles(app=None):
    from jinja2 import Environment

    src = (
        Path(__file__).resolve().parents[1] / "templates/admin/prompts_dating.html"
    ).read_text()
    Environment(extensions=["jinja2.ext.i18n"]).parse(src)
