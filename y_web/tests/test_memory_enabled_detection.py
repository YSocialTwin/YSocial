"""
Tests for the memory-enabled detection logic used to show/hide the Interview
link in both the microblogging and forum interfaces.

Covers the two bug-fixes introduced to handle:
  1. Flat config format: {"memory_enabled": true, ...}  (written by clients_routes.py)
  2. Forum client-config fallback: _experiment_memory_enabled now also walks
     client_*.json files for forum experiments, just as it already did for
     microblogging.
"""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers — build minimal config files in a temp directory
# ---------------------------------------------------------------------------


def _make_exp_dir(config_server_data=None, client_files=None):
    """
    Create a temporary directory structure that mimics an experiment folder:

        <tmpdir>/
            config_server.json     (optional)
            client_1.json          (optional, list of dicts)
            ...

    Returns (tmpdir_path, config_server_path).
    """
    tmp = tempfile.mkdtemp()
    cfg_path = os.path.join(tmp, "config_server.json")
    if config_server_data is not None:
        with open(cfg_path, "w") as fh:
            json.dump(config_server_data, fh)
    if client_files:
        for i, client_data in enumerate(client_files, start=1):
            client_path = os.path.join(tmp, f"client_{i}.json")
            with open(client_path, "w") as fh:
                json.dump(client_data, fh)
    return tmp, cfg_path


def _mock_exp(platform_type="forum", db_name="experiments/test-uid-123"):
    exp = MagicMock()
    exp.platform_type = platform_type
    exp.db_name = db_name
    return exp


# ---------------------------------------------------------------------------
# Unit tests for _experiment_memory_enabled (main.py)
# ---------------------------------------------------------------------------


def _call_experiment_memory_enabled(exp_dir_path, platform_type="forum"):
    """
    Call _experiment_memory_enabled with the DB mocked and the filesystem
    redirected to *exp_dir_path* (a real directory containing config_server.json
    and any client_*.json files).

    Uses a UID of "test-uid-xyz" and sets exp.db_name = "experiments/test-uid-xyz"
    so that the uid-extraction inside the function produces the right value.
    The function's base-dir derivation (os.path.dirname(os.path.abspath(__file__)))
    is patched to point one level *above* exp_dir_path, so the constructed path
    resolves to the real temp directory.
    """
    from y_web.routes.social.helpers import _experiment_memory_enabled  # noqa: PLC0415

    uid = "test-uid-xyz"
    # exp_dir_path is e.g. /tmp/abc/experiments/test-uid-xyz
    # The function builds: os.path.join(base_dir, "experiments", uid, "config_server.json")
    # We set base_dir = parent of the "experiments" subfolder inside exp_dir_path
    base_dir = os.path.dirname(os.path.dirname(exp_dir_path))  # two levels up

    mock_exp = MagicMock()
    mock_exp.platform_type = platform_type
    mock_exp.db_name = f"experiments/{uid}"

    with patch("y_web.routes.social.helpers.Exps") as mock_exps:
        mock_exps.query.filter_by.return_value.first.return_value = mock_exp
        # Redirect the base-dir to our tmpdir so all paths resolve correctly
        with patch(
            "y_web.routes.social.helpers.os.path.abspath",
            return_value=os.path.join(base_dir, "helpers.py"),
        ):
            return _experiment_memory_enabled(1)


@pytest.fixture()
def exp_tmpdir(tmp_path):
    """
    Provides a helper that creates a real experiment directory under tmp_path
    and returns (exp_dir, write_config, write_client) callables.
    """
    uid = "test-uid-xyz"
    exp_dir = tmp_path / "experiments" / uid
    exp_dir.mkdir(parents=True)

    def write_config(data):
        (exp_dir / "config_server.json").write_text(json.dumps(data))

    def write_client(index, data):
        (exp_dir / f"client_{index}.json").write_text(json.dumps(data))

    return exp_dir, write_config, write_client


