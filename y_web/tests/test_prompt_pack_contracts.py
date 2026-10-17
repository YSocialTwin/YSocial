"""Every language pack keeps the contracts the code relies on: same fields, same protocol tokens, renderable."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


vp = _load("validate_pack", ROOT / "scripts" / "prompts" / "validate_pack.py")
ps = _load("prompt_store_copy", ROOT / "y_web" / "prompt_store.py")
TOKENS_FILE = ROOT / "external" / "YClient" / "y_client" / "protocol_tokens.py"
LANGUAGES = ["en"] + vp.languages(ROOT)


class Probe(float):
    """Stands for any value a call site passes: attributes, items, a list to join, a number to format."""

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return Probe(1)

    def __getitem__(self, key):
        return Probe(1)

    def __iter__(self):
        return iter(["x", "y"])


def _strings(node, where=""):
    if isinstance(node, str):
        yield where, node
    elif isinstance(node, dict):
        for key, value in node.items():
            yield from _strings(value, f"{where}/{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _strings(value, f"{where}/{index}")


def _pack_files(language):
    base = ROOT / "data_schema" / "prompts" / language
    for name in vp.PACK_FILES if hasattr(vp, "PACK_FILES") else sorted(p.name for p in base.glob("prompts*.json")):
        if name.startswith("prompts") and (base / name).exists():
            yield base / name


@pytest.mark.parametrize("language", [l for l in LANGUAGES if l != "en"])
def test_the_pack_passes_the_validator_completely(language):
    assert vp.run(ROOT, only=language) == []


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_text_renders_with_the_fields_it_names(language):
    count = 0
    for path in _pack_files(language):
        for where, text in _strings(json.loads(path.read_text(encoding="utf-8"))):
            fields = {name: Probe(1) for name in ps.fields_of(text)}
            rendered = ps.render(text, **fields)
            assert isinstance(rendered, str), (path.name, where)
            count += 1
    assert count > 100


@pytest.mark.skipif(not TOKENS_FILE.exists(), reason="YClient is not checked out")
@pytest.mark.parametrize("language", [l for l in LANGUAGES if l != "en"])
def test_a_reply_in_the_protocol_is_understood_for_every_choice_a_prompt_offers(language):
    tokens = _load("protocol_tokens_copy", TOKENS_FILE)
    english = {p.name: dict(_strings(json.loads(p.read_text(encoding="utf-8")))) for p in _pack_files("en")}
    checked = 0
    for path in _pack_files(language):
        other = dict(_strings(json.loads(path.read_text(encoding="utf-8"))))
        for where, text in english[path.name].items():
            offered = vp._answer_tokens(text, set(vp._tokens(ROOT)))
            if len(offered) < 2:
                continue
            assert offered <= vp._answer_tokens(other[where], offered | set(vp._tokens(ROOT))), (path.name, where)
            for token in offered:
                reply = f"Sure, my answer is {token}."
                assert tokens.first_token(reply, sorted(offered)) == token, (where, token)
                checked += 1
    assert checked > 20
