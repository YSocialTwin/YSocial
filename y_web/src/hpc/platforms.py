"""Spec table of the platforms launched through the HPC/Ray path.

Everything that differs between platforms at launch time lives here, so that adding a platform
means adding one row instead of another ``if exp.platform_type == ...`` branch (plan, DEC-03).
The rows for ``microblogging`` and ``photo_sharing`` reproduce the previous inline behaviour exactly.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class HpcPlatform:
    key: str
    # external/<repo> holding run_server.py / run_client.py
    runtime_repo: str
    # external/<repo> used as the server working directory (defaults to runtime_repo)
    server_dir_repo: Optional[str] = None
    # gunicorn can serve this platform on PostgreSQL
    supports_gunicorn: bool = True
    # frozen bundles call the runner script directly (True) or via --run-server-subprocess (False)
    frozen_server_runs_script: bool = False
    # clients receive only --config (True) or --config/--agents/--prompts (False)
    client_config_only: bool = False
    # the config argument of the client is the per-client JSON (normalized) instead of the folder
    normalizes_client_config: bool = False
    prompts_filename: str = "prompts.json"
    # Ray actor names used to stop a client
    orchestrator_actor: str = "Orchestrator"
    client_actor_prefix: str = ""

    @property
    def server_repo(self) -> str:
        return self.server_dir_repo or self.runtime_repo

    def client_actor_name(self, runtime_client_id: str) -> str:
        return f"{self.client_actor_prefix}{runtime_client_id}"


HPC_PLATFORMS = {
    "microblogging": HpcPlatform(
        key="microblogging",
        runtime_repo="YSimulator",
        server_dir_repo="YServer",
    ),
    "photo_sharing": HpcPlatform(
        key="photo_sharing",
        runtime_repo="YPhotoSharing",
        supports_gunicorn=False,
        frozen_server_runs_script=True,
        client_config_only=True,
        normalizes_client_config=True,
        prompts_filename="prompts_ygram.json",
        orchestrator_actor="orchestrator_server",
        client_actor_prefix="Client_",
    ),
}


def get_hpc_platform(platform_type) -> HpcPlatform:
    """Return the spec for ``platform_type`` or raise ``NotImplementedError`` naming it."""
    try:
        return HPC_PLATFORMS[platform_type]
    except KeyError:
        raise NotImplementedError(f"Unsupported platform {platform_type}") from None


def find_hpc_platform(platform_type) -> Optional[HpcPlatform]:
    return HPC_PLATFORMS.get(platform_type)
