# Running YSocial

## Main entry points

YSocial has three ways to start. Most people use the [desktop installer](launcher.md) and never touch these.

### `ysocial`

The command installed with the Python package (and used by the desktop installer and Docker). It takes the same options as `y_social.py`.

```bash
ysocial --host localhost --port 8080
```

### `y_social.py`

Use this for direct browser-oriented execution.

- file: `y_social.py`
- typical use: source-based execution, explicit host/port control (same as the `ysocial` command)

### `y_social_launcher.py`

Optional desktop window (pywebview) for people who run YSocial from a source checkout. The packaged desktop experience is the [installer/launcher](launcher.md).

- file: `y_social_launcher.py`
- typical use: native window by default, browser fallback optional

## Execution modalities

### Browser mode

Suitable for:

- server-style execution
- remote browser access
- debugging web behavior directly

Example:

```bash
python y_social.py --host localhost --port 8080 --llm-backend ollama
```

### Desktop mode

Suitable for:

- local single-user operation
- packaged application usage
- avoiding browser chrome

Example:

```bash
python y_social_launcher.py --llm-backend ollama
```

### Browser fallback from launcher

The launcher can still be used in browser mode:

```bash
python y_social_launcher.py --browser --llm-backend ollama
```

## Application launch parameters

### Parameters from `y_social.py`

| Parameter | Meaning | Default |
|---|---|---|
| `-x`, `--host` | host/interface to bind | `localhost` |
| `-y`, `--port` | HTTP port | `8080` |
| `-d`, `--debug` | enable Flask debug mode | disabled |
| `-D`, `--db` | database backend | `sqlite` |
| `-l`, `--llm-backend` | LLM backend selector or URL | none |
| `-n`, `--no_notebook` | disable notebook launch support | notebook enabled by default in source mode |

### Additional parameters from the launcher

| Parameter | Meaning | Default |
|---|---|---|
| `--browser` | force browser mode | desktop mode |
| `--no-browser` | do not auto-open browser in browser mode | auto-open |
| `--window-width` | desktop window width | `1280` |
| `--window-height` | desktop window height | `800` |

## LLM backend modes

`--llm-backend` accepts three classes of values:

1. `ollama`
2. `vllm`
3. custom OpenAI-compatible server address or URL

Behavior:

- if omitted, LLM-backed features are disabled at application startup
- if provided, the app attempts a basic reachability check before continuing
- the resolved backend URL is exposed to the runtime through environment variables

## Notebook mode

Notebook support is intended primarily for source-based execution.

Important distinction:

- source mode: notebook support can be enabled
- desktop installer: the Jupyter Notebook server is opt-in (off by default, see *More options*)

## Typical operating sequences

### Local analyst workflow

1. start YSocial in desktop or browser mode
2. create an experiment
3. update experiment configuration
4. create or select a population
5. create one or more clients
6. start server and clients
7. monitor execution and inspect logs
8. review outputs, export, or open analysis tools

### Server-style workflow

1. start in browser mode on a chosen host and port
2. connect with a browser
3. configure experiments and clients through the admin UI
4. run and monitor from the admin panel

## Default credentials and first access

The codebase and packaging docs assume an initial administrative login such as:

- email: `admin@y-not.social`
- password: `admin`

Treat that as bootstrap access only. Change operational credentials in real deployments.
