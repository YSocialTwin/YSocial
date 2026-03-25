import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.unit


def _make_experiment(
    *,
    simulator_type="Standard",
    platform_type="microblogging",
    annotations="",
    db_name="experiments/test-uid/database_server.db",
):
    return SimpleNamespace(
        simulator_type=simulator_type,
        platform_type=platform_type,
        annotations=annotations,
        db_name=db_name,
    )


def test_standard_client_creation_uses_config_backed_opinion_toggle(tmp_path):
    from y_web.routes.admin.sub.clients._crud import (
        _opinion_dynamics_enabled_for_client_creation,
    )

    exp_uid = "test-uid"
    exp_dir = tmp_path / "y_web" / "experiments" / exp_uid
    exp_dir.mkdir(parents=True)
    (exp_dir / "config_server.json").write_text(
        json.dumps({"opinion_dynamics_enabled": True})
    )
    experiment = _make_experiment(db_name=f"experiments/{exp_uid}/database_server.db")

    with patch("y_web.routes.admin.sub.clients._crud.get_db_type", return_value="sqlite"):
        with patch(
            "y_web.src.system.path_utils.get_writable_path", return_value=str(tmp_path)
        ):
            assert _opinion_dynamics_enabled_for_client_creation(experiment) is True


def test_hpc_client_creation_reads_server_config_toggle(tmp_path):
    from y_web.routes.admin.sub.clients._crud import (
        _opinion_dynamics_enabled_for_client_creation,
    )

    exp_uid = "test-hpc"
    exp_dir = tmp_path / "y_web" / "experiments" / exp_uid
    exp_dir.mkdir(parents=True)
    (exp_dir / "server_config.json").write_text(json.dumps({"opinions_enabled": True}))
    experiment = _make_experiment(
        simulator_type="HPC",
        db_name=f"experiments/{exp_uid}/database_server.db",
    )

    with patch("y_web.routes.admin.sub.clients._crud.get_db_type", return_value="sqlite"):
        with patch(
            "y_web.src.system.path_utils.get_writable_path", return_value=str(tmp_path)
        ):
            assert _opinion_dynamics_enabled_for_client_creation(experiment) is True


def test_client_creation_opinion_toggle_falls_back_to_annotations():
    from y_web.routes.admin.sub.clients._crud import (
        _opinion_dynamics_enabled_for_client_creation,
    )

    experiment = _make_experiment(annotations="sentiment,opinions,toxicity")
    with patch("y_web.routes.admin.sub.clients._crud.get_db_type", return_value="sqlite"):
        assert _opinion_dynamics_enabled_for_client_creation(experiment) is True


def test_client_creation_routes_persist_and_redirect_opinion_configuration():
    source = open(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/clients/_crud.py",
        "r",
    ).read()
    assert '"opinion_dynamics": {' in source
    assert '"clientsr.opinion_configuration_standard"' in source
    assert '"clientsr.opinion_configuration_hpc"' in source


def test_client_creation_context_uses_shared_opinion_resolver():
    source = open(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/clients/_crud.py",
        "r",
    ).read()
    assert (
        "experiment_opinion_dynamics_enabled = (\n"
        "            _opinion_dynamics_enabled_for_client_creation(exp)\n"
        "        )"
    ) in source


def test_standard_redirect_is_implemented_in_standard_create_function():
    source = open(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/clients/_crud.py",
        "r",
    ).read()

    standard_start = source.index("def _create_standard_client_internal():")
    forum_start = source.index("def _create_forum_client_internal():")
    standard_chunk = source[standard_start:forum_start]

    next_def_after_forum = source.find("\ndef ", forum_start + 1)
    if next_def_after_forum == -1:
        next_def_after_forum = len(source)
    forum_chunk = source[forum_start:next_def_after_forum]

    assert '"clientsr.opinion_configuration_standard"' in standard_chunk
    assert '"clientsr.opinion_configuration_standard"' not in forum_chunk
