import pytest

pytestmark = pytest.mark.unit

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


def test_cleanup_handler_not_registered_without_explicit_opt_in():
    from y_web import _should_register_cleanup_handler

    with patch.dict(
        os.environ,
        {
            "YSOCIAL_REGISTER_ATEXIT_CLEANUP": "",
            "Y_CLIENT_SUBPROCESS": "",
            "Y_SERVER_SUBPROCESS": "",
            "Y_SOCIAL_SUBPROCESS": "",
        },
        clear=False,
    ):
        assert _should_register_cleanup_handler() is False


def test_cleanup_handler_requires_opt_in_and_non_subprocess():
    from y_web import _should_register_cleanup_handler

    with patch.dict(
        os.environ,
        {
            "YSOCIAL_REGISTER_ATEXIT_CLEANUP": "1",
            "Y_CLIENT_SUBPROCESS": "",
            "Y_SERVER_SUBPROCESS": "",
            "Y_SOCIAL_SUBPROCESS": "",
        },
        clear=False,
    ):
        assert _should_register_cleanup_handler() is True

    with patch.dict(
        os.environ,
        {
            "YSOCIAL_REGISTER_ATEXIT_CLEANUP": "1",
            "Y_SOCIAL_SUBPROCESS": "1",
        },
        clear=False,
    ):
        assert _should_register_cleanup_handler() is False


def test_y_social_explicitly_opts_into_cleanup_registration():
    with open(
        "/Users/rossetti/PycharmProjects/YWeb/y_social.py", "r", encoding="utf-8"
    ) as handle:
        source = handle.read()

    assert 'os.environ["YSOCIAL_REGISTER_ATEXIT_CLEANUP"] = "1"' in source


def test_server_subprocess_env_flags_are_set_in_startup_code():
    import y_web.src.simulation.server as mod

    with open(mod.__file__, "r", encoding="utf-8") as handle:
        source = handle.read()

    assert '"Y_SERVER_SUBPROCESS": "1"' in source
    assert '"Y_SOCIAL_SUBPROCESS": "1"' in source
