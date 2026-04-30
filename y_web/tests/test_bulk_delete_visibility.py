"""Tests for bulk experiment delete visibility wiring."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_bulk_delete_route_passes_current_admin_user_to_visibility_resolver():
    route_file = Path(
        "/app/y_web/routes/admin/sub/experiments/_crud.py"
    )
    content = route_file.read_text()

    assert (
        "_resolve_bulk_experiment_ids(exp_ids, admin_user=admin_user)" in content
    ), "Bulk delete route must scope deletion IDs to the current admin user's visibility set"
