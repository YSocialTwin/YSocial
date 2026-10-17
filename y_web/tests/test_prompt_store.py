"""Prompts moved out of the code (step 1 of the multilingual prompts task): store behaviour and call-site contract."""

import ast
from pathlib import Path

import pytest

from y_web import prompt_store as ps

PKG = Path(ps.__file__).parent


def test_render_replaces_only_named_fields_and_keeps_other_braces():
    text = 'Answer as {"tone": "x"} for {name}.'
    assert ps.render(text, name="Ann") == 'Answer as {"tone": "x"} for Ann.'


def test_render_raises_when_a_named_field_is_missing_and_ignores_extras():
    with pytest.raises(ps.PromptError):
        ps.render("Hi {who}")
    assert ps.render("Hi", who="x") == "Hi"


def test_unknown_key_raises_and_other_languages_fall_back_to_english():
    with pytest.raises(ps.PromptError):
        ps.get("no_such_key")
    key = "_routes__api_interview_send_message__1"
    assert ps.get(key, "zz") == ps.get(key, "en")


def test_values_are_rendered_like_an_f_string():
    out = ps.prompt("_routes__api_interview_send_message__1", persona="<persona>")
    for f in ['persona']:
        assert "<" + f + ">" in out


def _calls():
    for path in PKG.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "prompt_store"
                and node.func.attr in ("get", "prompt")
                and node.args
                and isinstance(node.args[0], ast.Constant)
            ):
                yield path.name, node


def test_every_call_site_uses_an_existing_key_and_matching_fields():
    seen = 0
    for fname, node in _calls():
        key = node.args[0].value
        template = ps.get(key)  # raises PromptError when the key is missing
        seen += 1
        if node.func.attr == "prompt":
            passed = {k.arg for k in node.keywords if k.arg}
            assert passed == ps.fields_of(template), f"{fname}: {key}"
    assert seen > 0


def test_render_follows_paths_items_joins_and_formats_without_evaluating():
    class Agent:
        age = 30
        _secret = "x"

    out = ps.render(
        "{self.age} {article['title']} {', '.join(tags)} {score:.2f} {\"a\": 1}",
        self=Agent(),
        article={"title": "T"},
        tags=["a", "b"],
        score=0.5,
    )
    assert out == '30 T a, b 0.50 {"a": 1}'
    with pytest.raises(ps.PromptError):
        ps.render("{self._secret}", self=Agent())
    with pytest.raises(ps.PromptError):
        ps.render("{missing.name}")
    assert ps.render("{self.upper()}", self="x") == "{self.upper()}"


def test_other_languages_use_their_file_and_fall_back_per_key(tmp_path, monkeypatch, caplog):
    import json

    en = {"a": "Hello {who}", "b": "Only English"}
    (tmp_path / "prompts_internal.json").write_text(json.dumps(en))
    (tmp_path / "prompts_internal.xx.json").write_text(json.dumps({"a": "Ciao {who}"}))
    monkeypatch.setattr(ps, "PACK_FILE", tmp_path / "prompts_internal.json")
    monkeypatch.setattr(ps, "_cache", {})
    monkeypatch.setattr(ps, "_warned", set())
    assert ps.prompt("a", "xx", who="Ann") == "Ciao Ann"
    with caplog.at_level("WARNING"):
        assert ps.get("b", "xx") == "Only English"
        assert ps.get("b", "xx") == "Only English"
    assert len([r for r in caplog.records if "no 'xx' text" in r.getMessage()]) == 1
    assert ps.get("a", "yy") == "Hello {who}"  # language without a file
    assert ps.get("a", "../etc") == "Hello {who}"  # never used as a path
    ps.set_language("xx")
    try:
        assert ps.prompt("a", who="Ann") == "Ciao Ann"
    finally:
        ps.set_language("en")


def test_italian_pack_is_complete_and_translated():
    import json
    import pathlib

    here = pathlib.Path(ps.__file__).parent
    en = json.loads((here / "prompts_internal.json").read_text(encoding="utf-8"))
    it = json.loads((here / "prompts_internal.it.json").read_text(encoding="utf-8"))
    assert set(en) == set(it)
    assert sum(1 for k in en if en[k] != it[k]) >= len(en) * 0.8
    # English is the default and is never altered by the presence of other packs
    assert ps.get(next(iter(en)), "en") == en[next(iter(en))]


