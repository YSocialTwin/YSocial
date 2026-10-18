#!/bin/sh
set -e
mkdir -p "${YSOCIAL_HOME:-/data}"
# Extra arguments are forwarded to `ysocial` (e.g. --db postgresql, --llm-backend vllm)
exec ysocial --host "${YSOCIAL_HOST:-0.0.0.0}" --port "${YSOCIAL_PORT:-5000}" "$@"
