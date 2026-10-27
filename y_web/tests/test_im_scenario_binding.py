"""Scenario Design drafts of an instant messaging experiment live in a sidecar database, bound only for its requests."""

import os
from types import SimpleNamespace

import pytest

from y_web.src.experiment import context as ctx

pytestmark = pytest.mark.unit


@pytest.fixture
def folder(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "y_web.src.system.path_utils.get_writable_path", lambda p: str(tmp_path / p)
    )
    run = tmp_path / "y_web" / "experiments" / "uid"
    run.mkdir(parents=True)
    return run


def test_the_sidecar_is_registered_beside_the_run_database(folder):
    app = SimpleNamespace(config={"SQLALCHEMY_BINDS": {}})
    db_name = "experiments/uid/database_server.db"
    assert ctx.register_scenario_sidecar(app, 7, db_name) is None  # no database yet: nothing is bound
    assert app.config["SQLALCHEMY_BINDS"] == {}
    (folder / "database_server.db").write_bytes(b"")
    assert ctx.register_scenario_sidecar(app, 7, db_name) == "db_exp_7_sd"
    uri = app.config["SQLALCHEMY_BINDS"]["db_exp_7_sd"]
    assert uri.startswith("sqlite:///") and uri.endswith(os.path.join("experiments", "uid", "scenario_design_im.db"))


def test_only_scenario_design_requests_of_im_experiments_use_it(monkeypatch):
    monkeypatch.setattr(ctx, "_is_im_experiment_id", lambda exp_id: exp_id == 7)
    for blueprint, exp_id, expected in (
        ("scenario_design", 7, True),
        ("scenario_design", 8, False),  # another platform: the usual database
        ("admin", 7, False),  # the other pages of the experiment never see the sidecar
        (None, 7, False),
    ):
        monkeypatch.setattr(ctx, "request", SimpleNamespace(blueprint=blueprint))
        assert ctx._is_scenario_design_request(exp_id) is expected
