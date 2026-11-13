"""The public interface between YSocial and a simulation platform.

A platform provider (a subclass of :class:`PlatformProvider`, declared in the ``platform`` section of its
repository's ``meta/registry.json``) imports from here and from nothing else in ``y_web``:

* the contract: :class:`PlatformProvider` and the small value types its hooks take or return;
* :func:`template_name`: how a platform names its own templates;
* :mod:`y_web.sdk.services`: what the core offers at run time (folders, run length, configuration, prompts);
* translation helpers, as the core itself uses them.

``PLATFORM_API`` is the version of this surface; see :mod:`y_web.sdk.version` for the rules that govern it.
"""

from y_web.i18n import N_, gettext
from y_web.platforms.base import (
    COMMON_FRONTEND_CAPABILITIES,
    HPC,
    STANDARD,
    CreationRules,
    PlatformConfigError,
    PlatformProvider,
    ServerConfigRequest,
    StandardRuntime,
)
from y_web.platforms.extension import template_name
from y_web.sdk import services
from y_web.sdk.version import PLATFORM_API

__all__ = [
    "COMMON_FRONTEND_CAPABILITIES",
    "CreationRules",
    "HPC",
    "N_",
    "PLATFORM_API",
    "PlatformConfigError",
    "PlatformProvider",
    "STANDARD",
    "ServerConfigRequest",
    "StandardRuntime",
    "gettext",
    "services",
    "template_name",
]
