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


def test_the_language_is_recorded_in_the_experiment_folder(packs, tmp_path):
    folder = tmp_path / "exp"
    pp.record_language(folder, experiment="xx")
    pp.record_language(folder, client="c1", client_language="zz")
    data = json.loads((folder / "prompt_language.json").read_text())
    assert data == {"experiment": "xx", "clients": {"c1": "en"}}


def _render_selector(languages, scope):
    from jinja2 import Environment, FileSystemLoader

    root = Path(__file__).resolve().parents[1] / "templates"
    env = Environment(loader=FileSystemLoader(str(root)))
    env.globals["_"] = lambda text: text
    return env.get_template("admin/_prompt_language.html").render(
        prompt_languages=languages, prompt_scope=scope
    )


def test_the_selector_appears_only_with_more_than_one_language():
    one = [{"code": "en", "native_name": "English"}]
    two = one + [{"code": "it", "native_name": "Italiano"}]
    assert "prompt_language" not in _render_selector(one, "experiment")
    html = _render_selector(two, "experiment")
    assert 'name="prompt_language"' in html and 'value="it"' in html
    assert 'value=""' not in html
    assert 'value=""' in _render_selector(two, "client")


def test_profile_values_are_written_per_language_in_the_run_folder(tmp_path):
    pp.record_language(tmp_path, experiment="it", client="c1", client_language="en")
    values = json.loads((tmp_path / "profile_values.it.json").read_text(encoding="utf-8"))
    assert values["nationality"]["American"] == "statunitense"
    assert not (tmp_path / "profile_values.en.json").exists()


def test_launch_env_names_the_language_only_when_it_is_not_english():
    class Obj:
        def __init__(self, language):
            self.prompt_language = language

    assert pp.launch_env(Obj("en"), Obj(None)) == {}
    assert pp.launch_env(Obj("it"), Obj(None)) == {"YSOCIAL_PROMPT_LANGUAGE": "it"}
    assert pp.launch_env(Obj("it"), Obj("en")) == {}
    assert pp.launch_env(Obj("zz"), Obj(None)) == {}


def test_a_run_folder_in_italian_makes_the_client_prompt_in_italian(tmp_path, monkeypatch):
    from y_web import prompt_store as ps

    for name in (ps.ENV_VAR, ps.FOLDER_VAR):
        monkeypatch.setenv(name, "x")
        monkeypatch.delenv(name)
    monkeypatch.setattr(ps, "_language", None)
    monkeypatch.setattr(ps, "_values", {})
    pp.write_pack("prompts.json", tmp_path / "prompts.json", "it")
    pp.record_language(tmp_path, experiment="it")
    assert ps.use_language_from_folder(tmp_path) == "it"

    class Agent:
        name, age, gender, nationality, profession = "Ann", 31, "female", "American", "Doctor"
        leaning, oe, co, ex, ag, ne = "centrist", "inventive/curious", "organized", "outgoing", "friendly", "calm"
        education_level, toxicity, language = "master", "low", "English"
        topics_opinions = topics_sentiment = ""

    template = json.loads((tmp_path / "prompts.json").read_text(encoding="utf-8"))["agent_roleplay"]
    text = ps.render(template, self=ps.localize(Agent()), interest=["music"], interests=["music"])
    assert "donna" in text and "statunitense" in text and "female" not in text and "American" not in text


def test_the_language_switch_appears_only_with_more_than_one_language():
    from jinja2 import Environment, FileSystemLoader

    root = Path(__file__).resolve().parents[1] / "templates"
    env = Environment(loader=FileSystemLoader(str(root)))
    env.globals["_"] = lambda text: text

    class Exp:
        idexp, prompt_language = 7, "it"

    render = lambda langs: env.get_template("admin/_prompt_language_switch.html").render(
        prompt_languages=langs, experiment=Exp()
    )
    one = [{"code": "en", "native_name": "English"}]
    two = one + [{"code": "it", "native_name": "Italiano"}]
    assert "prompts_language" not in render(one)
    html = render(two)
    assert "/admin/prompts_language/7" in html and 'value="it" selected' in html
    assert "confirm(" in html
