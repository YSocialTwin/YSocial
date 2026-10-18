"""data_schema/prompts/protocol_tokens.json mirrors the clients' protocol_tokens.py (CI has no external repos)."""
import importlib.util
import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
REF = ROOT / "data_schema" / "prompts" / "protocol_tokens.json"


def _tokens(path):
    spec = importlib.util.spec_from_file_location("pt_ref_check", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {
        v for n, v in vars(module).items()
        if n.isupper() and isinstance(v, str) and re.fullmatch(r"[A-Z_]+", v)
    }


@pytest.mark.unit
def test_reference_list_is_well_formed():
    tokens = json.loads(REF.read_text(encoding="utf-8"))["tokens"]
    assert tokens == sorted(set(tokens)) and "COMMENT" in tokens and "NEWS" in tokens


@pytest.mark.integration
@pytest.mark.external_repo
@pytest.mark.parametrize("repo", ["YClient", "YClientReddit", "YSimulator"])
def test_reference_matches_each_client_copy(repo):
    sub = {"YClient": "y_client", "YClientReddit": "y_client", "YSimulator": "YSimulator"}[repo]
    path = ROOT / "external" / repo / sub / "protocol_tokens.py"
    if not path.exists():
        pytest.skip("external repo not present")
    assert _tokens(path) == set(json.loads(REF.read_text(encoding="utf-8"))["tokens"])
