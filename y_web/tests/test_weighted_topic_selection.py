"""Topic of a post: one topic, probability ~ count over a moving window (count > 0 only)."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

EXT = Path(__file__).resolve().parents[2] / "external"
A = EXT / "YClient/y_client/topic_sampling.py"
B = EXT / "YClientReddit/y_client/topic_sampling.py"

pytestmark = pytest.mark.unit

if not A.exists():
    pytest.skip("external repos absent", allow_module_level=True)


def _load():
    spec = importlib.util.spec_from_file_location("ts_a", A)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.pick_topic_index


def test_copies_identical():
    assert A.read_text() == B.read_text()


def test_empty_and_single():
    pick = _load()
    assert pick([]) is None
    assert pick([{"id": 1, "topic": "x", "count": 3}]) == 0


def test_probability_proportional_to_count_and_zero_excluded():
    pick = _load()
    rng = np.random.RandomState(0)
    data = [{"count": 9}, {"count": 1}, {"count": 0}]
    picks = [pick(data, rng) for _ in range(5000)]
    assert 2 not in picks  # no interaction in the window -> never chosen
    assert 0.06 < picks.count(1) / len(picks) < 0.14  # ~1/10


def test_all_zero_gives_none():
    assert _load()([{"count": 0}]) is None


def test_missing_count_is_uniform():
    pick = _load()
    rng = np.random.RandomState(1)
    picks = [pick([{}, {}], rng) for _ in range(2000)]
    assert 0.4 < picks.count(0) / 2000 < 0.6


def test_servers_return_count_and_window_is_moving():
    for rel in ("YServer", "YServerReddit"):
        src = (EXT / rel / "y_server/routes/user_managment.py").read_text()
        assert '"count": int(interest[2])' in src
        assert "base_rounds = max(0, round_id - time_window)" in src


def test_servers_do_not_truncate_to_n_interests():
    for rel in ("YServer", "YServerReddit"):
        src = (EXT / rel / "y_server/routes/user_managment.py").read_text()
        assert ".limit(n_interests)" not in src


def test_hpc_selectors_use_counts():
    base = EXT / "YSimulator/YSimulator/YClient"
    for rel in ("agent_management/agent_selector.py", "agent_manager.py"):
        src = (base / rel).read_text()
        assert "weights=counts" in src
