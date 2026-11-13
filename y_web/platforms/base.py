"""Contract between the core and a simulation platform.

The core never compares ``Exps.platform_type`` with a platform name: it asks the provider registered for that
type (:mod:`y_web.platforms.registry`). A provider answers for one platform and every answer has a default here,
so a provider only states what is specific to its platform.

The built-in providers live in :mod:`y_web.platforms.builtin`; the plan is that each platform repository ships
its own (see ``docs/platform-decoupling`` in the project).
"""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, FrozenSet, List, Mapping, Optional, Tuple

from y_web.i18n import N_

DEFAULT_ICON = "layers"
STANDARD = "Standard"
HPC = "HPC"


@dataclass(frozen=True)
class CreationRules:
    """What a new experiment of a platform and simulator type must respect."""

    #: settings the platform fixes whatever the form says (``opinion_dynamics_enabled``, ``redis_enabled``, ...)
    forced: Mapping[str, Any] = field(default_factory=dict)
    #: translated refusal of a remote experiment, ``None`` when remote is allowed
    remote_error: Optional[str] = None
    #: who makes the database of the experiment: ``"server"`` (YSocial prepares it, SQLite or PostgreSQL), ``"own"``
    #: (the runtime creates its own SQLite database on first start) or ``"none"``
    database: str = "none"
    #: whether the empty server database shipped with YSocial is copied into a new experiment
    copies_clean_database: bool = False
    #: log line written when the application uses PostgreSQL but the experiment cannot
    sqlite_only_note: Optional[str] = None


class PlatformConfigError(ValueError):
    """The settings of a new experiment are refused by its platform; the message is translated and shown as is."""


@dataclass(frozen=True)
class ServerConfigRequest:
    """Everything a platform may need to write the server configuration of a new HPC experiment."""

    exp_name: str
    db_type: str
    db_uri: str
    data_path: str
    db_config_dict: Optional[Mapping[str, Any]]
    is_remote: int
    seed: Optional[str]
    topics: List[str]
    toxicity_annotation: bool
    sentiment_annotation: bool
    emotion_annotation: bool
    opinion_dynamics_enabled: bool
    perspective_api: Optional[str]
    redis_enabled: bool
    redis_host: Any
    redis_port: Any
    redis_password: Any
    redis_sliding_window_days: int


@dataclass(frozen=True)
class StandardRuntime:
    """The Flask server/client pair that runs a platform in ``Standard`` mode (outside the HPC runtime)."""

    #: repository of the server and of the client under ``external/``
    server_repo: str
    client_repo: str
    #: module the client's ``FakeAgent`` is imported from
    fake_agent_module: str
    #: whether the client is started with a log file
    client_takes_log_file: bool = False
    #: whether agents have activity profiles (backfilled in old agent files, pages post while their profile is on)
    activity_profiles: bool = False


#: frontend settings every platform that does not offer all of them honours
COMMON_FRONTEND_CAPABILITIES = frozenset(
    {
        "interaction_post",
        "interaction_comment",
        "interaction_like",
        "show_post_time",
        "posts_per_page",
        # the interface language is resolved for every platform (y_web.i18n)
        "language",
        "language_switch_allowed",
    }
)


