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

    def entry_url(self, exp_id: int, user_id: int) -> Optional[str]:
        """Page a participant lands on after logging into the experiment, or ``None`` when the platform has none."""
        return None
