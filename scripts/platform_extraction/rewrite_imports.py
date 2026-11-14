"""Rewrite the core imports of moved platform modules into SDK imports (AST-spliced)."""

import ast, sys, re

MODELS = "y_web.sdk.models"


def table():
    t = {}

    def put(mod, names, target, rename=None):
        for n in names:
            t[(mod, n)] = (target, (rename or {}).get(n, n))

    put("y_web", ["db"], MODELS)
    put("y_web", ["prompt_store"], "y_web.sdk.runtime")
    put("y_web.src.system", ["prompt_packs"], "y_web.sdk.runtime")
    put(
        "y_web.src.system.path_utils",
        ["get_external_repo_dir", "get_writable_path"],
        "y_web.sdk.runtime",
    )
    put(
        "y_web.src.simulation.subprocess_env",
        ["build_subprocess_env", "python_command"],
        "y_web.sdk.runtime",
    )
    for m in ("ids", "ordering", "hot_rank", "service"):
        t[("commons:" + m, None)] = ("y_web.sdk.commons." + m, None)
    put("y_web.src.llm", ["Annotator", "ContentAnnotator"], "y_web.sdk.content")
    put("y_web.src.llm.url_summarizer", ["UrlSummarizer"], "y_web.sdk.content")
    put(
        "y_web.src.content.article_extractor",
        ["extract_article_info"],
        "y_web.sdk.content",
    )
    put(
        "y_web.src.content.text_utils",
        ["process_reddit_post", "strip_tags", "toxicity", "vader_sentiment"],
        "y_web.sdk.content",
    )
    put("y_web.hashtag_text", ["normalize_hashtag"], "y_web.sdk.content")
    put("y_web.src.federation", ["human_outbox"], "y_web.sdk.federation")
    put("y_web.src.federation.dynamic", ["population_added"], "y_web.sdk.federation")
    put(
        "y_web.src.recsys",
        ["get_suggested_users", "get_suggested_posts"],
        "y_web.sdk.social",
    )
    put(
        "y_web.src.data_access",
        [
            "get_posts_associated_to_emotion",
            "get_posts_associated_to_hashtags",
            "get_posts_associated_to_interest",
            "get_report_count",
            "get_trending_emotions",
            "get_trending_topics",
            "get_user_friends",
            "get_user_recent_posts",
            "get_safe_profile_pic",
        ],
        "y_web.sdk.social",
    )
    put("y_web.src.experiment.context", ["experiment_db_bind"], "y_web.sdk.social")
    put(
        "y_web.src.external_runtime.plugin_loader",
        ["active_modules_context"],
        "y_web.sdk.social",
    )
    put(
        "y_web.routes.social.helpers",
        [
            "_content_recsys_info",
            "get_adhoc_agent_badge",
            "get_author_type_badge",
            "is_admin",
        ],
        "y_web.sdk.social",
        {"_content_recsys_info": "content_recsys_info"},
    )

    put("y_web.src.system.miscellanea", ["check_privileges"], "y_web.sdk.web")
    put(
        "y_web.src.agents.custom_features",
        ["summarize_agent_custom_features_bulk"],
        "y_web.sdk.agents",
    )
    put(
        "y_web.src.data_access",
        [
            "augment_text",
            "get_elicited_emotions",
            "get_topics",
            "get_trending_hashtags",
            "get_unanswered_mentions",
        ],
        "y_web.sdk.social",
    )
    put(
        "y_web.src.data_access.posts",
        [
            "_hidden_author_ids_for_viewer",
            "_hidden_post_ids_in_thread",
            "_origin_community",
        ],
        "y_web.sdk.social",
        {
            "_hidden_author_ids_for_viewer": "hidden_author_ids_for_viewer",
            "_hidden_post_ids_in_thread": "hidden_post_ids_in_thread",
            "_origin_community": "origin_community",
        },
    )
    put(
        "y_web.src.experiment.context",
        ["get_db_bind_key_for_exp", "register_experiment_database"],
        "y_web.sdk.social",
    )
    put(
        "y_web.routes.social.helpers",
        [
            "_experiment_memory_enabled",
            "is_admin",
            "_forum_logged_user",
            "_forum_profile_pic",
            "_forum_current_profile_pic",
            "_forum_memory_enabled",
            "_forum_resolve_back_url",
            "_get_discussions",
            "build_thread_tree",
        ],
        "y_web.sdk.social",
        {
            "_experiment_memory_enabled": "experiment_memory_enabled",
            "_forum_logged_user": "logged_user",
            "_forum_profile_pic": "profile_pic_of",
            "_forum_current_profile_pic": "current_profile_pic",
            "_forum_memory_enabled": "feed_memory_enabled",
            "_forum_resolve_back_url": "resolve_back_url",
            "_get_discussions": "get_discussions",
        },
    )
    put(
        "y_web.routes.social.helpers",
        ["_load_ui_settings"],
        "y_web.sdk.web",
        {"_load_ui_settings": "load_ui_settings"},
    )
    put(
        "y_web.routes.interactions.common",
        ["_maybe_update_fb_interests"],
        "y_web.sdk.social",
        {"_maybe_update_fb_interests": "maybe_update_fb_interests"},
    )
    put(
        "y_web.routes.admin.sub.experiments._helpers",
        ["_experiment_configuration_update_required"],
        "y_web.sdk.web",
        {
            "_experiment_configuration_update_required": "experiment_configuration_update_required"
        },
    )
    for mod in ("_facts", "_llm", "_memory", "_server"):
        pass
    for mod, names in {
        "_facts": ["_build_facts_snapshot", "_format_facts_pack"],
        "_llm": [
            "_generate_reply",
            "_resolve_llm_backend",
            "_sanitize_interview_reply",
        ],
        "_memory": [
            "_build_memory_snapshot",
            "_build_persona_snapshot",
            "_detect_run_id_from_server_log",
            "_format_memory_pack",
            "_get_top_interests_for_user",
            "_resolve_interview_profile_pic",
        ],
        "_server": [
            "_ensure_experiment_db_bind",
            "_ensure_experiment_server_db_binding",
            "_memory_server_unavailable",
        ],
    }.items():
        put(
            "y_web.routes.api.interview." + mod,
            names,
            "y_web.sdk.interview",
            {n: n[1:] for n in names},
        )
    # the clients package
    put(
        "clients._crud",
        [
            "_apply_structured_features_to_agent_payload",
            "_build_client_creation_context",
            "_client_config_path_for_platform",
            "_collect_population_agent_attributes",
            "_get_experiment_folder_name",
        ],
        "y_web.sdk.web",
        {
            n: n[1:]
            for n in [
                "_apply_structured_features_to_agent_payload",
                "_build_client_creation_context",
                "_client_config_path_for_platform",
                "_collect_population_agent_attributes",
                "_get_experiment_folder_name",
            ]
        },
    )
    put("clients._helpers", ["allocate_topics_by_percentage"], "y_web.sdk.web")
    put("y_web.src.llm.vllm_manager", ["get_llm_models"], "y_web.sdk.web")
    put(
        "y_web.src.system.miscellanea",
        ["llm_backend_status", "get_db_type"],
        "y_web.sdk.web",
    )
    return t


