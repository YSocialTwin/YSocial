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
    # the Standard forum (YServerReddit/YClientReddit) behaves like any other platform; these hooks are YForum's
    hpc_only_hooks = True
    configures_memory = True

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

    def apply_experiment_switches(self, config, original, **switches) -> bool:
        # YForum's schemas are strict: write the keys it reads next to the mirrors the experiment page reads
        from y_web.src.forum.experiment_config import apply_experiment_switches

        apply_experiment_switches(
            config,
            **{k: v for k, v in switches.items() if k != "stress_reward_config"},
        )
        return False

    def apply_client_switches(self, client_config, **switches) -> bool:
        from y_web.src.forum.experiment_config import apply_switches_to_client

        apply_switches_to_client(client_config, **switches)
        return True

    def persist_hpc_opinion_dynamics(self, context: dict) -> bool:
        """Persist the opinion dynamics in YForum's own shape (``simulation.opinion_dynamics``).

        YForum's strict client schema has no top-level ``opinion_dynamics`` and no opinion groups: the initial
        opinions travel in the population file, the model and its parameters here.
        """
        import json

        from flask import flash, request

        update_rule = request.form.get("update_rule", "bounded_confidence")
        if update_rule not in ("bounded_confidence", "llm_evaluation"):
            update_rule = "bounded_confidence"
        if update_rule == "bounded_confidence":
            parameters = {
                "epsilon": float(request.form.get("bc_epsilon", "0.25")),
                "mu": float(request.form.get("bc_mu", "0.5")),
                "theta": float(request.form.get("bc_theta", "0.0")),
                "cold_start": request.form.get("bc_cold_start", "neutral"),
            }
        else:
            parameters = {"cold_start": request.form.get("llm_cold_start", "neutral")}
        path = context["client_config_file"]
        if not os.path.exists(path):
            flash(
                _(
                    "Client configuration file not found: %(client_config_file)s",
                    client_config_file=path,
                ),
                "warning",
            )
            return True
        try:
            with open(path, "r", encoding="utf-8") as handle:
                client_config = json.load(handle)
            simulation = client_config.setdefault("simulation", {})
            simulation["opinion_dynamics"] = {
                "enabled": True,
                "model_name": update_rule,
                "parameters": parameters,
            }
            client_config.pop("opinion_dynamics", None)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(client_config, handle, indent=4)
            flash(_("Opinion dynamics configuration saved successfully."), "success")
        except (OSError, ValueError) as e:
            flash(
                _("Error updating client configuration: %(error)s", error=str(e)),
                "warning",
            )
        return True

    def after_opinion_distribution_saved(self, context: dict) -> None:
        """A client on YForum resumes from its roster file: drop it when the client never ran.

        The initial opinions are read from the population file only when the client registers its agents; once it
        has progress the roster stays (a resume keeps its agents) and the user is told the new values need a fresh
        start.
        """
        from flask import flash

        from y_web.sdk import services
        from y_web.src.forum.roster import KEPT_STARTED, REMOVED, reset_unstarted_roster

        client = context["client"]
        outcome = reset_unstarted_roster(
            context["client_config_file"],
            client.name,
            services.client_execution(client),
        )
        if outcome == REMOVED:
            flash(
                _(
                    "The saved agents of this client were discarded: the new opinions apply at its first start."
                ),
                "info",
            )
        elif outcome == KEPT_STARTED:
            flash(
                _(
                    "This client has already run: the new initial opinions apply only to a fresh start (new client or reset of the experiment)."
                ),
                "warning",
            )

    def validate_hpc_folder(self, exp_folder: str, runtime_dir: str) -> None:
        from y_web.src.forum.validation import validate_forum_folder

        validate_forum_folder(exp_folder, runtime_dir)

    def validate_hpc_client(
        self, exp_folder: str, runtime_dir: str, client_config: str
    ) -> bool:
        from y_web.src.forum.validation import validate_forum_folder

        validate_forum_folder(exp_folder, runtime_dir, client_config=client_config)
        return True

    def extra_runtime_availability(self):
        from y_web.src.forum.validation import forum_hpc_installed

        return {"forum_hpc": forum_hpc_installed()}

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


def register_builtin_platforms() -> None:
    for provider in (
        Microblogging(),
        Forum(),
    ):
        register(provider)
