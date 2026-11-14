import inspect, importlib, textwrap

SPECS = {
    "runtime": (
        '"""Where the runtimes live and how they are started and checked (paths, interpreter, run length, prompt packs).\n\nThe functions look the core up when called, so what the core (or a test) replaces is what a platform gets."""',
        [
            (
                "build_subprocess_env",
                "y_web.src.simulation.subprocess_env",
                "build_subprocess_env",
            ),
            (
                "describe_client_failure",
                "y_web.src.hpc.failures",
                "describe_client_failure",
            ),
            ("exit_messages", "y_web.src.hpc.failures", "exit_messages"),
            ("detect_env_handler", "y_web.src.simulation.server", "detect_env_handler"),
            (
                "get_external_repo_dir",
                "y_web.src.system.path_utils",
                "get_external_repo_dir",
            ),
            ("get_hpc_platform", "y_web.src.hpc.platforms", "get_hpc_platform"),
            ("get_writable_path", "y_web.src.system.path_utils", "get_writable_path"),
            ("python_command", "y_web.src.simulation.subprocess_env", "python_command"),
            ("remaining_days", "y_web.src.hpc.run_length", "remaining_days"),
            (
                "rewrite_server_config",
                "y_web.src.hpc.server_config",
                "rewrite_server_config",
            ),
            (
                "wait_for_hpc_server_ready",
                "y_web.src.hpc.client",
                "_wait_for_hpc_server_ready",
            ),
            (
                "build_hpc_runtime_client_id",
                "y_web.src.hpc.client",
                "_build_hpc_runtime_client_id",
            ),
            (
                "runtime_installed_and_visible",
                "y_web.src.external_runtime",
                "runtime_installed_and_visible",
            ),
            ("set_duration", "y_web.src.hpc.run_length", "set_duration"),
            ("is_vllm_installed", "y_web.src.llm.vllm_manager", "is_vllm_installed"),
            (
                "dispatch_platform_event",
                "y_web.src.external_runtime.plugin_loader",
                "dispatch_platform_event",
            ),
        ],
        "from y_web import prompt_store  # noqa: F401\nfrom y_web.src.system import prompt_packs  # noqa: F401\n",
        ["prompt_packs", "prompt_store"],
    ),
    "web": (
        '"""What a platform\'s views share with the rest of the web application: who may do what, and the page settings.\n\nThe functions look the core up when called, so what the core (or a test) replaces is what a platform gets."""',
        [
            (
                "build_client_creation_context",
                "y_web.routes.admin.sub.clients._crud",
                "_build_client_creation_context",
            ),
            ("check_privileges", "y_web.src.system.miscellanea", "check_privileges"),
            (
                "redirect_to_clients_page",
                "y_web.routes.admin.sub.clients._crud",
                "_redirect_to_clients_page",
            ),
            (
                "allocate_topics_by_percentage",
                "y_web.routes.admin.sub.clients._helpers",
                "allocate_topics_by_percentage",
            ),
            (
                "client_config_path_for_platform",
                "y_web.routes.admin.sub.clients._crud",
                "_client_config_path_for_platform",
            ),
            (
                "current_admin_user_or_none",
                "y_web.routes.admin.sub.experiments._helpers",
                "_current_admin_user_or_none",
            ),
            (
                "experiment_configuration_update_required",
                "y_web.routes.admin.sub.experiments._helpers",
                "_experiment_configuration_update_required",
            ),
            (
                "experiment_uses_llm_agents",
                "y_web.routes.admin.sub.experiments._helpers",
                "_experiment_uses_llm_agents",
            ),
            (
                "get_database_type",
                "y_web.routes.admin.sub.experiments._helpers",
                "_get_database_type",
            ),
            (
                "get_experiment_folder",
                "y_web.routes.admin.sub.experiments._helpers",
                "_get_experiment_folder",
            ),
            (
                "get_experiment_folder_name",
                "y_web.routes.admin.sub.clients._crud",
                "_get_experiment_folder_name",
            ),
            ("load_ui_settings", "y_web.routes.social.helpers", "_load_ui_settings"),
            (
                "load_feed_experiment_context",
                "y_web.routes.admin.sub.experiments._helpers",
                "_load_forum_experiment_context",
            ),
            (
                "read_json_if_exists",
                "y_web.routes.admin.sub.clients._crud",
                "_read_json_if_exists",
            ),
            (
                "get_client_population_pages",
                "y_web.routes.admin.sub.clients._crud",
                "_get_client_population_pages",
            ),
            (
                "extract_llm_names_from_population_payload",
                "y_web.routes.admin.sub.clients._crud",
                "_extract_llm_names_from_population_payload",
            ),
            (
                "build_hourly_activity_chart_series",
                "y_web.routes.admin.sub.clients._crud",
                "_build_hourly_activity_chart_series",
            ),
            (
                "hpc_prompts_filename",
                "y_web.routes.admin.sub.experiments._crud",
                "_hpc_prompts_filename",
            ),
            (
                "redirect_to_details_page",
                "y_web.routes.admin.sub.clients._details",
                "_redirect_to_details_page",
            ),
            (
                "opinion_configuration_internal",
                "y_web.routes.admin.sub.clients._opinion",
                "_opinion_configuration_internal",
            ),
            (
                "resolve_opinion_submission_context",
                "y_web.routes.admin.sub.clients._opinion",
                "_resolve_opinion_submission_context",
            ),
            (
                "apply_opinion_distributions_to_population",
                "y_web.routes.admin.sub.clients._opinion",
                "_apply_opinion_distributions_to_population",
            ),
            (
                "persist_non_hpc_opinion_dynamics",
                "y_web.routes.admin.sub.clients._opinion",
                "_persist_non_hpc_opinion_dynamics",
            ),
            (
                "invalidate_opinion_evolution_cache_for_experiment",
                "y_web.routes.admin.sub.clients._opinion",
                "_invalidate_opinion_evolution_cache_for_experiment",
            ),
            (
                "sync_initial_standard_opinions_to_experiment_db",
                "y_web.routes.admin.sub.clients._opinion",
                "_sync_initial_standard_opinions_to_experiment_db",
            ),
            (
                "update_client_simulation_internal",
                "y_web.routes.admin.sub.clients._recsys",
                "_update_client_simulation_internal",
            ),
            (
                "update_recsys_internal",
                "y_web.routes.admin.sub.clients._recsys",
                "_update_recsys_internal",
            ),
            (
                "update_client_llm_internal",
                "y_web.routes.admin.sub.clients._recsys",
                "_update_client_llm_internal",
            ),
            (
                "apply_population_attributes_to_client_config",
                "y_web.routes.admin.sub.clients._crud",
                "_apply_population_attributes_to_client_config",
            ),
            ("provider_of", "y_web.routes.admin.sub.clients._crud", "_provider_of"),
            (
                "opinion_dynamics_enabled_for_client_creation",
                "y_web.routes.admin.sub.clients._crud",
                "_opinion_dynamics_enabled_for_client_creation",
            ),
            (
                "memory_enabled_for_client_creation",
                "y_web.routes.admin.sub.clients._crud",
                "_memory_enabled_for_client_creation",
            ),
            ("get_llm_models", "y_web.src.llm.vllm_manager", "get_llm_models"),
            (
                "llm_backend_status",
                "y_web.src.system.miscellanea",
                "llm_backend_status",
            ),
            ("get_db_type", "y_web.src.system.miscellanea", "get_db_type"),
            (
                "read_feed_health",
                "y_web.routes.admin.sub.experiments._helpers",
                "_read_forum_feed_health",
            ),
            (
                "apply_structured_features_to_agent_payload",
                "y_web.routes.admin.sub.clients._crud",
                "_apply_structured_features_to_agent_payload",
            ),
            (
                "collect_population_agent_attributes",
                "y_web.routes.admin.sub.clients._crud",
                "_collect_population_agent_attributes",
            ),
            (
                "user_can_manage_experiment",
                "y_web.src.experiment.access",
                "user_can_manage_experiment",
            ),
            (
                "user_can_view_experiment",
                "y_web.src.experiment.access",
                "user_can_view_experiment",
            ),
        ],
        "",
        [],
    ),
    "federation": (
        '"""Federation features a platform takes part in: the outbox of humans, new populations and account confirmation."""',
        [
            ("confirm_account", "y_web.src.federation.humans", "confirm_account"),
            ("population_added", "y_web.src.federation.dynamic", "population_added"),
        ],
        "from y_web.src.federation import human_outbox  # noqa: F401\n",
        ["human_outbox"],
    ),
    "agents": (
        '"""The agent-side features every platform shares: the standard population code, the Appearance section, pictures."""',
        [
            (
                "delete_pictures_of",
                "y_web.src.agents.profile_pictures",
                "delete_pictures_of",
            ),
            (
                "picture_of_username",
                "y_web.src.agents.profile_pictures",
                "picture_of_username",
            ),
            (
                "random_cover_image_url",
                "y_web.src.content.cover_images",
                "random_cover_image_url",
            ),
            (
                "summarize_agent_custom_features_bulk",
                "y_web.src.agents.custom_features",
                "summarize_agent_custom_features_bulk",
            ),
        ],
        "from y_web.src.agents import appearance_form, population, profile_pictures  # noqa: F401\n",
        ["appearance_form", "population", "profile_pictures"],
    ),
    "social": (
        '"""What the pages a platform shows to its participants take from the core: the experiment database, the participant, mentions, suggestions and avatars.\n\nThe functions look the core up when called, so what the core (or a test) replaces is what a platform gets."""',
        [
            (
                "content_recsys_info",
                "y_web.routes.social.helpers",
                "_content_recsys_info",
            ),
            (
                "experiment_memory_enabled",
                "y_web.routes.social.helpers",
                "_experiment_memory_enabled",
            ),
            (
                "get_safe_profile_pic",
                "y_web.routes.social.helpers",
                "get_safe_profile_pic",
            ),
            ("is_admin", "y_web.routes.social.helpers", "is_admin"),
            (
                "get_unanswered_mentions",
                "y_web.src.data_access",
                "get_unanswered_mentions",
            ),
            (
                "ensure_experiment_user",
                "y_web.src.experiment.helpers",
                "ensure_experiment_user",
            ),
            (
                "get_experiment_engine_uri",
                "y_web.src.experiment.helpers",
                "get_experiment_engine_uri",
            ),
            (
                "open_experiment_session",
                "y_web.src.experiment.helpers",
                "open_experiment_session",
            ),
            (
                "get_suggested_users",
                "y_web.src.recsys.follow_recsys",
                "get_suggested_users",
            ),
            ("get_avatars_dir", "y_web.src.system.avatars_store", "get_avatars_dir"),
            ("logged_user", "y_web.routes.social.helpers", "_forum_logged_user"),
            ("profile_pic_of", "y_web.routes.social.helpers", "_forum_profile_pic"),
            (
                "current_profile_pic",
                "y_web.routes.social.helpers",
                "_forum_current_profile_pic",
            ),
            (
                "feed_memory_enabled",
                "y_web.routes.social.helpers",
                "_forum_memory_enabled",
            ),
            (
                "resolve_back_url",
                "y_web.routes.social.helpers",
                "_forum_resolve_back_url",
            ),
            ("get_discussions", "y_web.routes.social.helpers", "_get_discussions"),
            ("build_thread_tree", "y_web.routes.social.helpers", "build_thread_tree"),
            (
                "maybe_update_fb_interests",
                "y_web.routes.interactions.common",
                "_maybe_update_fb_interests",
            ),
            ("augment_text", "y_web.src.data_access", "augment_text"),
            ("get_elicited_emotions", "y_web.src.data_access", "get_elicited_emotions"),
            ("get_topics", "y_web.src.data_access", "get_topics"),
            ("get_trending_hashtags", "y_web.src.data_access", "get_trending_hashtags"),
            (
                "hidden_author_ids_for_viewer",
                "y_web.src.data_access.posts",
                "_hidden_author_ids_for_viewer",
            ),
            (
                "hidden_post_ids_in_thread",
                "y_web.src.data_access.posts",
                "_hidden_post_ids_in_thread",
            ),
            ("origin_community", "y_web.src.data_access.posts", "_origin_community"),
            (
                "get_adhoc_agent_badge",
                "y_web.routes.social.helpers",
                "get_adhoc_agent_badge",
            ),
            (
                "get_author_type_badge",
                "y_web.routes.social.helpers",
                "get_author_type_badge",
            ),
            (
                "get_posts_associated_to_emotion",
                "y_web.src.data_access",
                "get_posts_associated_to_emotion",
            ),
            (
                "get_posts_associated_to_hashtags",
                "y_web.src.data_access",
                "get_posts_associated_to_hashtags",
            ),
            (
                "get_posts_associated_to_interest",
                "y_web.src.data_access",
                "get_posts_associated_to_interest",
            ),
            ("get_report_count", "y_web.src.data_access", "get_report_count"),
            ("get_trending_emotions", "y_web.src.data_access", "get_trending_emotions"),
            ("get_trending_topics", "y_web.src.data_access", "get_trending_topics"),
            ("get_user_friends", "y_web.src.data_access", "get_user_friends"),
            ("get_user_recent_posts", "y_web.src.data_access", "get_user_recent_posts"),
            (
                "experiment_db_bind",
                "y_web.src.experiment.context",
                "experiment_db_bind",
            ),
            (
                "active_modules_context",
                "y_web.src.external_runtime.plugin_loader",
                "active_modules_context",
            ),
            ("get_suggested_posts", "y_web.src.recsys", "get_suggested_posts"),
            (
                "get_db_bind_key_for_exp",
                "y_web.src.experiment.context",
                "get_db_bind_key_for_exp",
            ),
            (
                "register_experiment_database",
                "y_web.src.experiment.context",
                "register_experiment_database",
            ),
        ],
        "",
        [],
    ),
    "content": (
        '"""Text, article and annotation helpers the pages and the actions of a platform share."""',
        [
            (
                "extract_article_info",
                "y_web.src.content.article_extractor",
                "extract_article_info",
            ),
            (
                "process_reddit_post",
                "y_web.src.content.text_utils",
                "process_reddit_post",
            ),
            ("strip_tags", "y_web.src.content.text_utils", "strip_tags"),
            ("toxicity", "y_web.src.content.text_utils", "toxicity"),
            ("vader_sentiment", "y_web.src.content.text_utils", "vader_sentiment"),
            ("normalize_hashtag", "y_web.hashtag_text", "normalize_hashtag"),
        ],
        "from y_web.src.llm import Annotator, ContentAnnotator  # noqa: F401\nfrom y_web.src.llm.url_summarizer import UrlSummarizer  # noqa: F401\n",
        ["Annotator", "ContentAnnotator", "UrlSummarizer"],
    ),
    "interview": (
        '"""What the interview endpoints expose to a platform that offers them on its own pages (facts, memory, persona, LLM reply)."""',
        [
            (
                "build_facts_snapshot",
                "y_web.routes.api.interview._facts",
                "_build_facts_snapshot",
            ),
            (
                "format_facts_pack",
                "y_web.routes.api.interview._facts",
                "_format_facts_pack",
            ),
            ("generate_reply", "y_web.routes.api.interview._llm", "_generate_reply"),
            (
                "resolve_llm_backend",
                "y_web.routes.api.interview._llm",
                "_resolve_llm_backend",
            ),
            (
                "sanitize_interview_reply",
                "y_web.routes.api.interview._llm",
                "_sanitize_interview_reply",
            ),
            (
                "build_memory_snapshot",
                "y_web.routes.api.interview._memory",
                "_build_memory_snapshot",
            ),
            (
                "build_persona_snapshot",
                "y_web.routes.api.interview._memory",
                "_build_persona_snapshot",
            ),
            (
                "detect_run_id_from_server_log",
                "y_web.routes.api.interview._memory",
                "_detect_run_id_from_server_log",
            ),
            (
                "format_memory_pack",
                "y_web.routes.api.interview._memory",
                "_format_memory_pack",
            ),
            (
                "get_top_interests_for_user",
                "y_web.routes.api.interview._memory",
                "_get_top_interests_for_user",
            ),
            (
                "resolve_interview_profile_pic",
                "y_web.routes.api.interview._memory",
                "_resolve_interview_profile_pic",
            ),
            (
                "ensure_experiment_db_bind",
                "y_web.routes.api.interview._server",
                "_ensure_experiment_db_bind",
            ),
            (
                "ensure_experiment_server_db_binding",
                "y_web.routes.api.interview._server",
                "_ensure_experiment_server_db_binding",
            ),
            (
                "memory_server_unavailable",
                "y_web.routes.api.interview._server",
                "_memory_server_unavailable",
            ),
        ],
        "",
        [],
    ),
}
for mod, (doc, funcs, extra_import, extra_names) in SPECS.items():
    out = [doc, "", "from __future__ import annotations", ""]
    if extra_import:
        out.append(extra_import)
    out.append("")
    names = []
    for name, src_mod, src_name in funcs:
        fn = getattr(importlib.import_module(src_mod), src_name)
        sig = inspect.signature(fn)
        sig_s = str(sig).replace("y_web.src.hpc.platforms.HpcPlatform", "'HpcPlatform'")
        params = []
        for p in sig.parameters.values():
            if p.kind == p.VAR_POSITIONAL:
                params.append("*" + p.name)
            elif p.kind == p.VAR_KEYWORD:
                params.append("**" + p.name)
            elif p.kind == p.KEYWORD_ONLY:
                params.append(f"{p.name}={p.name}")
            else:
                params.append(p.name)
        doc_line = (inspect.getdoc(fn) or "").split("\n")[0]
        out.append("")
        out.append(f"def {name}{sig_s}:")
        if doc_line:
            out.append(f'    """{doc_line}"""')
        out.append(f"    from {src_mod} import {src_name} as target")
        out.append("")
        out.append(f"    return target({', '.join(params)})")
        out.append("")
        names.append(name)
    allnames = sorted(names + extra_names)
    out.append("")
    out.append("__all__ = [")
    for n in allnames:
        out.append(f'    "{n}",')
    out.append("]")
    open(f"y_web/sdk/{mod}.py", "w").write("\n".join(out) + "\n")