TABLE = table()
MODEL_PREFIX = "y_web.src.models"


def convert(src, library_pkg, clients_pkg=False, in_actions=False):
    """library_pkg: how a moved module imports its siblings ('' none)."""
    tree = ast.parse(src)
    lines = src.split("\n")
    edits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        mod = node.module or ""
        if node.level and clients_pkg:
            mod = "clients." + mod if mod else "clients"
        elif node.level:
            continue
        indent = " " * node.col_offset
        new = []

        def emit(target, pairs):
            parts = ", ".join(a if b == a else f"{a} as {b}" for a, b in pairs)
            new.append(f"{indent}from {target} import {parts}")

        out = {}
        unknown = []
        for a in node.names:
            asn = a.asname or a.name
            if mod == MODEL_PREFIX or mod == "y_web.src.models":
                out.setdefault(MODELS, []).append((a.name, asn))
                continue
            if mod.startswith("y_web.src.commons."):
                out.setdefault("y_web.sdk.commons." + mod.split(".")[-1], []).append(
                    (a.name, asn)
                )
                continue
            if mod == "y_web.i18n" and a.name == "gettext":
                out.setdefault("y_web.sdk", []).append(("gettext", asn))
                continue
            key = (mod, a.name)
            if key in TABLE:
                tgt, nm = TABLE[key]
                out.setdefault(tgt, []).append((nm, asn))
                continue
            unknown.append(a.name)
        if not out and not unknown:
            continue
        if unknown and not out:
            continue  # leave (e.g. flask / stdlib / sibling imports handled elsewhere)
        if unknown:
            raise SystemExit(f"{mod}: unmapped {unknown} line {node.lineno}")
        for tgt, pairs in out.items():
            emit(tgt, pairs)
        edits.append((node.lineno, node.end_lineno, new, lines[node.lineno - 1]))
    for start, end, new, first in sorted(edits, reverse=True):
        # keep a trailing "# noqa" comment of the first line
        m = re.search(r"(#.*)$", first)
        if m and new:
            new[-1] += "  " + m.group(1)
        lines[start - 1 : end] = new
    return "\n".join(lines)


if __name__ == "__main__":
    f = sys.argv[1]
    print(convert(open(f).read(), "", clients_pkg="--clients" in sys.argv))
