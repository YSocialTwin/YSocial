"""Providers of the platforms that ship with YSocial."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, List, Mapping, Optional, Tuple

from y_web.i18n import N_
from y_web.i18n import gettext as _
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

    def creation_rules(self, simulator_type: str) -> CreationRules:
        return CreationRules(
            database="server", copies_clean_database=simulator_type == STANDARD
        )

    def resolve_simulator(self, simulator_type: str, available: Mapping[str, bool]):
        # either runtime will do: ask for the one that is installed
        if simulator_type == HPC:
            if available["hpc"]:
                return HPC, None
            if available["microblogging"]:
                return STANDARD, None
            return HPC, _(
                "HPC microblogging experiments are unavailable because YMicroblogging is not present."
            )
        if available["microblogging"]:
            return STANDARD, None
        if available["hpc"]:
            return HPC, None
        return STANDARD, _(
            "Microblogging experiments are unavailable because neither YServer/YClient nor YMicroblogging is present."
        )


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
    details_template = "admin/experiment_details_forum.html"
    inherits_client_llm_defaults = True
    frontend_capabilities = COMMON_FRONTEND_CAPABILITIES | {
        "interaction_dislike",  # downvote
        "notifications_menu",
        "annotations_enabled",
        "annotation_emotions",
        "annotation_topics",
        "default_forum_feed_type",
    }
    frontend_exclusive_settings = frozenset(
        {"default_forum_feed_type"}
    )  # feed ordering
    details_context_keys = ("forum_feed_health",)

    def details_context(self, experiment: Any) -> dict:
        from y_web.routes.admin.sub.experiments._helpers import (
            _read_forum_feed_health,
        )
        from y_web.sdk import services

        try:
            exp_folder = services.experiment_folder(experiment)
            return {
                "forum_feed_health": _read_forum_feed_health(experiment, exp_folder)
            }
        except Exception:
            return {"forum_feed_health": None}

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

    def creation_rules(self, simulator_type: str) -> CreationRules:
        if simulator_type == HPC:
            return CreationRules(
                # the forum runtime has no use for the YSimulator cache in this version
                forced={"redis_enabled": False},
                remote_error=_("Remote forum HPC experiments are not supported."),
                database="own",
                sqlite_only_note="Forum HPC experiments use SQLite even if the platform uses PostgreSQL",
            )
        return CreationRules(
            forced={
                "opinion_dynamics_enabled": False,
                "sentiment_annotation": False,
                "emotion_annotation": False,
            },
            database="server",
            copies_clean_database=True,
        )

    def resolve_simulator(self, simulator_type: str, available: Mapping[str, bool]):
        if simulator_type == HPC:
            if not available.get("forum_hpc"):
                return HPC, _(
                    "Forum HPC experiments are unavailable because YForum is not present."
                )
            return HPC, None
        if not available["forum"]:
            return STANDARD, _(
                "Forum experiments are unavailable because YServerReddit and YClientReddit are not both present."
            )
        return STANDARD, None

    def hpc_server_config(self, request: ServerConfigRequest) -> dict:
        from y_web.src.forum.experiment_config import (
            ForumConfigError,
            generate_forum_server_config,
        )

        try:
            return generate_forum_server_config(
                exp_name=request.exp_name,
                db_uri=request.db_uri,
                data_path=request.data_path,
                is_remote=request.is_remote,
                seed=request.seed,
                topics=request.topics,
                toxicity_annotation=request.toxicity_annotation,
                sentiment_annotation=request.sentiment_annotation,
                emotion_annotation=request.emotion_annotation,
                opinion_dynamics_enabled=request.opinion_dynamics_enabled,
                perspective_api=request.perspective_api,
            )
        except ForumConfigError as exc:
            raise PlatformConfigError(
                _("Invalid forum settings: %(why)s", why=str(exc))
            ) from exc

    def validate_hpc_folder(self, exp_folder: str, runtime_dir: str) -> None:
        from y_web.src.forum.validation import validate_forum_folder

        validate_forum_folder(exp_folder, runtime_dir)

    def prepare_hpc_client_start(self, client_config: str, client: Any) -> None:
        # YForum resumes from the roster it saved: a client that never ran must read its population (and the
        # initial opinions in it) again, not an old roster left by an aborted start
        from y_web.sdk import services

        try:
            from y_web.src.forum.roster import REMOVED, reset_unstarted_roster

            execution = services.client_execution(client)
            if reset_unstarted_roster(client_config, client.name, execution) == REMOVED:
                print(f"Removed the stale roster of forum client {client.name}")
        except Exception as exc:
            print(
                f"Warning: could not check the roster of forum client {client.name}: {exc}"
            )

    def sync_hpc_run_length(self, client_config: str, client: Any) -> None:
        # the YForum client counts num_days from the day it registers, like the dating one: a restarted or
        # extended client gets what is left of Client.days, not the whole total again
        from y_web.sdk import services

        services.set_client_run_length(client_config, client, unlimited_value=0)


class PhotoSharing(PlatformProvider):
    key = "photo_sharing"
    label = N_("Photo sharing")
    icon = "camera"
    order = 30

    def entry_url(self, exp_id: int, user_id: int) -> Optional[str]:
        return f"/{exp_id}/photo/feed/all/feed/rf/1"

    def creation_rules(self, simulator_type: str) -> CreationRules:
        return CreationRules(database="server")

    def resolve_simulator(self, simulator_type: str, available: Mapping[str, bool]):
        if not available["photo_sharing"]:
            return HPC, _(
                "Photo Sharing experiments are unavailable because YPhotoSharing is not present."
            )
        return HPC, None

    def hpc_server_config(self, request: ServerConfigRequest) -> dict:
        from y_web.routes.admin.sub.experiments._crud import (
            generate_photo_sharing_config,
        )

        return generate_photo_sharing_config(
            exp_name=request.exp_name,
            db_type=request.db_type,
            db_uri=request.db_uri,
            topics=request.topics,
            data_path=request.data_path,
            db_config_dict=request.db_config_dict,
            is_remote=request.is_remote,
        )

    def write_new_experiment_files(self, exp_dir: str, prompt_language: str) -> None:
        from y_web.sdk import services

        services.write_prompt_pack(
            "prompts_ygram.json",
            os.path.join(exp_dir, "prompts_ygram.json"),
            prompt_language,
        )

    details_template = "admin/experiment_details_photo.html"
    frontend_capabilities = COMMON_FRONTEND_CAPABILITIES | {
        "show_suggested_friends",  # "Suggestions for you" rail
        "show_recsys_info",
        "show_annotation_stats",
        "interaction_share",
        "annotation_agent_type",
        "default_photo_feed_tab",
    }
    frontend_exclusive_settings = frozenset({"default_photo_feed_tab"})  # home tab
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


def register_builtin_platforms() -> None:
    for provider in (
        Microblogging(),
        Forum(),
        PhotoSharing(),
    ):
        register(provider)
