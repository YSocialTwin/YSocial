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
    assert ps.get(key, "it") == ps.get(key, "en")


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
