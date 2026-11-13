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
    FormSectionError,
    HpcClientForm,
    PlatformConfigError,
    PlatformProvider,
    ServerConfigRequest,
    StandardRuntime,
)
from y_web.platforms.extension import template_name
from y_web.sdk import routes, services
from y_web.sdk.version import PLATFORM_API

__all__ = [
    "COMMON_FRONTEND_CAPABILITIES",
    "CreationRules",
    "FormSectionError",
    "HPC",
    "HpcClientForm",
    "N_",
    "PLATFORM_API",
    "PlatformConfigError",
    "PlatformProvider",
    "STANDARD",
    "ServerConfigRequest",
    "StandardRuntime",
    "gettext",
    "agents",
    "federation",
    "models",
    "routes",
    "runtime",
    "services",
    "social",
    "web",
    "template_name",
]


_LAZY = ("agents", "federation", "models", "runtime", "social", "web")


def __getattr__(name):
    """The groups that reach into the whole application load on first use (importing them at once would be circular)."""
    if name in _LAZY:
        import importlib

        return importlib.import_module(f"y_web.sdk.{name}")
    raise AttributeError(f"module 'y_web.sdk' has no attribute {name!r}")
