"""Every ``protocol_tokens.<NAME>`` the code reads must exist in ``protocol_tokens.py``.

Regression: the forum client read ``protocol_tokens.NEWS`` which the module did not define, so every agent
action failed with ``AttributeError`` (the token is a legacy alias of SHARE_LINK).
"""

import importlib.util
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
TOKENS = ROOT / "external" / "YClient" / "y_client" / "protocol_tokens.py"
COPIES = [
    ROOT / "external" / "YClientReddit" / "y_client" / "protocol_tokens.py",
    ROOT / "external" / "YSimulator" / "YSimulator" / "protocol_tokens.py",
]
REPOS = [
    "YClient",
    "YClientReddit",
    "YSimulator",
    "YPhotoSharing",
    "y_agents_plugins",
    "reactive_agents",
    "y_memory_subsystem",
]
USE = re.compile(r"\bprotocol_tokens\.([A-Z][A-Z_]*)\b")

if not TOKENS.exists():
    pytest.skip("YClient is not installed", allow_module_level=True)


def _load(path):
    spec = importlib.util.spec_from_file_location("protocol_tokens_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_copies_are_identical():
    text = TOKENS.read_text(encoding="utf-8")
    for copy in COPIES:
        if copy.exists():
            assert copy.read_text(encoding="utf-8") == text, f"{copy} differs from {TOKENS}"


def test_every_token_used_in_code_is_defined():
    defined = set(dir(_load(TOKENS)))
    missing = {}
    for repo in REPOS:
        base = ROOT / "external" / repo
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if any(part in {".venv", "node_modules", "tests", "test"} for part in path.parts):
                continue
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.lstrip().startswith("#"):
                    continue
                for name in USE.findall(line):
                    if name not in defined:
                        missing.setdefault(name, set()).add(f"{repo}/{path.name}")
    assert not missing, f"protocol_tokens has no: {missing}"


def test_news_is_a_legacy_alias_not_offered_to_the_model():
    module = _load(TOKENS)
    assert module.has_token("NEWS.", module.NEWS)
    assert module.NEWS not in module.ACTIONS
