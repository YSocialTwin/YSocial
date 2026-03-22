"""
Phase 9 validation tests — shim removal cleanup.

Verifies that:
- Canonical src imports work for the final refactoring layout
- Internal callers no longer import legacy pre-refactor paths
- Legacy shim files/packages have been removed
- execution_backend is fully canonical in src/
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
Y_WEB_DIR = REPO_ROOT / "y_web"
ROUTES_DIR = Y_WEB_DIR / "routes"
SRC_DIR = Y_WEB_DIR / "src"

LEGACY_IMPORT_RE = re.compile(
    r"^\s*from y_web\.(?:utils|models|data_access|experiment_context|llm_annotations|recsys_support|reddit|telemetry)(?:\.|\s+import)",
    re.MULTILINE,
)
LEGACY_SYMBOL_RE = re.compile(
    r"y_web\.(?:utils|models|data_access|experiment_context|llm_annotations|recsys_support|reddit|telemetry)"
)


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


def test_legacy_shim_files_removed():
    removed_paths = [
        Y_WEB_DIR / "models.py",
        Y_WEB_DIR / "data_access.py",
        Y_WEB_DIR / "experiment_context.py",
        Y_WEB_DIR / "utils",
        Y_WEB_DIR / "llm_annotations",
        Y_WEB_DIR / "recsys_support",
        Y_WEB_DIR / "reddit",
        Y_WEB_DIR / "telemetry",
    ]
    for path in removed_paths:
        assert not path.exists(), path


def test_routes_have_no_legacy_utils_imports():
    for path in ROUTES_DIR.rglob("*.py"):
        assert not LEGACY_IMPORT_RE.search(path.read_text()), path


def test_repo_uses_only_canonical_imports():
    for path in Y_WEB_DIR.rglob("*.py"):
        text = path.read_text()
        assert not LEGACY_IMPORT_RE.search(text), path


def test_execution_backend_is_canonical():
    from y_web.src.simulation.execution_backend import (
        start_client_for_experiment,
        start_server_for_experiment,
        stop_client_for_experiment,
        stop_server_for_experiment,
        uses_hpc_backend,
    )

    assert callable(uses_hpc_backend)
    assert callable(start_server_for_experiment)
    assert callable(stop_server_for_experiment)
    assert callable(start_client_for_experiment)
    assert callable(stop_client_for_experiment)
