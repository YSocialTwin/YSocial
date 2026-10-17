"""validate_pack.py accepts faithful language packs and rejects broken ones."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("validate_pack", ROOT / "scripts" / "prompts" / "validate_pack.py")
vp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vp)


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def tree(tmp_path):
    en = {"a": "Write about {topic}. Answer COMMENT or NONE.", "n": {"b": "Hello {self.name}"}}
    _write(tmp_path / "data_schema/prompts/en/prompts.json", en)
    _write(
        tmp_path / "data_schema/prompts/en/manifest.json",
        {"language": "en", "files": ["prompts.json"]},
    )
    _write(
        tmp_path / "data_schema/prompts/xx/manifest.json",
        {"language": "xx", "files": ["prompts.json"]},
    )
    _write(
        tmp_path / "data_schema/prompts/xx/prompts.json",
        {"a": "Scrivi su {topic}. Rispondi COMMENT oppure NONE.", "n": {"b": "Ciao {self.name}"}},
    )
    return tmp_path


def test_a_faithful_pack_passes(tree):
    assert vp.run(tree) == []


def test_the_real_english_pack_passes():
    assert vp.check_english(ROOT, vp._field_regex(ROOT)) == []


@pytest.mark.parametrize(
    "broken, expect",
    [
        ({"a": "Scrivi su {argomento}. COMMENT NONE", "n": {"b": "Ciao {self.name}"}}, "fields differ"),
        ({"a": "Scrivi su {topic}. Rispondi COMMENTA oppure NONE.", "n": {"b": "Ciao {self.name}"}}, "token COMMENT"),
        ({"a": "Scrivi su {topic}. COMMENT NONE"}, "n/b: missing"),
        ({"a": "x {topic} COMMENT NONE", "n": {"b": "Ciao {self.name}"}, "extra": "z"}, "does not exist"),
        ({"a": "x {topic} {extra} COMMENT NONE", "n": {"b": "Ciao {self.name}"}}, "fields differ"),
    ],
)
def test_broken_packs_are_reported(tree, broken, expect):
    _write(tree / "data_schema/prompts/xx/prompts.json", broken)
    problems = vp.run(tree)
    assert any(expect in line for line in problems), problems


def test_partial_packs_are_accepted_only_on_request(tree):
    _write(tree / "data_schema/prompts/xx/prompts.json", {"a": "Scrivi su {topic}. COMMENT NONE"})
    assert vp.run(tree) != []
    assert vp.run(tree, allow_partial=True) == []


def test_internal_packs_are_compared_too(tree):
    base = tree / "external/YClient/y_client"
    _write(base / "prompts_internal.json", {"k": "Reply {who}. YES or NO"})
    _write(base / "prompts_internal.xx.json", {"k": "Rispondi {chi}. YES o NO"})
    assert any("fields differ" in line for line in vp.run(tree))
