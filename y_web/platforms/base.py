"""Contract between the core and a simulation platform.

The core never compares ``Exps.platform_type`` with a platform name: it asks the provider registered for that
type (:mod:`y_web.platforms.registry`). A provider answers for one platform and every answer has a default here,
so a provider only states what is specific to its platform.

The built-in providers live in :mod:`y_web.platforms.builtin`; the plan is that each platform repository ships
its own (see ``docs/platform-decoupling`` in the project).
"""

from __future__ import annotations

from typing import Optional

from y_web.i18n import N_

DEFAULT_ICON = "layers"
STANDARD = "Standard"
HPC = "HPC"


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
