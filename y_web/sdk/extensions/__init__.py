"""The public interface between YSocial and an extension (Scenario Design, Training Modules, frontend add-ons...).

An extension imports from here and from nothing else in ``y_web``. Every name is a re-export of, or a forwarder to,
code that already exists in the core: nothing here has logic of its own, and the old import paths keep working.

``EXTENSION_API`` is the version of this surface (semantic versioning, separate from ``PLATFORM_API``); the rules are
in ``docs/extension-api.md`` and the surface is recorded in ``y_web/tests/data/sdk_extensions_api.json``.
"""

EXTENSION_API = "1.0"

MODULES = (
    "access",
    "agents",
    "content",
    "db",
    "experiments",
    "federation",
    "i18n",
    "interview",
    "models",
    "paths",
    "platforms",
    "runtime",
    "settings",
    "signup",
)

__all__ = ["EXTENSION_API", "MODULES", *MODULES]


def __getattr__(name):
    """The groups load on first use: importing them at once would load most of the application."""
    if name in MODULES:
        import importlib

        return importlib.import_module(f"y_web.sdk.extensions.{name}")
    raise AttributeError(f"module 'y_web.sdk.extensions' has no attribute {name!r}")