class PlatformProvider:
    """One simulation platform, as the core sees it."""

    #: value of ``Exps.platform_type``
    key: str = ""
    #: display name (marked for translation, shown through ``gettext``)
    label: str = N_("Other")
    #: icon name of the feather set used by the menus
    icon: str = DEFAULT_ICON
    #: position in menus; platforms with the same order are sorted by key
    order: int = 1000
    #: whether the clients are created by the generic HPC route (the platform page only posts to it)
    generic_hpc_client_creation: bool = True

    def entry_url(self, exp_id: int, user_id: int) -> Optional[str]:
        """Page a participant lands on after logging into the experiment, or ``None`` when the platform has none."""
        return None

    # --- admin: client pages ------------------------------------------------------------------------------------

    def client_mode(self, simulator_type: str) -> str:
        """Route/template family of the clients of an experiment: ``standard``, ``forum`` or ``hpc``."""
        return "hpc" if simulator_type == HPC else "standard"

    def opinion_mode(self, simulator_type: str) -> str:
        """Page family of the opinion settings of an experiment (same names as :meth:`client_mode`, plus ``im``)."""
        return self.client_mode(simulator_type)

    def clients_page(self, simulator_type: str) -> str:
        """Endpoint of the page that creates the clients of an experiment of this platform."""
        return (
            "clientsr.clients_hpc"
            if simulator_type == HPC
            else "clientsr.clients_standard"
        )

    def client_details_page(self, simulator_type: str) -> str:
        """Endpoint of the page that shows one client of an experiment of this platform."""
        return (
            "clientsr.client_details_hpc"
            if simulator_type == HPC
            else "clientsr.client_details"
        )

    # --- admin: client files and execution ----------------------------------------------------------------------

    #: whether the client file carries the run length in ``simulation.days`` / ``simulation.num_days`` (a forum client
    #: file is validated against a strict schema that has neither)
    client_file_has_simulation_days: bool = True
    #: prompt files, besides ``prompts.json``, that a client of this platform owns in the experiment folder
    extra_prompt_files: Tuple[str, ...] = ()
    #: ``(pack, file)``: the prompt pack a reset client restores, and the experiment file it is written to;
    #: ``None`` for a platform whose clients have nothing to restore
    prompt_pack: Optional[Tuple[str, str]] = None

    #: the Standard runtime of the platform, ``None`` when it only runs on the HPC runtime
    standard_runtime: Optional[StandardRuntime] = None
    #: modules the server of an experiment of this platform is configured with
    server_modules: Tuple[str, ...] = ("news", "voting", "image")

    def experiment_prompt_pack(self, simulator_type: str) -> Tuple[str, str]:
        """``(pack, file)``: the prompt pack an experiment starts with and its file in the experiment folder."""
        pack = "prompts_hpc.json" if simulator_type == HPC else "prompts.json"
        return pack, "prompts.json"

    def prompts_page(self, simulator_type: str) -> str:
        """Endpoint of the page where the prompts of an experiment of this platform are edited."""
        return (
            "experiments.prompts_hpc"
            if simulator_type == HPC
            else "experiments.prompts"
        )

    def client_state_files(self, exp_dir: Path, client: Any) -> List[Path]:
        """Files of a client's saved state, removed when the client is reset."""
        return []

    def rounds_per_day(self, exp: Any) -> Optional[int]:
        """Rounds a client plays per simulated day when that is a property of the experiment files, else ``None``."""
        return None

    # --- HPC runtime: starting a client --------------------------------------------------------------------------

    def hpc_client_files(
        self, exp_folder: str, client: Any, population: Any
    ) -> Tuple[str, str, str]:
        """``(client config, agents, prompts)`` files a client of this platform is started with."""
        return (
            os.path.join(exp_folder, f"client_{client.name}-{population.name}.json"),
            os.path.join(exp_folder, f"{population.name}.json"),
            os.path.join(exp_folder, "prompts.json"),
        )

    def prepare_hpc_client_files(
        self, exp_folder: str, client: Any, population: Any, client_config: str
    ) -> None:
        """Bring the files of an older layout up to date, before the start checks that they exist."""

    def prepare_hpc_client_start(self, client_config: str, client: Any) -> None:
        """Last preparation of a client whose files are all there."""

    def sync_hpc_run_length(self, client_config: str, client: Any) -> None:
        """Make the client file say how long the client runs (``Client.days`` is the source of truth)."""
        from y_web.sdk import services

        services.sync_client_duration(client_config, client)

    def start_hpc_gateway(self, exp_folder: str) -> None:
        """Start what must run between the HPC server and its clients (the human gateway of a platform)."""

    # --- HPC runtime: the server ----------------------------------------------------------------------------------

    def validate_hpc_folder(self, exp_folder: str, runtime_dir: str) -> None:
        """Check the files of an experiment against what the HPC runtime of the platform needs (raise to refuse)."""

    def prepare_hpc_server(self, exp_folder: str) -> None:
        """Fix the settings of the run just before the HPC server starts."""

    def after_hpc_server_started(self, exp: Any) -> None:
        """What starts together with the HPC server (not with its clients)."""

    def stop_hpc_gateway(self, exp_folder: str) -> None:
        """Stop what ``start_hpc_gateway`` / ``after_hpc_server_started`` started, before the server is stopped."""

    # --- admin: creating an experiment -----------------------------------------------------------------------------

    def resolve_simulator(
        self, simulator_type: str, available: Mapping[str, bool]
    ) -> Tuple[str, Optional[str]]:
        """``(simulator type, error)`` for a new experiment of this platform.

        ``available`` says which runtimes are installed (keys: ``microblogging``, ``hpc``, ``forum``, ``forum_hpc``,
        ``photo_sharing``, ``instant_messaging``, ``dating``). ``error`` is the translated reason the experiment
        cannot be created, or ``None``.
        """
        return (HPC if simulator_type == HPC else STANDARD), None

    def creation_rules(self, simulator_type: str) -> CreationRules:
        """The rules a new experiment of this platform on ``simulator_type`` must respect."""
        return CreationRules()

    def write_new_experiment_files(self, exp_dir: str, prompt_language: str) -> None:
        """Files, besides the server configuration, that a new HPC experiment starts with."""

    def hpc_server_config(self, request: ServerConfigRequest) -> dict:
        """Server configuration of a new experiment on the HPC runtime (raise ``PlatformConfigError`` to refuse)."""
        from y_web.sdk import services

        return services.generate_hpc_server_config(
            exp_name=request.exp_name,
            platform_type=self.key,
            db_type=request.db_type,
            db_uri=request.db_uri,
            redis_enabled=request.redis_enabled,
            redis_host=request.redis_host,
            redis_port=request.redis_port,
            redis_password=request.redis_password,
            redis_sliding_window_days=request.redis_sliding_window_days,
            perspective_api=(
                request.perspective_api if request.perspective_api else None
            ),
            toxicity_annotation=request.toxicity_annotation,
            sentiment_annotation=request.sentiment_annotation,
            emotion_annotation=request.emotion_annotation,
            opinion_dynamics_enabled=request.opinion_dynamics_enabled,
            topics=request.topics,
            data_path=request.data_path,
            db_config_dict=request.db_config_dict,
            is_remote=request.is_remote,
        )

    # --- admin: opening, starting and copying an experiment ----------------------------------------------------------

    def observer_url(self, exp_id: int) -> Optional[str]:
        """Page an administrator opens an experiment on when the platform has no per-user feed, else ``None``."""
        return None

    def validate_before_start(self, exp: Any) -> Optional[str]:
        """Translated reason the experiment cannot be started because its files are not valid, or ``None``."""
        return None

    def slots_per_day(self, exp_folder: str) -> int:
        """Rounds per simulated day of an experiment kept in ``exp_folder``."""
        return 24

    def folder_clone(self) -> Optional[Tuple[Any, Any]]:
        """``(copy_folder, new_uid)`` for a platform whose experiment is copied as a folder of inputs, else ``None``."""
        return None

    # --- admin: the experiment page -----------------------------------------------------------------------------------

    #: template of the experiment page
    details_template: str = "admin/experiment_details.html"
    #: names of the template variables :meth:`details_context` provides (the page of other platforms sees ``None``)
    details_context_keys: Tuple[str, ...] = ()

    def details_context(self, experiment: Any) -> dict:
        """Template variables, named in ``details_context_keys``, that only the page of this platform uses."""
        return {}

    # --- admin: the frontend settings of an experiment ------------------------------------------------------------------

    #: setting keys the templates of the platform honour; ``None`` when they honour all of them
    frontend_capabilities: Optional[FrozenSet[str]] = None
    #: setting keys only this platform's templates read: the platforms that offer everything hide them
    frontend_exclusive_settings: FrozenSet[str] = frozenset()

    #: whether the LLM defaults of a new client start from the latest client of the experiment
    inherits_client_llm_defaults: bool = False

    # --- extension: what an installed platform adds to the application --------------------------------------------------

    #: folder ``ysocial_platform/`` of the platform repository; ``None`` for a built-in platform. Its ``templates/``
    #: are reachable as ``@<key>/<name>`` and its ``static/`` as ``/platform-static/<key>/<name>``
    package_dir: Optional[Path] = None

    #: dotted name of the package with the platform's own modules (``<package>.population``, ``<package>.human``...);
    #: ``None`` when the platform has none. The core reaches them only through :func:`y_web.platforms.registry.library`
    library_package: Optional[str] = None

    def library(self, name: str) -> Any:
        """A module of the platform's own package (see :attr:`library_package`)."""
        if not self.library_package:
            raise LookupError(f"platform {self.key!r} has no library")
        return importlib.import_module(f"{self.library_package}.{name}")

    #: table the runtime creates in every database of this platform and YSocial does not have: its presence tells the
    #: core never to apply the YSocial experiment schema to that database
    marker_table: Optional[str] = None

    #: whether the platform's participants live in the runtime's own database: YSocial binds no database for the
    #: experiment, adds no participant row to it and sends the participant to :meth:`observer_url`
    owns_database: bool = False

    # --- admin: the files of a run --------------------------------------------------------------------------------------

    def clear_run_artifacts(self, exp_folder: str) -> Optional[Tuple[int, List[str]]]:
        """Remove what a run left in ``exp_folder``; ``(removed, failed paths)``, or ``None`` for the generic clean-up."""
        return None

    def snapshot_for_download(self, folder: str, staging_dir: str) -> bool:
        """Copy ``folder`` consistently into ``staging_dir`` for a download; ``False`` when the platform zips the folder."""
        return False

    def carries_population_fields(self, population: Any) -> bool:
        """Whether the agents of ``population`` carry this platform's dedicated custom fields."""
        return False

    def owns_uploaded_folder(self, exp_dir: str) -> bool:
        """Whether an unpacked uploaded experiment folder is one of this platform's experiments."""
        return False

    def import_uploaded_experiment(
        self, exp_dir: str, uid: str, exp_name_override: str, exp_group: str
    ) -> Any:
        """Register the uploaded experiment unpacked in ``exp_dir``; returns the response to show."""
        raise NotImplementedError

    #: whether the client switches of the experiment page are mapped by the platform's own client forms
    maps_client_switches: bool = False

    def apply_experiment_switches(
        self, config: dict, original: Mapping[str, Any], **switches: Any
    ) -> bool:
        """Write the annotation/behaviour switches of the experiment page into a server ``config``.

        ``original`` is the configuration as it was read, before the core changed it. ``False`` leaves the generic
        write in place; a platform with a strict schema writes its own keys and returns ``True``.
        """
        return False

    def attach_routes(self) -> None:
        """Import the modules that add views to the blueprints of the core (see :mod:`y_web.sdk.routes`).

        Called once at startup, before the blueprints are registered; importing a module twice does nothing, so
        a second application in the same process is fine.
        """

    def blueprints(self) -> List[Any]:
        """Flask blueprints of the platform (participant pages, admin pages, APIs), registered at startup."""
        return []
