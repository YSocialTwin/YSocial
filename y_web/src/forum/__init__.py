"""YForum (Ray runtime of the forum) integration in YSocial.

A forum experiment on the HPC path runs YForum with its own database; the schema is the one of the forum, so the
pages of YSocial read it without a translation. The experiment switches of ``/admin/experiment_details`` are mapped
onto the keys YForum reads (``experiment_config``).
"""


def is_forum_hpc_experiment(experiment) -> bool:
    """A forum experiment that runs on YForum (HPC) rather than on the Flask pair (Standard)."""
    return (
        getattr(experiment, "platform_type", None) == "forum"
        and getattr(experiment, "simulator_type", None) == "HPC"
    )


def forum_hpc_installed() -> bool:
    """YForum is present (writable or bundled copy) with the two entry points the HPC launcher runs."""
    import os

    from y_web.src.system.path_utils import get_external_repo_dir

    root = get_external_repo_dir("YForum")
    return all(
        os.path.isfile(os.path.join(root, name))
        for name in ("run_server.py", "run_client.py")
    )
