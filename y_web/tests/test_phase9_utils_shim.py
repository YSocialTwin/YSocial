"""
Phase 9 validation tests — final utils shim cleanup.

Verifies that:
- Canonical src imports work for the final refactoring layout
- Legacy utils/reddit/recsys/llm shims still import correctly
- y_web.utils shims advertise deprecation warnings
- Internal callers no longer import legacy y_web.utils paths
- execution_backend is canonical in src/ while preserving legacy shim behavior
"""

from __future__ import annotations

import importlib
import re
import sys
import warnings
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
Y_WEB_DIR = REPO_ROOT / "y_web"
UTILS_DIR = Y_WEB_DIR / "utils"
ROUTES_DIR = Y_WEB_DIR / "routes"
SRC_DIR = Y_WEB_DIR / "src"

LEGACY_IMPORT_RE = re.compile(r"^\s*from y_web\.utils(?:\.|\s+import)", re.MULTILINE)
OLD_SRC_IMPORT_RE = re.compile(
    r"^\s*from y_web\.(?:utils|llm_annotations|recsys_support)(?:\.|\s+import)",
    re.MULTILINE,
)


def test_phase9_legacy_imports_work():
    from y_web.src.data_access import get_trending_hashtags, get_user_recent_posts
    from y_web.src.llm import Annotator, ContentAnnotator
    from y_web.src.models import Admin_users, Post, Profession, User_mgmt
    from y_web.src.recsys import get_suggested_posts, get_suggested_users
    from y_web.src.forum.actions import apply_vote, create_post_reddit
    from y_web.src.forum.service import fetch_feed_page, serialize_feed_posts
    from y_web.src.telemetry.usage_data import Telemetry
    from y_web.src.agents.population import generate_population_from_config
    from y_web.src.experiment.access import user_can_view_experiment
    from y_web.utils.external_processes import start_client, start_server
    from y_web.utils.log_metrics import update_client_log_metrics

    assert callable(generate_population_from_config)
    assert callable(user_can_view_experiment)
    assert callable(start_server)
    assert callable(start_client)
    assert callable(update_client_log_metrics)
    assert callable(get_suggested_posts)
    assert callable(get_suggested_users)
    assert callable(create_post_reddit)
    assert callable(apply_vote)
    assert callable(fetch_feed_page)
    assert callable(serialize_feed_posts)
    assert Annotator is not None
    assert ContentAnnotator is not None
    assert Telemetry is not None
    assert User_mgmt is not None
    assert Post is not None
    assert Admin_users is not None
    assert Profession is not None
    assert callable(get_user_recent_posts)
    assert callable(get_trending_hashtags)


def test_phase9_canonical_imports_work():
    from y_web.src.agents.population import generate_population_from_config
    from y_web.src.data_access.posts import get_user_recent_posts
    from y_web.src.data_access.trends import get_trending_hashtags
    from y_web.src.experiment.context import setup_experiment_context
    from y_web.src.forum.actions import apply_vote, create_post_reddit
    from y_web.src.forum.service import fetch_feed_page, serialize_feed_posts
    from y_web.src.hpc.log_metrics import update_client_log_metrics
    from y_web.src.llm import Annotator, ContentAnnotator
    from y_web.src.models.admin import Admin_users, Exps
    from y_web.src.models.config import Education, Profession
    from y_web.src.models.experiment import Post, User_mgmt
    from y_web.src.recsys import get_suggested_posts, get_suggested_users
    from y_web.src.simulation import start_client, start_server
    from y_web.src.telemetry.usage_data import Telemetry

    assert callable(generate_population_from_config)
    assert callable(get_user_recent_posts)
    assert callable(get_trending_hashtags)
    assert callable(setup_experiment_context)
    assert callable(start_server)
    assert callable(start_client)
    assert callable(update_client_log_metrics)
    assert callable(create_post_reddit)
    assert callable(apply_vote)
    assert callable(fetch_feed_page)
    assert callable(serialize_feed_posts)
    assert callable(get_suggested_posts)
    assert callable(get_suggested_users)
    assert Annotator is not None
    assert ContentAnnotator is not None
    assert Telemetry is not None
    assert User_mgmt is not None
    assert Post is not None
    assert Admin_users is not None
    assert Exps is not None
    assert Profession is not None
    assert Education is not None


@pytest.mark.parametrize("shim_file", sorted(UTILS_DIR.glob("*.py")), ids=lambda p: p.name)
def test_utils_shims_declare_deprecation_warning(shim_file: Path):
    text = shim_file.read_text()
    assert "warnings.warn(" in text
    assert "DeprecationWarning" in text


@pytest.mark.parametrize(
    "module_name",
    ["y_web.utils", "y_web.utils.execution_backend", "y_web.utils.external_processes"],
)
def test_utils_shims_emit_deprecation_warning_on_reload(module_name: str):
    module = importlib.import_module(module_name)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        importlib.reload(module)
    assert any(item.category is DeprecationWarning for item in caught)


def test_routes_have_no_legacy_utils_imports():
    for path in ROUTES_DIR.rglob("*.py"):
        assert not LEGACY_IMPORT_RE.search(path.read_text()), path


def test_y_web_init_has_no_legacy_utils_imports():
    init_path = Y_WEB_DIR / "__init__.py"
    assert not LEGACY_IMPORT_RE.search(init_path.read_text())


def test_src_tree_uses_canonical_imports():
    for path in SRC_DIR.rglob("*.py"):
        text = path.read_text()
        assert not OLD_SRC_IMPORT_RE.search(text), path


def test_execution_backend_shim_identity():
    from y_web.src.simulation.execution_backend import start_server_for_experiment as canonical
    from y_web.src.simulation.execution_backend import start_server_for_experiment as shim

    assert shim is canonical


def test_canonical_execution_backend_honors_legacy_shim_monkeypatch(monkeypatch):
    import y_web.utils.execution_backend as legacy_module
    from y_web.src.simulation.execution_backend import start_server_for_experiment

    exp = SimpleNamespace(simulator_type="Standard")
    mock_start = MagicMock(return_value="patched-server")
    monkeypatch.setattr(legacy_module, "start_server", mock_start)

    assert start_server_for_experiment(exp) == "patched-server"
    mock_start.assert_called_once_with(exp)


def test_execution_backend_canonical_module_is_in_sys_modules_after_shim_import():
    import y_web.utils.execution_backend  # noqa: F401

    assert "y_web.src.simulation.execution_backend" in sys.modules
