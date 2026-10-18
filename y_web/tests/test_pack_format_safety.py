"""The user-editable templates of every shipped pack must be safe for str.format.

YSimulator fills ``system_template`` / ``user_template`` (``prompts_config``) with ``str.format`` so that custom
prompts keep their semantics. A stray brace in a shipped pack would crash a client at run time, so this fails
first. Flat prompts (a string per key) are rendered by the closed-list renderer and may hold literal braces.
"""

import json
import string
from pathlib import Path

import pytest

PACKS = Path(__file__).resolve().parents[2] / "data_schema" / "prompts"
FILES = sorted(PACKS.glob("*/prompts*.json"))
TEMPLATE_KEYS = ("system_template", "user_template")


def _templates(node, path=""):
    if isinstance(node, dict):
        for key, value in node.items():
            if key in TEMPLATE_KEYS and isinstance(value, str):
                yield f"{path}/{key}", value
            else:
                yield from _templates(value, f"{path}/{key}")


def test_packs_found():
    assert FILES
    assert any(_templates(json.loads(f.read_text(encoding="utf-8"))) for f in FILES)


@pytest.mark.parametrize("file", FILES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_templates_parse_with_str_format(file):
    data = json.loads(file.read_text(encoding="utf-8"))
    for path, text in _templates(data):
        try:
            fields = [f for _, f, _, _ in string.Formatter().parse(text) if f is not None]
        except ValueError as error:
            pytest.fail(f"{file.parent.name}/{file.name} {path}: {error}")
        for field in fields:
            root = field.replace("[", ".").split(".")[0]
            assert root.isidentifier(), f"{file.parent.name}/{file.name} {path}: unsupported field {{{field}}}"
