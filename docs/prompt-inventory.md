# Prompt inventory (step 0 of the multilingual prompts task)

Status: first pass for gate G0. Generated tables come from `scripts/prompts/inventory_scan.py` (static scan, heuristic: it over-counts UI messages and database comparisons); the sections written by hand are marked. Nothing in the code was changed to produce this file.

## Findings that differ from the task document (hand-written)

1. **The Reddit client has 51 prompt keys, not 20.** `external/YClientReddit/config_files/prompts.json` adds comment and share styles (`handler_comment_QUICK_AFFIRM`, `..._TROLL`, `handler_share_CRITICAL_ESSAY`, ...), the memory prompts (`handler_memory_*`), mention and thread browsing decisions, high-affect classifiers and rewrite/repair prompts. `data_schema/prompts_forum.json` in YWeb has 20.
2. **Prompt files are duplicated and not identical.** YWeb `data_schema/prompts.json` (18 keys), YClient `config_files/prompts.json` (20 keys) and YClientReddit `config_files/prompts.json` (51 keys) share key names but have different text and different sets of fields (for example `self.profession` appears in YWeb but not in YClient's `agent_roleplay_simple`). A single source of truth has to be chosen before packs are built.
3. **Many prompts live in Python, not in JSON.** `YClientReddit/y_client/classes/base_agent.py` holds about 50 prompt-like literals (memory reflections, community digest, browsing, style selection, moderation); YClient `base_agent.py` about 11; YSimulator `llm_service.py` and `vllm_service.py` about 80 together plus `batch_processor.py`, `reply_generator.py`, `reply_handler.py`; YPhotoSharing's services about 30; `y_agents_plugins` plugins (propaganda, comic relief, stress attacker, moderator, master of puppets) about 35; `reactive_agents/adapter.py` about 19; and YWeb has prompts in `src/llm/content_annotation.py`, `src/llm/image_annotator.py` and `routes/api/interview/`.
4. **`eval` is only in the microblogging and Reddit clients** (6 sites, listed below). YSimulator and YPhotoSharing render with `str.format` (48 sites in YSimulator), which cannot run code but does fail on a missing or renamed field.
5. **HPC and photo prompts are nested** (`system_template` / `user_template` per action) and `evaluate_opinion` has a user template built dynamically in `llm_service.py`.

## Protocol tokens read from model answers (hand-triaged from the parser candidates below)

Parsers compare whole uppercase English words with the answer, for example `"COMMENT" in text.split()` after `upper()` and `"YES" in text.split()` (YClient `base_agent.py`); a token followed by punctuation (`NEUTRAL.`) does not match.

| Decision | Tokens | Where (function) |
| --- | --- | --- |
| Action choice, microblogging | `COMMENT`, `POST`, `READ`, `SEARCH`, `FOLLOW`, `SHARE`, `CAST`, `IMAGE` | YClient `base_agent.select_action`, `select_action_lite`, and the fake agent |
| Action choice, Reddit | the same plus `NEWS`, `SHARE_IMAGE`, `SHARE_LINK` | YClientReddit `base_agent.select_action`, `select_image` |
| Follow and reciprocal follow | `YES` (anything else counts as no) | `__evaluate_follow`, `_should_reciprocate_follow_event` |
| Reaction to a post | `YES`, `NO`, `NEUTRAL` (Reddit also `NEUTRAL`) | `reaction` |
| Vote | `LEFT`, `RIGHT`, `NONE` | `cast` |
| Moderation report | `REPORT`, `REPORT_TOXIC`, `REPORT_OFFENSIVE`, `TOXIC`, `OFFENSIVE` | `_extract_report_type` |
| Reddit comment skip | `SKIP` | YClientReddit `comment` |
| Opinion evaluation | `AGREE`, `DISAGREE`, `NEUTRAL` | `llm_evaluation` in the four clients, `evaluate_opinion` and its batch version in YSimulator, `reactive_agents/opinion_dynamics.py` |
| HPC reactions | `COMMENT`, `LIKE` | YSimulator `decide_reaction`, `decide_reaction_batch`; `reactive_agents` `decide_photo_reaction`, `decide_thread_reaction` |
| HPC read reaction | `IGNORE`, `LIKE`, `LOVE`, `LAUGH`, `ANGRY`, `SAD`, `DISLIKE`, `COMMENT`, `SHARE`, `REPORT`, `REPORT_TOXIC`, `REPORT_OFFENSIVE`, `TOXIC`, `OFFENSIVE` | YSimulator `generate_read_reaction` (+ batch) and `batch_processor` |
| HPC search action | `COMMENT`, `SHARE` and the reactions above | YSimulator `decide_search_action`, `_process_vllm_search_batch` |
| Photo sharing | `FOLLOW`; `ACCEPT`; `POSITIVE`, `NEGATIVE`; `IGNORE`, `LAUGH`, `LIKE`, `LOVE` | YPhotoSharing `decide_follow`, `decide_follow_request`, `extract_sentiment`, `react_to_photo` |
| Generic yes/no | `yes`, `no`, `follow`, `unfollow`, `ignore` | YSimulator `llm_utils/response_parser.parse_boolean_response` |

JSON answers (the code reads fields, not tokens): the stress/reward annotation (`tone`, `directness`, `support_strength`, with tone values `positive|neutral|critical|hostile|supportive` or `hostile|supportive`), the Reddit memory social card (`summary_text`), and the other `handler_memory_*` prompts, community digest and thread card (field names in the prompt text), the GoEmotions emotion list and topic lists (`content_annotation.py`, `extract_emotions`, `extract_article_topics`). Their parsers are not in the candidate list below because they do not compare strings; their field names must still be treated as protocol and live in the shared token module (step 2).

Triage notes: a match is **not** a protocol token when it is an internal action name stored in the database (`follow`, `comment`, `share`, `post` in the stress/reward, memory, server and plugin code), a configuration value (`NULL`, `EMPTY`, `INT`, `CUDA_VISIBLE_DEVICES`, `ALIVE`, the `yes` flags of `moderator.py` and `stress_attacker.py`), or an internal event type of `y_agents_plugins/runtime/executor.py` (`CREATE_POST`, `APPLY_MODERATION`, ...). `y_agents_plugins` contains no parser of model answers in this scan; its plugins write prompts (propaganda, comic relief, stress attacker, moderator) that are in the literal counts.

Still to confirm in step 2: the exact synonyms each parser accepts (for example whether `DISLIKE` or `OFFENSIVE` are real model answers or only mapped values), and whether the YWeb interview and annotation code parses JSON from the model (`y_web/src/llm/content_annotation.py`).

## Generated tables

### Prompt files

| File | Keys | Nested groups | sha256 (12) |
| --- | --- | --- | --- |
| `data_schema/prompts.json` | 18 | 0 | `14a0930a90b9` |
| `data_schema/prompts_forum.json` | 20 | 0 | `51b62c428f2e` |
| `data_schema/prompts_hpc.json` | 22 | 19 | `042b5cf34f61` |
| `data_schema/prompts_ygram.json` | 28 | 25 | `159c0a04e970` |
| `external/YClient/config_files/prompts.json` | 20 | 0 | `356ec765f952` |
| `external/YClientReddit/config_files/prompts.json` | 51 | 0 | `533e8f3f04a1` |
| `external/YPhotoSharing/example/prompts_ygram.json` | 12 | 12 | `b13b25636787` |

### Template fields found in the prompt files

`action`, `actions`, `ag`, `age`, `agent_personality`, `article.summary`, `article.title`, `article['summary']`, `article['title']`, `article_summary`, `article_summary_snippet`, `article_text`, `article_title`, `author`, `author_label`, `author_name`, `author_username`, `behavior_labels`, `bio`, `caption`, `co`, `community_digest`, `context_text`, `conv`, `current_label`, `current_opinion`, `day`, `descr`, `description`, `dominant_view_block`, `draft_text`, `emotion_list`, `event_type`, `evidence`, `evidence_lines`, `ex`, `gender`, `image_description`, `incoming_text`, `interests_str`, `known_usernames`, `max_chars`, `max_sentences`, `memory_argument_hint`, `memory_callback_hint`, `memory_context_text`, `memory_cues_block`, `memory_scope`, `memory_tone_hint`, `mention_author`, `mention_instruction`, `mention_text`, `mode`, `my_text`, `name`, `nationality`, `ne`, `num_styles`, `oe`, `old_summary`, `opinion_options`, `opinion_scale`, `options`, `other_text`, `other_username`, `parent_snippet`, `persona`, `political_leaning`, `post_content`, `post_text`, `prev_digest`, `proactive_affect_block`, `profession`, `reason`, `recalled_memories_block`, `recent_roots_text`, `relationship_actor`, `relationship_hint`, `relationship_target`, `relationship_target_id`, `reply_allowed`, `reply_block_reasons`, `scan_snippets`, `self.ag`, `self.age`, `self.co`, `self.education_level`, `self.ex`, `self.gender`, `self.language`, `self.leaning`, `self.name`, `self.nationality`, `self.ne`, `self.oe`, `self.profession`, `self.replying_to`, `self.topics_opinions`, `self.topics_sentiment`, `self.toxicity`, `share_styles_list`, `slot`, `styles_list`, `subreddit_vibe`, `target_archetype`, `target_quality_hint`, `target_username`, `text`, `thread_context`, `thread_context_instruction`, `thread_snippet`, `topic`, `topic_instruction`, `topics`, `topics_instruction`, `toxicity`, `url`, `username`, `website.leaning`, `website.name`, `website_name`

### Code scan per repository

| Repository | Prompt-like literals | eval/exec | str.format | Answer comparisons |
| --- | --- | --- | --- | --- |
| YWeb | 104 | 0 | 8 | 41 |
| YClient | 17 | 3 | 0 | 53 |
| YClientReddit | 63 | 3 | 1 | 60 |
| YSimulator | 132 | 0 | 48 | 137 |
| YPhotoSharing | 37 | 0 | 0 | 24 |
| y_agents_plugins | 37 | 0 | 0 | 13 |
| reactive_agents | 24 | 0 | 0 | 12 |

### eval / exec sites

- `external/YClient/y_client/classes/base_agent.py:776` eval
- `external/YClient/y_client/classes/fake_page_agent.py:208` eval
- `external/YClient/y_client/classes/page_agent.py:247` eval
- `external/YClientReddit/y_client/classes/base_agent.py:7358` eval
- `external/YClientReddit/y_client/classes/fake_page_agent.py:204` eval
- `external/YClientReddit/y_client/classes/page_agent.py:293` eval

### Files with prompt-like literals

| File | Literals |
| --- | --- |
| `y_web/routes/admin/sub/agents.py` | 10 |
| `y_web/routes/admin/sub/clients/_crud.py` | 4 |
| `y_web/routes/admin/sub/clients/_execution.py` | 4 |
| `y_web/routes/admin/sub/experiments/_crud.py` | 10 |
| `y_web/routes/admin/sub/experiments/_data.py` | 9 |
| `y_web/routes/admin/sub/experiments/_external_runtimes.py` | 4 |
| `y_web/routes/admin/sub/experiments/_helpers.py` | 7 |
| `y_web/routes/admin/sub/experiments/_notifications.py` | 3 |
| `y_web/routes/admin/sub/users.py` | 15 |
| `y_web/routes/api/interview/_routes.py` | 5 |
| `y_web/routes/api/social.py` | 5 |
| `y_web/src/llm/content_annotation.py` | 6 |
| `external/YClient/y_client/classes/base_agent.py` | 11 |
| `external/YClientReddit/y_client/classes/base_agent.py` | 50 |
| `external/YClientReddit/y_client/classes/fake_base_agent.py` | 3 |
| `external/YSimulator/YSimulator/YClient/LLM_interactions/llm_service.py` | 36 |
| `external/YSimulator/YSimulator/YClient/LLM_interactions/vllm_service.py` | 46 |
| `external/YSimulator/YSimulator/YClient/action_generators/reply_generator.py` | 11 |
| `external/YSimulator/YSimulator/YClient/llm_utils/load_balancer.py` | 3 |
| `external/YSimulator/YSimulator/YClient/reply_handler.py` | 11 |
| `external/YSimulator/YSimulator/YClient/simulation/batch_processor.py` | 19 |
| `external/YPhotoSharing/YPhotoSharing/YClient/LLM_interactions/remote_batch_service.py` | 15 |
| `external/YPhotoSharing/YPhotoSharing/YClient/LLM_interactions/vllm_service.py` | 15 |
| `external/y_agents_plugins/src/y_agents_plugins/plugins/comic_relief.py` | 8 |
| `external/y_agents_plugins/src/y_agents_plugins/plugins/master_of_puppets.py` | 4 |
| `external/y_agents_plugins/src/y_agents_plugins/plugins/moderator.py` | 4 |
| `external/y_agents_plugins/src/y_agents_plugins/plugins/propaganda.py` | 10 |
| `external/y_agents_plugins/src/y_agents_plugins/plugins/stress_attacker.py` | 8 |
| `external/y_agents_plugins/src/y_agents_plugins/runtime/loader.py` | 3 |
| `external/reactive_agents/src/reactive_agents/adapter.py` | 19 |
| `external/reactive_agents/src/reactive_agents/opinion_dynamics.py` | 3 |

### Answer comparisons in LLM-facing files

| File | Lines |
| --- | --- |
| `y_web/routes/admin/sub/agents.py` | 564, 1178 |
| `y_web/routes/admin/sub/experiments/_crud.py` | 3388, 3388 |
| `y_web/routes/admin/sub/experiments/_data.py` | 2862, 2862, 2976, 2976 |
| `y_web/routes/admin/sub/experiments/_opinion.py` | 4354, 4356, 4415, 4426, 4509, 4528, 4660, 4662, 4665, 4670, 4677, 4733, 4753, 4783, 7110, 7128, 7130 |
| `y_web/routes/api/reddit.py` | 155 |
| `y_web/routes/api/social.py` | 233 |
| `y_web/routes/social/common.py` | 356 |
| `y_web/src/forum/service/formatters.py` | 501, 523 |
| `external/YClient/y_client/classes/base_agent.py` | 3129, 3255, 3314, 3333, 3354, 3356, 3502, 3502, 3572, 3572, 3583, 3583, 3596, 3596, 3607, 3607, 3620, 3620, 3626, 3626, 3653, 3653, 3664, 3664, 3675 |
| `external/YClient/y_client/classes/fake_base_agent.py` | 418, 445, 568, 568, 608, 608, 619, 619, 630, 630, 641, 641, 654, 654, 660, 660 |
| `external/YClient/y_client/stress_reward/update_system.py` | 290, 294, 298, 302, 305 |
| `external/YClientReddit/y_client/classes/base_agent.py` | 4088, 7129, 7143, 7161, 7169, 9432, 9451, 9565, 9605, 9668, 11037, 11051, 11062, 11068, 11242, 11303, 11324, 11347, 11349, 11498, 11498, 11534, 11534, 11566, 11566 |
| `external/YClientReddit/y_client/classes/fake_base_agent.py` | 496, 636, 760, 760, 804, 804, 815, 815, 826, 826, 837, 837, 850, 850, 866, 866 |
| `external/YClientReddit/y_client/clients/client_base.py` | 72, 72 |
| `external/YClientReddit/y_client/clients/client_web.py` | 93, 93 |
| `external/YClientReddit/y_client/stress_reward/update_system.py` | 186, 189, 192, 195, 197 |
| `external/YSimulator/YSimulator/YClient/LLM_interactions/llm_service.py` | 505, 505, 864, 864, 967, 967, 969, 969, 981, 981, 1035, 1035, 1036 |
| `external/YSimulator/YSimulator/YClient/LLM_interactions/vllm_service.py` | 1218, 1218, 1290, 1290, 1401, 1401, 1403, 1403, 1855, 1855, 1917, 1917, 1919, 1919, 1931, 1931, 1967, 1967, 1968 |
| `external/YSimulator/YSimulator/YClient/action_generators/read_generator.py` | 213 |
| `external/YSimulator/YSimulator/YClient/action_generators/search_generator.py` | 161, 170 |
| `external/YSimulator/YSimulator/YClient/actions/llm_actions.py` | 351, 353 |
| `external/YSimulator/YSimulator/YClient/actions/rule_based_actions.py` | 215, 215 |
| `external/YSimulator/YSimulator/YClient/activity_selector.py` | 262 |
| `external/YSimulator/YSimulator/YClient/client.py` | 758, 788, 788, 806, 806 |
| `external/YSimulator/YSimulator/YClient/memory_runtime.py` | 708, 708, 734, 734, 807, 807 |
| `external/YSimulator/YSimulator/YClient/simulation/batch_processor.py` | 816, 816, 846, 846, 928, 928, 933, 933, 1060, 1062, 1519, 1519, 1537, 1537, 1618, 1618, 1625, 1625, 1793, 1793, 1852, 1852 |
| `external/YSimulator/YSimulator/YClient/simulation/round_executor.py` | 182 |
| `external/YSimulator/YSimulator/YClient/simulation/secondary_follow_processor.py` | 117, 122, 134, 138, 155, 177, 177, 179, 179 |
| `external/YSimulator/YSimulator/YClient/stress_reward/update_system.py` | 159, 162, 165 |
| `external/YSimulator/YSimulator/YServer/opinion_dynamics/opinion_handler.py` | 201 |
| `external/YSimulator/YSimulator/YServer/schema_migrations.py` | 108 |
| `external/YSimulator/YSimulator/YServer/server.py` | 1368 |
| `external/YPhotoSharing/YPhotoSharing/YClient/LLM_interactions/llm_service.py` | 549, 549 |
| `external/YPhotoSharing/YPhotoSharing/YClient/LLM_interactions/remote_batch_service.py` | 389, 389 |
| `external/YPhotoSharing/YPhotoSharing/YClient/LLM_interactions/vllm_service.py` | 296, 296 |
| `external/YPhotoSharing/YPhotoSharing/YClient/actions/follow.py` | 66, 66 |
| `external/YPhotoSharing/YPhotoSharing/YClient/actions/react.py` | 73, 73 |
| `external/YPhotoSharing/YPhotoSharing/YClient/agent_management/agent.py` | 206, 206, 269, 271, 273, 275, 283 |
| `external/YPhotoSharing/YPhotoSharing/YClient/simulation/round_planner.py` | 32 |
| `external/YPhotoSharing/YPhotoSharing/YClient/stress_reward/update_system.py` | 237, 240 |
| `external/YPhotoSharing/YPhotoSharing/YServer/classes/db_middleware.py` | 1213 |
| `external/YPhotoSharing/YPhotoSharing/YServer/opinion_dynamics/opinion_handler.py` | 220 |
| `external/YPhotoSharing/YPhotoSharing/YServer/services/moderation_service.py` | 73, 105 |
| `external/y_agents_plugins/src/y_agents_plugins/db/experiment.py` | 746, 1769, 1771 |
| `external/y_agents_plugins/src/y_agents_plugins/plugins/comic_relief.py` | 34 |
| `external/y_agents_plugins/src/y_agents_plugins/plugins/master_of_puppets.py` | 341, 476, 688 |
| `external/y_agents_plugins/src/y_agents_plugins/runtime/executor.py` | 562 |
| `external/y_agents_plugins/src/y_agents_plugins/stress_reward/update_system.py` | 248, 251, 254, 257, 259 |
| `external/reactive_agents/src/reactive_agents/adapter.py` | 414, 414 |
| `external/reactive_agents/src/reactive_agents/continuity.py` | 199 |
| `external/reactive_agents/src/reactive_agents/photo_events.py` | 244, 304, 304 |
| `external/reactive_agents/src/reactive_agents/secondary_dynamics.py` | 125, 125 |
| `external/reactive_agents/src/reactive_agents/writer.py` | 308, 717, 717, 1013 |

### Parser candidates (function and the protocol-looking words it compares)

- `external/YClient/y_client/classes/base_agent.py`
  - `_apply_stress_reward_comment`: `neutral`
  - `reaction`: `NO`, `YES`, `follow`
  - `__evaluate_follow`: `YES`, `follow`
  - `_should_reciprocate_follow_event`: `YES`, `follow`
  - `cast`: `LEFT`, `NONE`, `RIGHT`
  - `select_action`: `CAST`, `COMMENT`, `FOLLOW`, `IMAGE`, `POST`, `READ`, `SEARCH`, `SHARE`
  - `select_action_lite`: `CAST`, `COMMENT`, `FOLLOW`, `IMAGE`, `POST`, `READ`, `SEARCH`, `SHARE`
  - `_has_usable_llm_config`: `none`, `null`
  - `_memory_after_vote`: `like`
  - `_extract_report_type`: `OFFENSIVE`, `REPORT`, `REPORT_OFFENSIVE`, `REPORT_TOXIC`, `TOXIC`
  - `handle_reciprocal_follow_event`: `follow`, `unfollow`
- `external/YClient/y_client/classes/fake_base_agent.py`
  - `reaction`: `NO`, `YES`, `follow`
  - `__evaluate_follow`: `YES`, `follow`
  - `cast`: `LEFT`, `NONE`, `RIGHT`
  - `select_action`: `CAST`, `COMMENT`, `FOLLOW`, `IMAGE`, `POST`, `READ`, `SEARCH`, `SHARE`
- `external/YClient/y_client/llm/autogen_compat.py`
  - `_normalize_llm_config`: `NULL`
  - `_looks_like_ollama`: `EMPTY`, `NULL`
- `external/YClient/y_client/opinion_dynamics/confidence_bound.py`
  - `bounded_confidence`: `neutral`
- `external/YClient/y_client/opinion_dynamics/llm_evaluation.py`
  - `llm_evaluation`: `AGREE`, `DISAGREE`, `neutral`
- `external/YClient/y_client/stress_reward/update_system.py`
  - `_compute_delta`: `comment`, `share`
- `external/YClientReddit/y_client/classes/base_agent.py`
  - `_apply_stress_reward_comment`: `neutral`
  - `_memory_is_low_toxicity_profile`: `no`
  - `_enforce_text_limits`: `comment`, `post`
  - `_select_comment_target_via_thread_browse`: `comment`, `none`
  - `comment`: `SKIP`
  - `reaction`: `NEUTRAL`, `NO`, `YES`, `follow`
  - `vote`: `like`
  - `__evaluate_follow`: `YES`, `follow`
  - `_should_reciprocate_follow_event`: `YES`, `follow`
  - `cast`: `LEFT`, `NONE`, `RIGHT`
  - `select_action`: `CAST`, `COMMENT`, `FOLLOW`, `IMAGE`, `NEWS`, `POST`, `READ`, `SEARCH`, `SHARE`, `SHARE_IMAGE`, `SHARE_LINK`
  - `reply`: `reply`
  - `_to_bool`: `yes`
  - `_memory_extract_behavior_labels`: `angry`, `disagree`
  - `_memory_format_conversation_cues`: `none`
  - `_memory_after_vote_legacy`: `like`
  - `_extract_report_type`: `OFFENSIVE`, `REPORT`, `REPORT_OFFENSIVE`, `REPORT_TOXIC`, `TOXIC`
  - `handle_reciprocal_follow_event`: `follow`, `unfollow`
  - `select_image`: `NEWS`
  - `_memory_get_relationship_signal_for_user`: `angry`, `disagree`
- `external/YClientReddit/y_client/classes/fake_base_agent.py`
  - `reaction`: `NO`, `YES`, `follow`
  - `__evaluate_follow`: `YES`, `follow`
  - `cast`: `LEFT`, `NONE`, `RIGHT`
  - `select_action`: `CAST`, `COMMENT`, `FOLLOW`, `IMAGE`, `NEWS`, `POST`, `READ`, `SEARCH`, `SHARE`, `SHARE_IMAGE`, `SHARE_LINK`
  - `select_image`: `NEWS`
- `external/YClientReddit/y_client/clients/client_base.py`
  - `__init__`: `SHARE`
- `external/YClientReddit/y_client/clients/client_web.py`
  - `__init__`: `SHARE`
- `external/YClientReddit/y_client/llm/autogen_compat.py`
  - `_normalize_llm_config`: `NULL`
  - `_looks_like_ollama`: `EMPTY`, `NULL`
- `external/YClientReddit/y_client/opinion_dynamics/confidence_bound.py`
  - `bounded_confidence`: `neutral`
- `external/YClientReddit/y_client/opinion_dynamics/llm_evaluation.py`
  - `llm_evaluation`: `AGREE`, `DISAGREE`, `neutral`
- `external/YClientReddit/y_client/stress_reward/update_system.py`
  - `_compute_delta`: `comment`, `share`
- `external/YSimulator/YSimulator/YClient/LLM_interactions/llm_service.py`
  - `decide_reaction`: `COMMENT`, `LIKE`
  - `generate_read_reaction`: `ANGRY`, `DISLIKE`, `IGNORE`, `LAUGH`, `LIKE`, `LOVE`, `OFFENSIVE`, `REPORT`, `REPORT_OFFENSIVE`, `REPORT_TOXIC`, `SAD`, `TOXIC`
  - `decide_search_action`: `ANGRY`, `COMMENT`, `IGNORE`, `LAUGH`, `LIKE`, `LOVE`, `SAD`, `SHARE`
  - `generate_reciprocal_follow_decision`: `follow`, `unfollow`
  - `evaluate_opinion`: `AGREE`, `DISAGREE`, `NEUTRAL`
- `external/YSimulator/YSimulator/YClient/LLM_interactions/remote_batch_service.py`
  - `_headers`: `NULL`
  - `_probe_openai_batch_support`: `NULL`
- `external/YSimulator/YSimulator/YClient/LLM_interactions/vllm_service.py`
  - `decide_reaction`: `COMMENT`, `LIKE`
  - `generate_read_reaction`: `ANGRY`, `DISLIKE`, `IGNORE`, `LAUGH`, `LIKE`, `LOVE`, `OFFENSIVE`, `REPORT`, `REPORT_OFFENSIVE`, `REPORT_TOXIC`, `SAD`, `TOXIC`
  - `decide_search_action`: `ANGRY`, `COMMENT`, `IGNORE`, `LAUGH`, `LIKE`, `LOVE`, `SAD`, `SHARE`
  - `generate_reciprocal_follow_decision`: `follow`, `unfollow`
  - `evaluate_opinion`: `AGREE`, `DISAGREE`, `NEUTRAL`
  - `decide_reaction_batch`: `COMMENT`, `LIKE`
  - `generate_read_reaction_batch`: `ANGRY`, `COMMENT`, `LAUGH`, `LIKE`, `LOVE`, `SAD`, `SHARE`
  - `evaluate_opinion_batch`: `AGREE`, `DISAGREE`, `NEUTRAL`
- `external/YSimulator/YSimulator/YClient/action_generators/read_generator.py`
  - `generate`: `IGNORE`
- `external/YSimulator/YSimulator/YClient/action_generators/search_generator.py`
  - `generate`: `comment`, `share`
- `external/YSimulator/YSimulator/YClient/actions/rule_based_actions.py`
  - `generate_rule_based_read`: `IGNORE`
- `external/YSimulator/YSimulator/YClient/activity_selector.py`
  - `select_action`: `follow`
- `external/YSimulator/YSimulator/YClient/client.py`
  - `_attach_stress_reward_payload`: `ANGRY`, `COMMENT`, `FOLLOW`, `LAUGH`, `LIKE`, `LOVE`, `POST`, `REPORT`, `SAD`, `SHARE`, `UNFOLLOW`, `neutral`
- `external/YSimulator/YSimulator/YClient/llm_utils/gpu_utils.py`
  - `get_all_gpu_memory_info`: `CUDA_VISIBLE_DEVICES`
- `external/YSimulator/YSimulator/YClient/llm_utils/load_balancer.py`
  - `_discover_existing_vllm_pool`: `ALIVE`
- `external/YSimulator/YSimulator/YClient/llm_utils/response_parser.py`
  - `parse_boolean_response`: `follow`, `ignore`, `no`, `unfollow`, `yes`
- `external/YSimulator/YSimulator/YClient/memory_runtime.py`
  - `_record_single_action`: `ANGRY`, `COMMENT`, `LAUGH`, `LIKE`, `LOVE`, `POST`, `SAD`, `SHARE`
- `external/YSimulator/YSimulator/YClient/opinion_dynamics/llm_evaluation.py`
  - `llm_evaluation`: `AGREE`, `DISAGREE`, `neutral`
- `external/YSimulator/YSimulator/YClient/simulation/batch_processor.py`
  - `_process_vllm_search_batch`: `ANGRY`, `COMMENT`, `LAUGH`, `LIKE`, `LOVE`, `SAD`, `SHARE`
  - `_gather_reactions_with_vllm_batch`: `comment`, `read`, `share`
  - `_process_vllm_read_batch`: `IGNORE`, `REPORT_TOXIC`, `SHARE`
  - `_batch_evaluate_and_update_opinions`: `AGREE`, `DISAGREE`
  - `_gather_reactions_standard`: `IGNORE`, `REPORT_TOXIC`, `SHARE`
- `external/YSimulator/YSimulator/YClient/simulation/round_executor.py`
  - `execute_round`: `comment`, `follow`, `post`, `read`, `search`, `share`
- `external/YSimulator/YSimulator/YClient/simulation/secondary_follow_processor.py`
  - `process_reciprocal_follows`: `FOLLOW`, `UNFOLLOW`
  - `process_secondary_follows`: `follow`, `unfollow`
- `external/YSimulator/YSimulator/YClient/simulation/simulator.py`
  - `run`: `WAIT`
- `external/YSimulator/YSimulator/YClient/stress_reward/update_system.py`
  - `_compute_delta`: `comment`, `share`
- `external/YSimulator/YSimulator/YServer/opinion_dynamics/opinion_handler.py`
  - `_get_neighbors_opinions_sql`: `follow`
- `external/YSimulator/YSimulator/YServer/schema_migrations.py`
  - `ensure_moderation_schema`: `post`
- `external/YSimulator/YSimulator/YServer/server.py`
  - `check_follow_relationship`: `follow`
- `external/YSimulator/YSimulator/YServer/services/memory_service.py`
  - `record_event`: `comment`, `post`, `share`
- `external/YPhotoSharing/YPhotoSharing/YClient/LLM_interactions/llm_service.py`
  - `extract_sentiment`: `NEGATIVE`, `POSITIVE`
  - `decide_follow`: `FOLLOW`
  - `decide_follow_request`: `ACCEPT`
- `external/YPhotoSharing/YPhotoSharing/YClient/LLM_interactions/remote_batch_service.py`
  - `generate`: `NULL`
  - `_probe_openai_batch`: `NULL`
  - `decide_follow`: `FOLLOW`
- `external/YPhotoSharing/YPhotoSharing/YClient/LLM_interactions/vllm_service.py`
  - `decide_follow`: `FOLLOW`
- `external/YPhotoSharing/YPhotoSharing/YClient/actions/follow.py`
  - `follow_user`: `FOLLOW`
- `external/YPhotoSharing/YPhotoSharing/YClient/actions/react.py`
  - `react_to_photo`: `IGNORE`, `LAUGH`, `LIKE`, `LOVE`
- `external/YPhotoSharing/YPhotoSharing/YClient/actions/review_follow_requests.py`
  - `review_follow_requests`: `ACCEPT`
- `external/YPhotoSharing/YPhotoSharing/YClient/agent_management/agent.py`
  - `_execute_action`: `comment`, `follow`, `react`, `share`, `unfollow`
  - `run_round`: `FOLLOW`
- `external/YPhotoSharing/YPhotoSharing/YClient/opinion_dynamics/llm_evaluation.py`
  - `llm_evaluation`: `AGREE`, `DISAGREE`, `neutral`
- `external/YPhotoSharing/YPhotoSharing/YClient/simulation/round_planner.py`
  - `build_action_weights`: `post`, `read`
- `external/YPhotoSharing/YPhotoSharing/YClient/stress_reward/update_system.py`
  - `_compute_delta`: `comment`, `share`
- `external/YPhotoSharing/YPhotoSharing/YServer/classes/db_middleware.py`
  - `review_follow_request`: `accept`
  - `get_home_feed`: `follow`
- `external/YPhotoSharing/YPhotoSharing/YServer/opinion_dynamics/opinion_handler.py`
  - `_get_neighbors_opinions_sql`: `follow`
- `external/YPhotoSharing/YPhotoSharing/YServer/services/moderation_service.py`
  - `_evaluate_content`: `comment`
  - `_take_action`: `comment`
- `external/y_agents_plugins/src/y_agents_plugins/db/experiment.py`
  - `_with_generated_id`: `INT`
  - `_coerce_for_column`: `INT`
  - `_missing_reference_value`: `INT`
  - `create_follow`: `unfollow`
  - `get_followed_user_ids`: `follow`, `unfollow`
  - `_topic_id_sql_type`: `INT`
  - `_with_required_user_defaults`: `INT`, `NUM`, `REAL`
- `external/y_agents_plugins/src/y_agents_plugins/llm/langchain.py`
  - `_normalize_api_key`: `EMPTY`, `NULL`
- `external/y_agents_plugins/src/y_agents_plugins/plugins/comic_relief.py`
  - `on_tick`: `comment`
- `external/y_agents_plugins/src/y_agents_plugins/plugins/master_of_puppets.py`
  - `_build_schedule_payload`: `post`
  - `_materialize_scheduled_action`: `post`
  - `_recent_campaign_target_stats`: `post`
- `external/y_agents_plugins/src/y_agents_plugins/plugins/moderator.py`
  - `_shadow_ban_enabled`: `yes`
  - `_ban_enabled`: `yes`
- `external/y_agents_plugins/src/y_agents_plugins/plugins/stress_attacker.py`
  - `_enabled`: `yes`
- `external/y_agents_plugins/src/y_agents_plugins/runtime/executor.py`
  - `execute`: `APPLY_MODERATION`, `APPLY_STRESS_EVENT`, `CREATE_COMMENT`, `CREATE_POST`, `FOLLOW_USER`, `REACT_POST`, `REPORT_POST`, `SHARE_POST`
  - `_apply_stress_reward_create_post`: `neutral`
  - `_apply_stress_reward_comment`: `neutral`
  - `_apply_stress_reward_reaction`: `laugh`, `like`, `love`
  - `_apply_synthetic_stress_event`: `comment`
  - `_persist_mop_activity`: `CREATE_COMMENT`, `CREATE_POST`, `SHARE_POST`
- `external/y_agents_plugins/src/y_agents_plugins/stress_reward/update_system.py`
  - `_compute_delta`: `comment`, `share`
- `external/reactive_agents/src/reactive_agents/adapter.py`
  - `generate_photo_comment`: `reply`
  - `decide_photo_reaction`: `COMMENT`, `LIKE`
- `external/reactive_agents/src/reactive_agents/continuity.py`
  - `run_continuity_pass`: `follow`
- `external/reactive_agents/src/reactive_agents/opinion_dynamics.py`
  - `_evaluate_opinion_llm`: `AGREE`, `DISAGREE`
  - `calculate_and_write_opinion_updates`: `AGREE`, `DISAGREE`, `neutral`
- `external/reactive_agents/src/reactive_agents/photo_events.py`
  - `_react`: `COMMENT`, `LIKE`
  - `_followers_of`: `follow`
- `external/reactive_agents/src/reactive_agents/secondary_dynamics.py`
  - `decide_thread_reaction`: `COMMENT`, `LIKE`
- `external/reactive_agents/src/reactive_agents/writer.py`
  - `_process_secondary_follow`: `follow`
  - `_process_thread_reaction`: `LIKE`
  - `_process_agent_reaction_event`: `COMMENT`, `LIKE`
  - `process_followed_post_event`: `follow`

