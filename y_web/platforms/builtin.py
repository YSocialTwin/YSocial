"""Providers of the platforms that ship with YSocial."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, List, Optional, Tuple

from y_web.i18n import N_
from y_web.platforms.base import HPC, PlatformProvider, StandardRuntime
from y_web.platforms.registry import register


class Microblogging(PlatformProvider):
    key = "microblogging"
    label = N_("Microblogging")
    icon = "message-circle"
    order = 10

    prompt_pack = ("prompts.json", "prompts.json")
    standard_runtime = StandardRuntime(
        server_repo="YServer",
        client_repo="YClient",
        fake_agent_module="y_client.classes",
        activity_profiles=True,
    )

    def entry_url(self, exp_id: int, user_id: int) -> Optional[str]:
        return f"/{exp_id}/feed/{user_id}/feed/rf/1"


class Forum(PlatformProvider):
    key = "forum"
    label = N_("Forum")
    icon = "message-square"
    order = 20

    def entry_url(self, exp_id: int, user_id: int) -> Optional[str]:
        return f"/{exp_id}/rfeed/{user_id}/feed/rf/1"

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
    server_modules = ("news", "voting", "image", "image_post")
    standard_runtime = StandardRuntime(
        server_repo="YServerReddit",
        client_repo="YClientReddit",
        fake_agent_module="y_client.classes.fake_base_agent",
        client_takes_log_file=True,
    )

    def experiment_prompt_pack(self, simulator_type: str) -> Tuple[str, str]:
        return self.prompt_pack

    def prompts_page(self, simulator_type: str) -> str:
        return (
            "experiments.prompts_hpc"
            if simulator_type == HPC
            else "experiments.prompts_forum"
        )

    def prepare_hpc_client_start(self, client_config: str, client: Any) -> None:
        # YForum resumes from the roster it saved: a client that never ran must read its population (and the
        # initial opinions in it) again, not an old roster left by an aborted start
        from sqlalchemy import select

        from y_web import db
        from y_web.src.models import Client_Execution

        try:
            from y_web.src.forum.roster import REMOVED, reset_unstarted_roster

            execution = db.session.scalars(
                select(Client_Execution).filter_by(client_id=client.id)
            ).first()
            if reset_unstarted_roster(client_config, client.name, execution) == REMOVED:
                print(f"Removed the stale roster of forum client {client.name}")
        except Exception as exc:
            print(
                f"Warning: could not check the roster of forum client {client.name}: {exc}"
            )

    def sync_hpc_run_length(self, client_config: str, client: Any) -> None:
        # the YForum client counts num_days from the day it registers, like the dating one: a restarted or
        # extended client gets what is left of Client.days, not the whole total again
        from y_web.src.hpc.client import _set_dating_run_length

        _set_dating_run_length(client_config, client, unlimited_value=0)


class PhotoSharing(PlatformProvider):
    key = "photo_sharing"
    label = N_("Photo sharing")
    icon = "camera"
    order = 30

    def entry_url(self, exp_id: int, user_id: int) -> Optional[str]:
        return f"/{exp_id}/photo/feed/all/feed/rf/1"

    extra_prompt_files = ("prompts_ygram.json",)
    prompt_pack = ("prompts_ygram.json", "prompts_ygram.json")

    def experiment_prompt_pack(self, simulator_type: str) -> Tuple[str, str]:
        return self.prompt_pack

    def clients_page(self, simulator_type: str) -> str:
        return "clientsr.clients_photo"

    def hpc_client_files(self, exp_folder: str, client: Any, population: Any):
        config, agents, _ = super().hpc_client_files(exp_folder, client, population)
        return config, agents, os.path.join(exp_folder, "prompts_ygram.json")

    def prepare_hpc_client_files(
        self, exp_folder: str, client: Any, population: Any, client_config: str
    ) -> None:
        from y_web.src.hpc.client import _migrate_legacy_photo_sharing_client_layout

        _migrate_legacy_photo_sharing_client_layout(
            exp_folder, client.name, population.name, client_config
        )

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

    def prompts_page(self, simulator_type: str) -> str:
        return "experiments.prompts_im"

    def hpc_client_files(self, exp_folder: str, client: Any, population: Any):
        config, agents, _ = super().hpc_client_files(exp_folder, client, population)
        return config, agents, os.path.join(exp_folder, "prompts_im.json")

    def start_hpc_gateway(self, exp_folder: str) -> None:
        from y_web.src.hpc.client import _start_im_human_gateway

        _start_im_human_gateway(exp_folder)  # server -> gateway -> clients (plan 4.8)

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

    def prompts_page(self, simulator_type: str) -> str:
        return "experiments.prompts_dating"

    def sync_hpc_run_length(self, client_config: str, client: Any) -> None:
        from y_web.src.hpc.client import _set_dating_run_length

        _set_dating_run_length(client_config, client)

    def start_hpc_gateway(self, exp_folder: str) -> None:
        from y_web.src.dating.gateway import start_for_experiment

        start_for_experiment(exp_folder)  # server -> gateway -> clients (IR-D-22)

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
