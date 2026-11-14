"""Spec table of the platforms launched through the HPC/Ray path.

Everything that differs between platforms at launch time lives here, so that adding a platform
means declaring ``hpc_launch`` on its provider instead of another ``if exp.platform_type == ...`` branch (plan, DEC-03).
The rows are declared by the providers (``PlatformProvider.hpc_launch``).
"""

from collections.abc import Mapping
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
    # the folder is passed as --config and the per-client JSON as --client-config
    client_config_file_arg: bool = False
    prompts_filename: str = "prompts.json"
    # Ray actor names used to stop a client
    orchestrator_actor: str = "Orchestrator"
    client_actor_prefix: str = ""
    # the runtime ships an offline validator that must pass before the server is started
    validates_config: bool = False
    # YSimulator-style client preparation steps (stress/reward and network bootstrap rewrite the client
    # config; the actor log clean-up trims "completion" lines); the prompts file must exist before a start
    syncs_client_config: bool = True
    requires_prompts_file: bool = True
    # the runtime can take part in a World Simulation (federation adapter and gate are installed)
    supports_federation: bool = False

    @property
    def server_repo(self) -> str:
        return self.server_dir_repo or self.runtime_repo

    def client_actor_name(self, runtime_client_id: str) -> str:
        return f"{self.client_actor_prefix}{runtime_client_id}"


class _Table(Mapping):
    """``platform key -> HpcPlatform``, read from the providers that declare ``hpc_launch`` (as installed now)."""

    _specs: dict = {}

    def _rows(self) -> dict:
        from y_web.platforms import registry

        declared = {}
        for provider in registry.providers():
            for variant in registry.variants(provider.key):
                if variant.hpc_launch and provider.key not in declared:
                    declared[provider.key] = variant
        # one spec object per declaring provider, so that lookups return the same instance
        return {
            key: self._specs.setdefault(
                id(variant), HpcPlatform(key=key, **variant.hpc_launch)
            )
            for key, variant in declared.items()
        }

    def __getitem__(self, key):
        return self._rows()[key]

    def __iter__(self):
        return iter(self._rows())

    def __len__(self):
        return len(self._rows())


HPC_PLATFORMS = _Table()


def get_hpc_platform(platform_type) -> HpcPlatform:
    """Return the spec for ``platform_type`` or raise ``NotImplementedError`` naming it."""
    try:
        return HPC_PLATFORMS[platform_type]
    except KeyError:
        raise NotImplementedError(f"Unsupported platform {platform_type}") from None


def find_hpc_platform(platform_type) -> Optional[HpcPlatform]:
    return HPC_PLATFORMS.get(platform_type)
