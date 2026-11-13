"""Simulation platforms: the contract with the core and the registry of the available ones.

Importing this package registers the built-in platforms; use :mod:`y_web.platforms.registry` to ask about them.
"""

from y_web.platforms import registry
from y_web.platforms.base import PlatformProvider
from y_web.platforms.builtin import register_builtin_platforms

if not registry.keys():
    register_builtin_platforms()

__all__ = ["PlatformProvider", "registry"]
