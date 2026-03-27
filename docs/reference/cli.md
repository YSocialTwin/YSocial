# CLI Reference

## Main entry points

YSocial exposes two operator-facing entry points.

| Entry point | Purpose |
|---|---|
| `python y_social.py` | direct browser-oriented application start |
| `python y_social_launcher.py` | desktop-first launcher and packaged-app entry |

## `y_social.py`

### Supported parameters

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `-x`, `--host` | string | `localhost` | bind address |
| `-y`, `--port` | integer/string | `8080` | HTTP port |
| `-d`, `--debug` | flag | off | enable debug mode |
| `-D`, `--db` | enum | `sqlite` | dashboard DB backend |
| `-l`, `--llm-backend` | string | unset | LLM backend selector or OpenAI-compatible endpoint |
| `-n`, `--no_notebook` | flag | notebook enabled | disable notebook integration |

### Examples

```bash
python y_social.py --host localhost --port 8080
python y_social.py --host 0.0.0.0 --port 8080 --db postgresql
python y_social.py --host localhost --port 8080 --llm-backend ollama
python y_social.py --host localhost --port 8080 --llm-backend http://127.0.0.1:8000
```

## `y_social_launcher.py`

### Supported parameters

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `-x`, `--host` | string | `localhost` | bind address |
| `-y`, `--port` | integer/string | `8080` | HTTP port |
| `-d`, `--debug` | flag | off | enable debug mode |
| `-D`, `--db` | enum | `sqlite` | dashboard DB backend |
| `-l`, `--llm-backend` | string | unset | LLM backend selector or OpenAI-compatible endpoint |
| `--browser` | flag | off | force browser mode |
| `--no-browser` | flag | off | suppress browser auto-open in browser mode |
| `--window-width` | integer | `1280` | desktop window width |
| `--window-height` | integer | `800` | desktop window height |

### Examples

```bash
python y_social_launcher.py
python y_social_launcher.py --browser
python y_social_launcher.py --llm-backend ollama
python y_social_launcher.py --window-width 1600 --window-height 900
```

## LLM backend values

The runtime accepts three operational classes:

1. `ollama`
2. `vllm`
3. custom OpenAI-compatible address or URL

Interpretation rules in the current code:

- `ollama` resolves to `http://127.0.0.1:11434/v1`
- `vllm` resolves to `http://127.0.0.1:8000/v1`
- `host:port` is normalized to `http://host:port/v1`
- full URLs are normalized to end in `/v1`

## Process-runner arguments

YSocial also uses internal subprocess entry points for simulation execution. These are operator-relevant mainly for debugging.

Files:

- `/Users/rossetti/PycharmProjects/YWeb/y_web/src/simulation/process_runner.py`
- `/Users/rossetti/PycharmProjects/YWeb/y_web/src/simulation/client_runner.py`
- `/Users/rossetti/PycharmProjects/YWeb/y_web/src/simulation/server_runner.py`

These subprocesses carry experiment and client identifiers, resume flags, and DB-type parameters. In ordinary usage they are launched from the admin UI, not manually.
