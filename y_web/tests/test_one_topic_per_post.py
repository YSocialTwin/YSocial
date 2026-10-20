"""Posts are generated and tagged with exactly one topic (clients)."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "external"
FILES = [
    "YClient/y_client/classes/base_agent.py",
    "YClient/y_client/classes/fake_base_agent.py",
    "YClientReddit/y_client/classes/base_agent.py",
    "YClientReddit/y_client/classes/fake_base_agent.py",
]


@pytest.mark.parametrize("rel", FILES)
def test_single_interest_selected(rel):
    p = ROOT / rel
    if not p.exists():
        pytest.skip("external repo not present")
    src = p.read_text()
    assert "exactly one topic per post" in src
    assert "np.random.randint(1, 3)" not in src
