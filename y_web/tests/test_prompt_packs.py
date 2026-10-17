"""Language packs: discovery, fallback to English, and the files written for an experiment."""

import json
import shutil
from pathlib import Path

import pytest

from y_web.src.system import prompt_packs as pp


@pytest.fixture
def packs(tmp_path, monkeypatch):
    root = tmp_path / "prompts"
    (root / "en").mkdir(parents=True)
    (root / "xx").mkdir()
    (root / "en/manifest.json").write_text(json.dumps({"language": "en", "name": "English"}))
    (root / "xx/manifest.json").write_text(json.dumps({"language": "xx", "name": "Xish", "native_name": "Xx"}))
    (root / "en/prompts.json").write_text(json.dumps({"a": "Hello {who}", "n": {"b": "B", "c": "C"}}))
    (root / "xx/prompts.json").write_text(json.dumps({"a": "Ciao {who}", "n": {"b": "BB"}}))
    monkeypatch.setattr(pp, "packs_root", lambda: root)
    return root


def test_languages_lists_english_first(packs):
    assert [x["code"] for x in pp.languages()] == ["en", "xx"]
    assert pp.languages()[1]["native_name"] == "Xx"


def test_normalize_and_resolve_never_trust_the_input(packs):
    assert pp.normalize("XX") == "xx"
    for bad in ("", None, "zz", "../etc", "en/../xx"):
        assert pp.normalize(bad) == "en"
    assert pp.resolve("zz", "xx") == "xx"
    assert pp.resolve("xx", "en") == "xx"
    assert pp.resolve(None, None) == "en"


def test_missing_keys_fall_back_to_english_at_any_depth(packs, caplog):
    with caplog.at_level("WARNING"):
        data = pp.load_pack("prompts.json", "xx")
    assert data == {"a": "Ciao {who}", "n": {"b": "BB", "c": "C"}}
    assert any("fall back to English" in r.getMessage() for r in caplog.records)


def test_a_file_missing_in_a_language_uses_english(packs):
    (packs / "en/other.json").write_text(json.dumps({"z": "Z"}))
    assert pp.load_pack("other.json", "xx") == {"z": "Z"}


def test_english_is_copied_byte_for_byte_and_others_written_merged(packs, tmp_path):
    out = tmp_path / "out.json"
    pp.write_pack("prompts.json", out, "en")
    assert out.read_bytes() == (packs / "en/prompts.json").read_bytes()
    pp.write_pack("prompts.json", out, "xx")
    assert json.loads(out.read_text())["n"] == {"b": "BB", "c": "C"}


def test_the_shipped_english_pack_matches_its_manifest():
    root = Path(__file__).resolve().parents[2] / "data_schema" / "prompts" / "en"
    manifest = json.loads((root / "manifest.json").read_text())
    assert set(manifest["files"]) == set(pp.PACK_FILES)
    assert all((root / name).exists() for name in manifest["files"])
