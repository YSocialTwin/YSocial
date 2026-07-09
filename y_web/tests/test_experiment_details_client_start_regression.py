"""
Regression checks for experiment detail client actions.

These tests are source-level guards for the expensive details-page render path.
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path("/Users/rossetti/PycharmProjects/YWeb")


def test_client_action_routes_redirect_back_to_experiment_details():
    execution_source = (
        REPO_ROOT / "y_web" / "routes" / "admin" / "sub" / "clients" / "_execution.py"
    ).read_text(encoding="utf-8")

    assert execution_source.count(
        'return redirect(url_for("experiments.experiment_details", uid=idexp))'
    ) >= 6
    assert "return experiment_details(idexp)" not in execution_source


def test_experiment_details_batches_client_execution_lookup():
    data_source = (
        REPO_ROOT / "y_web" / "routes" / "admin" / "sub" / "experiments" / "_data.py"
    ).read_text(encoding="utf-8")

    start = data_source.index("def experiment_details(uid):")
    end = data_source.index("@experiments.route(\"/admin/update_experiment_descr")
    experiment_details_source = data_source[start:end]

    assert "Client_Execution.client_id.in_(client_ids)" in experiment_details_source
    assert (
        "Client_Execution.query.filter_by(client_id=client.id).first()"
        not in experiment_details_source
    )
