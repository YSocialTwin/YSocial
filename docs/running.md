# Running YSocial

## Main entry points

YSocial has two primary application entry points.

### `y_social.py`

Use this for direct browser-oriented execution.

- file: `/Users/rossetti/PycharmProjects/YWeb/y_social.py`
- typical use: source-based execution, explicit host/port control

### `y_social_launcher.py`

Use this for the desktop-first workflow and PyInstaller entry.

- file: `/Users/rossetti/PycharmProjects/YWeb/y_social_launcher.py`
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
- PyInstaller mode: notebook support is intentionally disabled by design

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
