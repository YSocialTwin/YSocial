# Configuration

## Configuration layers

YSocial configuration is layered. That is the most important thing to understand before changing parameters.

1. Application launch parameters
2. Experiment configuration
3. Population configuration
4. Client configuration
5. Optional analysis and memory services

## 1. Application launch parameters

These are the flags passed to `y_social.py` or `y_social_launcher.py`.

### Core parameters

| Parameter | Layer | Purpose |
|---|---|---|
| `--host` | app | bind address |
| `--port` | app | HTTP port |
| `--debug` | app | development diagnostics |
| `--db` | app | dashboard/application DB backend |
| `--llm-backend` | app | default LLM endpoint selection |
| `--no_notebook` | app | disable embedded notebook support |
| `--browser` | launcher | force browser mode |
| `--window-width` / `--window-height` | launcher | desktop window geometry |

## 2. Experiment configuration

Experiment configuration is the top-level runtime contract for a simulation.

Typical persisted files include:

- `config_server.json`
- `server_config.json`

Common experiment parameters:

| Parameter | Meaning |
|---|---|
| `name` / `server_name` | human-readable experiment label |
| `platform_type` | selected platform template |
| `host` / `address` | server binding or runtime address |
| `port` | runtime port |
| `is_remote` | remote execution or remote server workflow |
| `topics` | simulation topics seed list |
| `sentiment_annotation` | sentiment processing toggle |
| `emotion_annotation` | emotion processing toggle |
| `perspective_api` | toxicity service key or activation parameter |
| `opinion_dynamics_enabled` | opinion dynamics master flag |
| `memory.enabled` | experiment-level memory activation |
| `experiment_configuration_confirmed` | admin workflow gate |

### Practical guidance

- Treat experiment settings as the master contract for all derived clients.
- Update experiment configuration before starting servers or creating clients when the UI requires confirmation.
- Keep `topics` current. They affect seed content, annotation, and downstream analysis.

## 3. Population configuration

Population files define who the simulated agents are and how they are distributed.

Common parameter groups:

| Group | Typical contents |
|---|---|
| demographics | age, gender, language, education, profession |
| behavioral traits | activity patterns, engagement rates, toxicity, political leaning |
| topical traits | interests, topics, content preferences |
| opinion state | seeded opinions and opinion distributions |
| network inputs | connection structure and generation parameters |
| activity profiles | schedule-like behavior blocks used by agents |

Guidance:

- Use populations to encode cohorts, not server behavior.
- Keep population distributions valid and normalized.
- If opinion dynamics is enabled, verify that seeded opinions are consistent with the chosen topic set.

## 4. Client configuration

Client configuration binds a population to a runnable simulation client.

Common client parameter groups:

| Group | Typical contents |
|---|---|
| population binding | population id or population file |
| model/backend | selected LLM service, model name, endpoint |
| vision model | image transcription or vision-capable model |
| recommendations | feed and follow recommender choices |
| network mode | synthetic or imported network settings |
| scheduling | execution mode, concurrency, resume behavior |
| memory | client-level memory enablement and retrieval settings |
| annotation support | client-side toggles that depend on experiment settings |

### HPC-oriented client settings

When the HPC path is used, the generated config may include sections such as:

- `llm`
- `llm_v`
- `database`
- `redis`
- `simulation`
- `logging`

The current codebase also writes backend interoperability fields for service-driven LLM use:

- `api_format`
- `batching_policy`

## 5. Analysis and memory configuration

Optional analysis-related configuration surfaces include:

### Notebook analysis

Notebook behavior is controlled at application launch and per experiment workflow.

### Opinion evolution

Opinion evolution depends on:

- enabled opinion dynamics
- topic availability
- consistent opinion writes into the experiment DB

### Interview and memory

The interview flow can use different memory retrieval modes and depends on:

- experiment memory enablement
- client-level memory enablement
- memory server availability when semantic retrieval is used

## Configuration storage guidance

In practice, there are three places where operators look for truth:

1. dashboard/application database
2. experiment directory JSON files
3. runtime experiment database

Use them for different purposes:

- JSON files are the best place to inspect the intended configuration.
- the dashboard DB is the best place to inspect admin state and assignment state.
- the experiment DB is the best place to inspect actual execution outputs.

## Safe operating rule

When debugging a configuration issue, verify in this order:

1. experiment JSON
2. client JSON
3. runtime DB and logs
4. UI state

That prevents confusing persisted intent with observed execution.