class TestExperimentMemoryEnabledMainPy:
    """Integration tests for y_web.routes.social.helpers._experiment_memory_enabled."""

    # -- nested format (already worked, regression guard) --------------------

    def test_nested_format_true(self, exp_tmpdir):
        """config_server.json: {"memory": {"enabled": true}} → True."""
        exp_dir, write_config, _ = exp_tmpdir
        write_config({"memory": {"enabled": True}})
        assert _call_experiment_memory_enabled(str(exp_dir), "forum") is True

    def test_nested_format_false(self, exp_tmpdir):
        """config_server.json: {"memory": {"enabled": false}} → False (no client files)."""
        exp_dir, write_config, _ = exp_tmpdir
        write_config({"memory": {"enabled": False}})
        assert _call_experiment_memory_enabled(str(exp_dir), "forum") is False

    # -- flat format in config_server.json (new) -----------------------------

    def test_flat_format_config_server_forum(self, exp_tmpdir):
        """config_server.json flat {"memory_enabled": true} → True for forum."""
        exp_dir, write_config, _ = exp_tmpdir
        write_config({"memory_enabled": True})
        assert _call_experiment_memory_enabled(str(exp_dir), "forum") is True

    def test_flat_format_config_server_microblogging(self, exp_tmpdir):
        """config_server.json flat {"memory_enabled": true} → True for microblogging."""
        exp_dir, write_config, _ = exp_tmpdir
        write_config({"memory_enabled": True})
        assert _call_experiment_memory_enabled(str(exp_dir), "microblogging") is True

    def test_flat_format_config_server_false_no_clients(self, exp_tmpdir):
        """Flat {"memory_enabled": false} with no client files → False."""
        exp_dir, write_config, _ = exp_tmpdir
        write_config({"memory_enabled": False})
        assert _call_experiment_memory_enabled(str(exp_dir), "forum") is False

    # -- flat format in forum client config files (new) ----------------------

    def test_forum_client_file_flat_memory_enabled(self, exp_tmpdir):
        """Forum client_1.json with flat "memory_enabled": true → True."""
        exp_dir, write_config, write_client = exp_tmpdir
        write_config({"memory": {"enabled": False}})
        write_client(
            1,
            {
                "memory_enabled": True,
                "memory_pair_limit": 5,
                "forum_post_structure_strict": True,
            },
        )
        assert _call_experiment_memory_enabled(str(exp_dir), "forum") is True

    def test_forum_client_file_flat_memory_disabled(self, exp_tmpdir):
        """Forum client_1.json with "memory_enabled": false → False."""
        exp_dir, write_config, write_client = exp_tmpdir
        write_config({})
        write_client(1, {"memory_enabled": False})
        assert _call_experiment_memory_enabled(str(exp_dir), "forum") is False

    # -- microblogging nested agents format still works (regression guard) ---

    def test_microblogging_client_agents_nested(self, exp_tmpdir):
        """Microblogging client_1.json: {"agents": {"memory_enabled": true}} → True."""
        exp_dir, write_config, write_client = exp_tmpdir
        write_config({})
        write_client(1, {"agents": {"memory_enabled": True}})
        assert _call_experiment_memory_enabled(str(exp_dir), "microblogging") is True

    def test_user_reported_flat_config_as_client_file(self, exp_tmpdir):
        """The exact user-reported flat config in a forum client file → True."""
        exp_dir, write_config, write_client = exp_tmpdir
        write_config({})
        write_client(
            1,
            {
                "memory_enabled": True,
                "memory_pair_limit": 5,
                "memory_prompt_max_chars": 1600,
                "memory_prompt_mode": "subtle_forum",
                "forum_post_structure_strict": True,
            },
        )
        assert _call_experiment_memory_enabled(str(exp_dir), "forum") is True


# ---------------------------------------------------------------------------
# Functional / logic tests that don't depend on the DB layer
# ---------------------------------------------------------------------------


