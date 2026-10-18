"""Rendering a prompt template with the closed-list renderer gives what the old f-string evaluation gave."""

import json
from pathlib import Path

import pytest

from y_web import prompt_store as ps

FILES = [
    Path(__file__).resolve().parents[2] / p
    for p in [
        "data_schema/prompts/en/prompts.json",
        "data_schema/prompts/en/prompts_forum.json",
        "data_schema/prompts/en/prompts_hpc.json",
        "data_schema/prompts/en/prompts_ygram.json",
    ]
]


class Probe:
    """Any attribute is a distinct text, so a wrong lookup shows."""

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return f"<{name}>"


def _templates():
    def walk(node, where):
        if isinstance(node, str):
            yield where, node
        elif isinstance(node, dict):
            for k, v in node.items():
                yield from walk(v, f"{where}/{k}")

    for path in FILES:
        if path.exists():
            yield from walk(json.loads(path.read_text(encoding="utf-8")), path.name)


@pytest.mark.parametrize("where,text", list(_templates()))
def test_render_matches_fstring_evaluation(where, text):
    scope = dict(
        self=Probe(),
        article={"title": "T", "summary": "S"},
        website=Probe(),
        interest=["a", "b"],
        interests=["a", "b"],
    )
    try:
        expected = eval(f'f"""{text}"""', dict(scope))
    except Exception:
        pytest.skip(
            "template is not evaluable on its own (fields supplied by the call site)"
        )
    assert ps.render(text, **scope) == expected
