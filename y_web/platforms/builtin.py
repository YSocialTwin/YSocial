"""Providers of the platforms that ship with YSocial."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, List, Mapping, Optional, Tuple

from y_web.i18n import N_
from y_web.i18n import gettext as _
from y_web.platforms.base import (
    HPC,
    STANDARD,
    COMMON_FRONTEND_CAPABILITIES,
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


class InstantMessaging(PlatformProvider):
    key = "instant_messaging"
    label = N_("Instant messaging")
    icon = "send"
    order = 40

    def opinion_mode(self, simulator_type: str) -> str:
        return "im"

    def prompts_page(self, simulator_type: str) -> str:
        return "experiments.prompts_im"

    def creation_rules(self, simulator_type: str) -> CreationRules:
        # IM has its own annotation and analytics model; the YSocial toggles do not apply (plan, 5.2)
        return CreationRules(
            forced={
                "opinion_dynamics_enabled": False,
                "toxicity_annotation": False,
                "perspective_api": None,
                "sentiment_annotation": False,
                "emotion_annotation": False,
                "redis_enabled": False,
            },
            remote_error=_("Remote instant messaging experiments are not supported."),
            database="own",
            sqlite_only_note="Instant messaging experiments use SQLite even if the platform uses PostgreSQL",
        )

    details_template = "admin/experiment_details_im.html"
    frontend_capabilities = COMMON_FRONTEND_CAPABILITIES | {
        "interactions_enabled",
        "interaction_share",  # forwarding
        "notifications_menu",
        "annotations_enabled",  # topics, sentiment, toxicity and emotion chips on messages
        "annotation_topics",
        "annotation_sentiment",
        "annotation_toxicity",
        "annotation_emotions",
        "annotation_agent_type",  # agent / human badge on messages
        "annotation_author_type",
        "profile_topics_box",
        "infinite_scroll_enabled",
        "im_show_forward_origin",
        "im_show_reactions",
        "im_show_member_roles",
        "im_default_view",
        "im_allow_time_travel",
        "im_public_observer_enabled",
        "im_participant_mode_enabled",
        "im_participant_notice",
        "im_participant_poll_seconds",
    }
    # the chat page controls belong to this platform only
    frontend_exclusive_settings = frozenset(
        key for key in frontend_capabilities if key.startswith("im_")
    )
    details_context_keys = ("im_analytics", "im_advanced", "im_switches")

    def details_context(self, experiment: Any) -> dict:
        from y_web.sdk import services

        context = {"im_analytics": None, "im_advanced": None, "im_switches": None}
        # the analytics cards follow the tables of the derived database, like every other platform's pages follow theirs
        try:
            from y_web.src.im import analytics

            analytics.ensure_derived(experiment)
            context["im_analytics"] = analytics.cards(experiment)
        except Exception:
            context["im_analytics"] = {"state": {"state": "failed", "message": ""}}
        try:
            from y_web.src.im.experiment_config import read_advanced_settings

            context["im_advanced"] = read_advanced_settings(
                services.experiment_folder(experiment)
            )
        except Exception:
            context["im_advanced"] = None
        try:
            from y_web.src.im.exp_stats import refresh_exp_stats

            refresh_exp_stats(experiment)
        except Exception:
            services.db_session().rollback()
        try:
            from y_web.src.im.experiment_config import (
                load_server_config,
                read_switches,
            )
            from y_web.src.im.participant import experiment_folder

            context["im_switches"] = read_switches(
                load_server_config(experiment_folder(experiment))
            )
        except Exception:
            context["im_switches"] = None
        return context

    def observer_url(self, exp_id: int) -> Optional[str]:
        # IM has no per-user feed row: the observer opens on the chat list (plan, 6.3)
        return f"/{exp_id}/im"

    def validate_before_start(self, exp: Any) -> Optional[str]:
        from y_web.sdk import services
        from y_web.src.im.validation import ImValidationError, validate_im_folder

        try:
            validate_im_folder(services.hpc_experiment_folder(exp))
        except ImValidationError as exc:
            return _("The instant messaging configuration is not valid: %(why)s") % {
                "why": "; ".join(exc.messages[:5])
            }
        return None

    def folder_clone(self):
        from y_web.src.im.clone import copy_im_folder, new_uid

        return copy_im_folder, new_uid

    def hpc_server_config(self, request: ServerConfigRequest) -> dict:
        from y_web.routes.admin.sub.experiments._im import (
            ImConfigError,
            generate_im_server_config,
        )

        try:
            # run length, start date and round length come from the client form; humans can register
            # at any time, so the gateway is always part of an IM experiment
            return generate_im_server_config(
                exp_name=request.exp_name,
                db_uri=request.db_uri,
                data_path=request.data_path,
                is_remote=request.is_remote,
                toxicity_annotation=request.toxicity_annotation,
                sentiment_annotation=request.sentiment_annotation,
                emotion_annotation=request.emotion_annotation,
                opinion_dynamics_enabled=request.opinion_dynamics_enabled,
            )
        except ImConfigError as exc:
            raise PlatformConfigError(
                _("Invalid instant messaging settings: %(why)s", why=str(exc))
            ) from exc

    def resolve_simulator(self, simulator_type: str, available: Mapping[str, bool]):
        if not available.get("instant_messaging"):
            return HPC, _(
                "Instant messaging experiments are unavailable because YInstantMessaging is not present."
            )
        return HPC, None

    def hpc_client_files(self, exp_folder: str, client: Any, population: Any):
        config, agents, _ = super().hpc_client_files(exp_folder, client, population)
        return config, agents, os.path.join(exp_folder, "prompts_im.json")

    def validate_hpc_folder(self, exp_folder: str, runtime_dir: str) -> None:
        from y_web.src.im.validation import validate_im_folder

        validate_im_folder(exp_folder, runtime_dir)

    def after_hpc_server_started(self, exp: Any) -> None:
        from y_web.src.hpc.server import _start_im_gateway_when_ready

        _start_im_gateway_when_ready(exp)

    def stop_hpc_gateway(self, exp_folder: str) -> None:
        # reverse of the start order: gateway first, then the server (plan 4.8)
        from y_web.src.im.gateway_process import stop_gateway

        stop_gateway(exp_folder)

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

    def creation_rules(self, simulator_type: str) -> CreationRules:
        # dating has no opinion dynamics; toxicity uses the local model (no Perspective key) and the
        # annotations are the runtime's own (plan S1)
        return CreationRules(
            forced={
                "opinion_dynamics_enabled": False,
                "perspective_api": None,
                "redis_enabled": False,
            },
            remote_error=_("Remote dating experiments are not supported."),
            database="own",
            sqlite_only_note="Dating experiments use SQLite even if the platform uses PostgreSQL",
        )

    details_template = "@dating/admin/experiment_details_dating.html"
    frontend_capabilities = frozenset(
        {
            "language",
            "language_switch_allowed",
            "dating_allow_time_travel",
            "dating_public_observer_enabled",
            "dating_participant_mode_enabled",
            "dating_participant_notice",
            "dating_poll_seconds",
        }
    )
    # the dating page controls belong to this platform only
    frontend_exclusive_settings = frozenset(
        key for key in frontend_capabilities if key.startswith("dating_")
    )

    def observer_url(self, exp_id: int) -> Optional[str]:
        # the observer (S6) is the only way in: dating has no per-user feed row either
        return f"/{exp_id}/dating"

    def validate_before_start(self, exp: Any) -> Optional[str]:
        from y_web.src.dating.validation import (
            DatingValidationError,
            validate_dating_folder,
        )
        from y_web.sdk import services

        try:
            validate_dating_folder(services.hpc_experiment_folder(exp))
        except DatingValidationError as exc:
            return _("The dating configuration is not valid: %(why)s") % {
                "why": "; ".join(exc.messages[:5])
            }
        return None

    def slots_per_day(self, exp_folder: str) -> int:
        from y_web.src.dating.clone import slots_per_day

        return slots_per_day(exp_folder)

    def folder_clone(self):
        from y_web.src.dating.clone import copy_dating_folder, new_uid

        return copy_dating_folder, new_uid

    def hpc_server_config(self, request: ServerConfigRequest) -> dict:
        from y_web.src.dating.experiment_config import (
            DatingConfigError,
            generate_dating_server_config,
        )

        try:
            return generate_dating_server_config(
                exp_name=request.exp_name,
                db_uri=request.db_uri,
                data_path=request.data_path,
                is_remote=request.is_remote,
                seed=request.seed,
                toxicity_annotation=request.toxicity_annotation,
                sentiment_annotation=request.sentiment_annotation,
                emotion_annotation=request.emotion_annotation,
            )
        except DatingConfigError as exc:
            raise PlatformConfigError(
                _("Invalid dating settings: %(why)s", why=str(exc))
            ) from exc

    def resolve_simulator(self, simulator_type: str, available: Mapping[str, bool]):
        if not available.get("dating"):
            return HPC, _(
                "Dating experiments are unavailable because YDating is not present."
            )
        return HPC, None

    def sync_hpc_run_length(self, client_config: str, client: Any) -> None:
        from y_web.sdk import services

        services.set_client_run_length(client_config, client)

    def validate_hpc_folder(self, exp_folder: str, runtime_dir: str) -> None:
        from y_web.src.dating.validation import validate_dating_folder

        validate_dating_folder(exp_folder, runtime_dir)

    def prepare_hpc_server(self, exp_folder: str) -> None:
        # the settings that shape the run are fixed from the first start (S3 lock)
        import json

        from y_web.src.dating import server_settings

        config_file = os.path.join(exp_folder, "server_config.json")
        with open(config_file, "r", encoding="utf-8") as handle:
            server_config = json.load(handle)
        if server_settings.ensure_humans(server_config):  # people are always welcome
            with open(config_file, "w", encoding="utf-8") as handle:
                json.dump(server_config, handle, indent=4)
        server_settings.write_lock(exp_folder, server_config)

    def stop_hpc_gateway(self, exp_folder: str) -> None:
        # reverse of the start order: gateway first, then the server
        from y_web.src.dating.gateway import stop_gateway

        stop_gateway(exp_folder)

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
