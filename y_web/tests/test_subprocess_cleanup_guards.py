import os
from unittest.mock import patch


def test_simulation_subprocess_detection_covers_all_subprocess_flags():
    from y_web import _is_simulation_subprocess

    with patch.dict(os.environ, {"Y_CLIENT_SUBPROCESS": "1"}, clear=False):
        assert _is_simulation_subprocess() is True

    with patch.dict(os.environ, {"Y_SERVER_SUBPROCESS": "1"}, clear=False):
        assert _is_simulation_subprocess() is True

    with patch.dict(os.environ, {"Y_SOCIAL_SUBPROCESS": "1"}, clear=False):
        assert _is_simulation_subprocess() is True


def test_simulation_subprocess_detection_false_without_flags():
    from y_web import _is_simulation_subprocess

    with patch.dict(
        os.environ,
        {
            "Y_CLIENT_SUBPROCESS": "",
            "Y_SERVER_SUBPROCESS": "",
            "Y_SOCIAL_SUBPROCESS": "",
        },
        clear=False,
    ):
        assert _is_simulation_subprocess() is False


def test_server_subprocess_env_flags_are_set_in_startup_code():
    import y_web.src.simulation.server as mod

    with open(mod.__file__, "r", encoding="utf-8") as handle:
        source = handle.read()

    assert 'env["Y_SERVER_SUBPROCESS"] = "1"' in source
    assert 'env["Y_SOCIAL_SUBPROCESS"] = "1"' in source
