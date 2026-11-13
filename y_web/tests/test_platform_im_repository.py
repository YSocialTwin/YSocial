"""Instant messaging is provided by its repository (YInstantMessaging), not by the core (plan, phase F5)."""

from y_web.platforms import registry
from y_web.tests import _platform_alias


def test_the_core_ships_no_instant_messaging_provider():
    from y_web.platforms import builtin

    assert not hasattr(builtin, "InstantMessaging")


def test_the_platform_is_known_only_where_its_repository_is_installed():
    installed = _platform_alias.installed(_platform_alias.INSTANT_MESSAGING)
    assert (registry.get("instant_messaging") is not None) == installed
    # an experiment of a missing platform is handled by the generic provider, never by an error
    assert registry.resolve("instant_messaging") is not None
