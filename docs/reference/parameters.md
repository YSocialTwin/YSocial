# Configuration Parameters Reference

## Scope

This page summarizes the main parameter families that appear across the application runtime, experiment JSON, client JSON, and population artifacts.

It is a reference page, not a full behavioral spec.

## Application-level parameters

These are set at process startup.

| Parameter | Layer | Description |
|---|---|---|
| `host` | app | HTTP bind host |
| `port` | app | HTTP bind port |
| `db` | app | dashboard DB backend |
| `llm_backend` | app | default LLM endpoint selection |
| `debug` | app | development-oriented diagnostics |
| `notebook` | app | notebook integration enablement |
| `desktop_mode` | launcher | desktop-window runtime mode |

## Experiment-level parameters

Typical keys observed in generated experiment config files:

| Parameter | Description |
|---|---|
| `name` / `server_name` | experiment label |
| `platform_type` | selected simulation platform |
| `host` / `address` | server runtime address |
| `port` | server runtime port |
| `database_uri` | experiment DB connection target |
| `data_path` | base path for experiment data |
| `topics` | topic seed list |
| `is_remote` | remote execution flag |
| `sentiment_annotation` | sentiment annotation enablement |
| `emotion_annotation` | emotion annotation enablement |
| `perspective_api` | toxicity annotation credential/config |
| `opinion_dynamics_enabled` | opinion dynamics master flag |
| `memory.enabled` | experiment-level memory master flag |
| `experiment_configuration_confirmed` | admin workflow confirmation gate |

## Client-level parameters

Common client JSON areas:

| Section | Description |
|---|---|
| `agents` | agent backend, model, probabilities, and behavior controls |
| `servers` | service endpoints used by the client |
| `simulation` | runtime mode, opinion/memory toggles, and related execution state |
| `recommendations` | content/follow recommender settings |
| `network` | network generation or imported network settings |
| `logging` | client-side logging preferences |
| `llm` | text-generation backend block in HPC-like flows |
| `llm_v` | vision/image backend block in HPC-like flows |

### LLM service interoperability keys

The current code writes or uses keys such as:

- `api_format`
- `batching_policy`
- `base_url`
- `model`
- `api_key`

## Population-level parameters

Population definitions commonly carry:

| Area | Description |
|---|---|
| demographics | age, gender, language, education, profession |
| interests | topics/interests per agent or per distribution |
| opinions | seeded per-topic opinions |
| activity | activity profiles and engagement behavior |
| leaning/toxicity | behavioral and attitudinal distributions |
| network hints | generation settings for the social graph |

## Operational rule

When a configuration issue appears, inspect these in order:

1. launch parameters
2. experiment JSON
3. client JSON
4. population JSON
5. runtime DB and logs

That sequence maps best to how the application derives runtime behavior.