@pytest.fixture
def clean_language(monkeypatch):
    for name in (ps.ENV_VAR, ps.FOLDER_VAR):  # set then delete, so the original (absent) state is restored
        monkeypatch.setenv(name, "x")
        monkeypatch.delenv(name)
    monkeypatch.setattr(ps, "_language", None)
    monkeypatch.setattr(ps, "_values", {})
    yield
    monkeypatch.undo()


def _run_folder(tmp_path, experiment="it", clients=None):
    import json

    (tmp_path / "prompt_language.json").write_text(
        json.dumps({"experiment": experiment, "clients": clients or {}}), encoding="utf-8"
    )
    (tmp_path / "profile_values.it.json").write_text(
        json.dumps({"nationality": {"American": "statunitense"}, "gender": {"male": "uomo"}, "leaning": {"centrist": "centrista"}}),
        encoding="utf-8",
    )
    return tmp_path


def test_language_is_english_unless_a_folder_or_the_environment_says_otherwise(clean_language, tmp_path):
    assert ps.current_language() == "en"
    assert ps.language_from_folder(tmp_path) == "en"
    folder = _run_folder(tmp_path, "it", {"c2": "en"})
    assert ps.language_from_folder(folder) == "it"
    assert ps.language_from_folder(folder, "c2") == "en"
    assert ps.language_from_folder(folder, "other") == "it"


def test_set_language_reaches_other_copies_through_the_environment(clean_language, monkeypatch):
    import os

    ps.set_language("it")
    assert os.environ[ps.ENV_VAR] == "it"
    monkeypatch.setattr(ps, "_language", None)  # a copy of the module that was never told
    assert ps.current_language() == "it"


def test_environment_language_wins_over_the_record(clean_language, tmp_path, monkeypatch):
    folder = _run_folder(tmp_path, "it")
    monkeypatch.setenv(ps.ENV_VAR, "en")
    assert ps.use_language_from_folder(folder) == "en"
    assert ps.localize(object()) is not None


def test_profile_values_read_in_the_prompt_language_without_touching_the_agent(clean_language, tmp_path):
    class Agent:
        nationality = "American"
        gender = "male"
        leaning = "centrist"
        profession = "Astronaut"  # no translation: stays as it is
        age = 31

    agent = Agent()
    assert ps.localize(agent) is agent  # English: the object itself
    assert ps.use_language_from_folder(_run_folder(tmp_path, "it")) == "it"
    view = ps.localize(agent)
    assert (view.nationality, view.gender, view.leaning) == ("statunitense", "uomo", "centrista")
    assert (view.profession, view.age) == ("Astronaut", 31)
    assert agent.nationality == "American"
    text = ps.render("{self.gender} {self.nationality}, {self.age}", self=view)
    assert text == "uomo statunitense, 31"
    attrs = {"nationality": "American", "political_leaning": "centrist", "name": "Ann"}
    assert ps.localize_attrs(attrs) == {"nationality": "statunitense", "political_leaning": "centrista", "name": "Ann"}
    assert attrs["nationality"] == "American"
    assert ps.env_for_workers()[ps.ENV_VAR] == "it"


def test_english_runs_pass_nothing_to_workers(clean_language, tmp_path):
    ps.use_language_from_folder(_run_folder(tmp_path, "en"))
    assert ps.env_for_workers() == {}


def test_single_values_such_as_the_follow_action_are_localized(clean_language, tmp_path):
    import json

    folder = _run_folder(tmp_path, "it")
    (folder / "profile_values.it.json").write_text(
        json.dumps({"action": {"follow": "seguire", "unfollow": "smettere di seguire"}}), encoding="utf-8"
    )
    assert ps.localize_value("action", "follow") == "follow"  # English until a language is active
    ps.use_language_from_folder(folder)
    assert ps.localize_value("action", "follow") == "seguire"
    assert ps.localize_value("action", "unknown") == "unknown"
    assert ps.localize_value("nope", "follow") == "follow"
