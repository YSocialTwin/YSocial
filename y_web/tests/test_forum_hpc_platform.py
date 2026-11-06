"""The forum is one row of the HPC platform table (YForum, the Ray runtime that replaces the Flask pair)."""

from y_web.src.hpc.platforms import HPC_PLATFORMS, find_hpc_platform, get_hpc_platform


def test_forum_is_one_row_pointing_at_yforum():
    spec = get_hpc_platform("forum")
    assert spec.key == "forum"
    assert spec.runtime_repo == "YForum"
    assert spec.server_repo == "YForum"
    assert find_hpc_platform("forum") is spec


def test_forum_launch_arguments_follow_the_yforum_command_line():
    # run_server.py takes --config <folder>; run_client.py takes --config <folder> --client-config <file>
    spec = get_hpc_platform("forum")
    assert spec.client_config_only and spec.client_config_file_arg
    assert spec.normalizes_client_config
    assert spec.orchestrator_actor == "Orchestrator"
    assert spec.supports_federation is True
    assert spec.supports_gunicorn is False


def test_forum_row_does_not_change_the_other_platforms():
    before = {
        "microblogging": ("YSimulator", "YServer", True),
        "photo_sharing": ("YPhotoSharing", "YPhotoSharing", False),
        "instant_messaging": ("YInstantMessaging", "YInstantMessaging", False),
        "dating": ("YDating", "YDating", False),
    }
    for key, (runtime, server, gunicorn) in before.items():
        spec = HPC_PLATFORMS[key]
        assert (spec.runtime_repo, spec.server_repo, spec.supports_gunicorn) == (
            runtime,
            server,
            gunicorn,
        )
