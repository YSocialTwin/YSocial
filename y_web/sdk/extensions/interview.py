"""The interview services (facts, memory, persona, LLM reply) an extension reuses."""

from y_web.sdk.interview import (
    build_memory_snapshot,
    build_persona_snapshot,
    detect_run_id_from_server_log,
    ensure_experiment_db_bind,
    ensure_experiment_server_db_binding,
    format_memory_pack,
    generate_reply,
    get_top_interests_for_user,
    memory_server_unavailable,
    resolve_llm_backend,
)

from ._forward import forward

build_memory_snapshot_local_db = forward(
    "y_web.routes.api.interview._memory",
    "_build_memory_snapshot_local_db",
    name="build_memory_snapshot_local_db",
    doc="Memory snapshot read from the database of the experiment itself; same arguments as the core function.",
)
detect_run_id_from_experiment_db = forward(
    "y_web.routes.api.interview._memory",
    "_detect_run_id_from_experiment_db",
    name="detect_run_id_from_experiment_db",
    doc="Run id found in the database of the experiment; same arguments as the core function.",
)
get_top_interests_for_user_in_exp = forward(
    "y_web.routes.api.interview._memory",
    "_get_top_interests_for_user_in_exp",
    name="get_top_interests_for_user_in_exp",
    doc="Top interests of a user read from a given experiment; same arguments as the core function.",
)
normalize_llm_base_url = forward(
    "y_web.routes.api.interview._helpers",
    "_normalize_llm_base_url",
    name="normalize_llm_base_url",
    doc="Normalise the base URL of an LLM server; same arguments as the core function.",
)

__all__ = [
    "build_memory_snapshot",
    "build_memory_snapshot_local_db",
    "build_persona_snapshot",
    "detect_run_id_from_experiment_db",
    "detect_run_id_from_server_log",
    "ensure_experiment_db_bind",
    "ensure_experiment_server_db_binding",
    "format_memory_pack",
    "generate_reply",
    "get_top_interests_for_user",
    "get_top_interests_for_user_in_exp",
    "memory_server_unavailable",
    "normalize_llm_base_url",
    "resolve_llm_backend",
]
