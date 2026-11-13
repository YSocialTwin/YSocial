"""Providers of the platforms that ship with YSocial."""

from __future__ import annotations

from typing import Optional

from y_web.i18n import N_
from y_web.platforms.base import PlatformProvider
from y_web.platforms.registry import register


class Microblogging(PlatformProvider):
    key = "microblogging"
    label = N_("Microblogging")
    icon = "message-circle"
    order = 10

    def entry_url(self, exp_id: int, user_id: int) -> Optional[str]:
        return f"/{exp_id}/feed/{user_id}/feed/rf/1"


class Forum(PlatformProvider):
    key = "forum"
    label = N_("Forum")
    icon = "message-square"
    order = 20

    def entry_url(self, exp_id: int, user_id: int) -> Optional[str]:
        return f"/{exp_id}/rfeed/{user_id}/rfeed/rf/1"


class PhotoSharing(PlatformProvider):
    key = "photo_sharing"
    label = N_("Photo sharing")
    icon = "camera"
    order = 30

    def entry_url(self, exp_id: int, user_id: int) -> Optional[str]:
        return f"/{exp_id}/photo/feed/all/feed/rf/1"


class InstantMessaging(PlatformProvider):
    key = "instant_messaging"
    label = N_("Instant messaging")
    icon = "send"
    order = 40


class Dating(PlatformProvider):
    key = "dating"
    label = N_("Dating")
    icon = "heart"
    order = 50


def register_builtin_platforms() -> None:
    for provider in (
        Microblogging(),
        Forum(),
        PhotoSharing(),
        InstantMessaging(),
        Dating(),
    ):
        register(provider)
