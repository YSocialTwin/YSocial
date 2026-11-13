"""Contract between the core and a simulation platform.

The core never compares ``Exps.platform_type`` with a platform name: it asks the provider registered for that
type (:mod:`y_web.platforms.registry`). A provider answers for one platform and every answer has a default here,
so a provider only states what is specific to its platform.

The built-in providers live in :mod:`y_web.platforms.builtin`; the plan is that each platform repository ships
its own (see ``docs/platform-decoupling`` in the project).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Tuple

from y_web.i18n import N_

DEFAULT_ICON = "layers"
STANDARD = "Standard"
HPC = "HPC"


@dataclass(frozen=True)
class StandardRuntime:
    """The Flask server/client pair that runs a platform in ``Standard`` mode (outside the HPC runtime)."""

    #: repository of the server and of the client under ``external/``
    server_repo: str
    client_repo: str
    #: module the client's ``FakeAgent`` is imported from
    fake_agent_module: str
    #: whether the client is started with a log file
    client_takes_log_file: bool = False
    #: whether agents have activity profiles (backfilled in old agent files, pages post while their profile is on)
    activity_profiles: bool = False


class PlatformProvider:
    """One simulation platform, as the core sees it."""

    #: value of ``Exps.platform_type``
    key: str = ""
    #: display name (marked for translation, shown through ``gettext``)
    label: str = N_("Other")
    #: icon name of the feather set used by the menus
    icon: str = DEFAULT_ICON
    #: position in menus; platforms with the same order are sorted by key
    order: int = 1000
    #: whether the clients are created by the generic HPC route (the platform page only posts to it)
    generic_hpc_client_creation: bool = True

    def entry_url(self, exp_id: int, user_id: int) -> Optional[str]:
        """Page a participant lands on after logging into the experiment, or ``None`` when the platform has none."""
        return None

    # --- admin: client pages ------------------------------------------------------------------------------------

    def client_mode(self, simulator_type: str) -> str:
        """Route/template family of the clients of an experiment: ``standard``, ``forum`` or ``hpc``."""
        return "hpc" if simulator_type == HPC else "standard"

    def opinion_mode(self, simulator_type: str) -> str:
        """Page family of the opinion settings of an experiment (same names as :meth:`client_mode`, plus ``im``)."""
        return self.client_mode(simulator_type)

    def clients_page(self, simulator_type: str) -> str:
        """Endpoint of the page that creates the clients of an experiment of this platform."""
        return (
            "clientsr.clients_hpc"
            if simulator_type == HPC
            else "clientsr.clients_standard"
        )

    def client_details_page(self, simulator_type: str) -> str:
        """Endpoint of the page that shows one client of an experiment of this platform."""
        return (
            "clientsr.client_details_hpc"
            if simulator_type == HPC
            else "clientsr.client_details"
        )

    # --- admin: client files and execution ----------------------------------------------------------------------

    #: whether the client file carries the run length in ``simulation.days`` / ``simulation.num_days`` (a forum client
    #: file is validated against a strict schema that has neither)
    client_file_has_simulation_days: bool = True
    #: prompt files, besides ``prompts.json``, that a client of this platform owns in the experiment folder
    extra_prompt_files: Tuple[str, ...] = ()
    #: ``(pack, file)``: the prompt pack a reset client restores, and the experiment file it is written to;
    #: ``None`` for a platform whose clients have nothing to restore
    prompt_pack: Optional[Tuple[str, str]] = None

    #: the Standard runtime of the platform, ``None`` when it only runs on the HPC runtime
    standard_runtime: Optional[StandardRuntime] = None
    #: modules the server of an experiment of this platform is configured with
    server_modules: Tuple[str, ...] = ("news", "voting", "image")

    def experiment_prompt_pack(self, simulator_type: str) -> Tuple[str, str]:
        """``(pack, file)``: the prompt pack an experiment starts with and its file in the experiment folder."""
        pack = "prompts_hpc.json" if simulator_type == HPC else "prompts.json"
        return pack, "prompts.json"

    def prompts_page(self, simulator_type: str) -> str:
        """Endpoint of the page where the prompts of an experiment of this platform are edited."""
        return (
            "experiments.prompts_hpc"
            if simulator_type == HPC
            else "experiments.prompts"
        )

    def client_state_files(self, exp_dir: Path, client: Any) -> List[Path]:
        """Files of a client's saved state, removed when the client is reset."""
        return []

    def rounds_per_day(self, exp: Any) -> Optional[int]:
        """Rounds a client plays per simulated day when that is a property of the experiment files, else ``None``."""
        return None