class TestMemoryEnabledLogicDirect:
    """
    Test the config-parsing logic directly, without needing a DB.
    This exercises the same branches as _experiment_memory_enabled but via
    direct config inspection, making the tests simpler and faster.
    """

    @staticmethod
    def _is_memory_enabled_in_config(config: dict) -> bool:
        """Mirror the logic added in _experiment_memory_enabled."""
        memory_cfg = config.get("memory")
        if isinstance(memory_cfg, dict) and "enabled" in memory_cfg:
            if bool(memory_cfg.get("enabled")):
                return True
        # Flat format
        if bool(config.get("memory_enabled", False)):
            return True
        return False

    @staticmethod
    def _is_memory_enabled_in_client(client_config: dict) -> bool:
        """Mirror client-file checking logic."""
        agents_cfg = client_config.get("agents")
        if isinstance(agents_cfg, dict) and bool(agents_cfg.get("memory_enabled")):
            return True
        if bool(client_config.get("memory_enabled", False)):
            return True
        return False

    # -- config_server.json scenarios ----------------------------------------

    def test_nested_enabled(self):
        assert self._is_memory_enabled_in_config({"memory": {"enabled": True}})

    def test_nested_disabled(self):
        assert not self._is_memory_enabled_in_config({"memory": {"enabled": False}})

    def test_nested_missing_enabled_key(self):
        assert not self._is_memory_enabled_in_config({"memory": {}})

    def test_flat_enabled(self):
        assert self._is_memory_enabled_in_config({"memory_enabled": True})

    def test_flat_disabled(self):
        assert not self._is_memory_enabled_in_config({"memory_enabled": False})

    def test_flat_missing(self):
        assert not self._is_memory_enabled_in_config({})

    def test_nested_takes_priority_over_flat(self):
        """Nested enabled=True should still win even if flat key is absent."""
        cfg = {"memory": {"enabled": True}}
        assert self._is_memory_enabled_in_config(cfg)

    def test_both_nested_false_flat_true(self):
        """Flat key can enable memory even when nested dict says False."""
        cfg = {"memory": {"enabled": False}, "memory_enabled": True}
        assert self._is_memory_enabled_in_config(cfg)

    # -- client config file scenarios ----------------------------------------

    def test_client_agents_nested_enabled(self):
        assert self._is_memory_enabled_in_client({"agents": {"memory_enabled": True}})

    def test_client_agents_nested_disabled(self):
        assert not self._is_memory_enabled_in_client(
            {"agents": {"memory_enabled": False}}
        )

    def test_client_flat_enabled(self):
        """Forum-style flat client config."""
        client = {
            "memory_enabled": True,
            "memory_pair_limit": 5,
            "forum_post_structure_strict": True,
        }
        assert self._is_memory_enabled_in_client(client)

    def test_client_flat_disabled(self):
        assert not self._is_memory_enabled_in_client({"memory_enabled": False})

    def test_client_no_memory_key(self):
        assert not self._is_memory_enabled_in_client({"other_key": "value"})

    def test_user_reported_config(self):
        """The exact flat config snippet reported by the user must be detected."""
        user_config = {
            "memory_enabled": True,
            "memory_pair_limit": 5,
            "memory_prompt_max_chars": 1600,
            "memory_social_decay_lambda": 0.05,
            "memory_social_corruption_rate": 0.02,
            "memory_social_resummarize_every_events": 4,
            "memory_thread_decay_lambda": 0.03,
            "memory_thread_corruption_rate": 0.01,
            "memory_thread_resummarize_every_events": 4,
            "memory_evidence_tail_max": 8,
            "memory_digest_update_cadence_rounds": 3,
            "memory_digest_events_limit": 80,
            "memory_cold_start_window": 5,
            "memory_semantic_enabled": True,
            "memory_search_k": 8,
            "memory_search_max_chars": 900,
            "memory_search_time_window_rounds": 40,
            "memory_tier_a_max_chars": 350,
            "memory_tier_b_max_chars": 900,
            "memory_tier_c_max_chars": 900,
            "memory_total_max_chars": 2200,
            "memory_tier_c_uncertainty_threshold": 0.45,
            "memory_reflection_cadence_rounds": 3,
            "memory_reflection_min_events": 12,
            "memory_reflection_trigger_importance_sum": 3.5,
            "memory_reflection_max_items_per_run": 60,
            "memory_embedding_model": "snowflake-arctic-embed:110m",
            "memory_embedding_async": False,
            "memory_importance_mode": "heuristic_then_batch_llm",
            "memory_prompt_mode": "subtle_forum",
            "memory_reply_context_max_chars": 280,
            "memory_vote_signal_only": True,
            "forum_post_structure_strict": True,
            "memory_cross_thread_callback_min_score": 0.8,
        }
        # Should be detected both as config_server.json flat format ...
        assert self._is_memory_enabled_in_config(
            user_config
        ), "User-reported config with flat 'memory_enabled: true' must be detected"
        # ... and as a client config flat format
        assert self._is_memory_enabled_in_client(
            user_config
        ), "User-reported config detected as client file flat format"
