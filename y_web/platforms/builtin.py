"""Providers of the platforms that ship with YSocial."""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional

from y_web.i18n import N_
from y_web.platforms.base import HPC, PlatformProvider
from y_web.platforms.registry import register


class Microblogging(PlatformProvider):
    key = "microblogging"
    label = N_("Microblogging")
    icon = "message-circle"
    order = 10

    prompt_pack = ("prompts.json", "prompts.json")

    def entry_url(self, exp_id: int, user_id: int) -> Optional[str]:
        return f"/{exp_id}/feed/{user_id}/feed/rf/1"


class Forum(PlatformProvider):
    key = "forum"
    label = N_("Forum")
    icon = "message-square"
    order = 20

    def entry_url(self, exp_id: int, user_id: int) -> Optional[str]:
        return f"/{exp_id}/rfeed/{user_id}/rfeed/rf/1"

    # The Flask pair (YServerReddit/YClientReddit) and the Ray runtime (YForum) have their own pages.
    def client_mode(self, simulator_type: str) -> str:
        return "hpc" if simulator_type == HPC else "forum"

    def clients_page(self, simulator_type: str) -> str:
        return (
            "clientsr.clients_forum_hpc"
            if simulator_type == HPC
            else "clientsr.clients_forum"
        )

    def client_details_page(self, simulator_type: str) -> str:
        return (
            "clientsr.client_details_hpc"
            if simulator_type == HPC
            else "clientsr.client_details_forum"
        )

    generic_hpc_client_creation = False
    client_file_has_simulation_days = False
    prompt_pack = ("prompts_forum.json", "prompts.json")


class PhotoSharing(PlatformProvider):
    key = "photo_sharing"
    label = N_("Photo sharing")
    icon = "camera"
    order = 30

    def entry_url(self, exp_id: int, user_id: int) -> Optional[str]:
        return f"/{exp_id}/photo/feed/all/feed/rf/1"

    extra_prompt_files = ("prompts_ygram.json",)
    prompt_pack = ("prompts_ygram.json", "prompts_ygram.json")

    def clients_page(self, simulator_type: str) -> str:
        return "clientsr.clients_photo"

    def client_state_files(self, exp_dir: Path, client: Any) -> List[Path]:
        # the state of the client of a population, then any other population of the same client
        return list(exp_dir.glob(f"client_{client.name}-*.state.json"))


class InstantMessaging(PlatformProvider):
    key = "instant_messaging"
    label = N_("Instant messaging")
    icon = "send"
    order = 40

    def opinion_mode(self, simulator_type: str) -> str:
        return "im"

    def clients_page(self, simulator_type: str) -> str:
        return "clientsr.clients_im"

    generic_hpc_client_creation = False


class Dating(PlatformProvider):
    key = "dating"
    label = N_("Dating")
    icon = "heart"
    order = 50

    def clients_page(self, simulator_type: str) -> str:
        return "clientsr.clients_dating"

    def client_details_page(self, simulator_type: str) -> str:
        return "clientsr.client_details_dating"

    def rounds_per_day(self, exp: Any) -> Optional[int]:
        from y_web.routes.admin.sub.clients._dating import (
            _experiment_folder,
            _load_server_config,
        )

        simulation = _load_server_config(_experiment_folder(exp)).get("simulation")
        return int((simulation or {}).get("num_slots_per_day", 24))

    generic_hpc_client_creation = False


def register_builtin_platforms() -> None:
    for provider in (
        Microblogging(),
        Forum(),
        PhotoSharing(),
        InstantMessaging(),
        Dating(),
    ):
        register(provider)
