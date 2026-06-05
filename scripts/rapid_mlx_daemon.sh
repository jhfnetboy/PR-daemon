#!/usr/bin/env bash
# Manage the local Rapid-MLX OpenAI-compatible server for PR-Daemon.

set -euo pipefail

CMD="${1:-status}"
HOST="${RAPID_MLX_HOST:-127.0.0.1}"
PORT="${RAPID_MLX_PORT:-8000}"
BASE_URL="${RAPID_MLX_BASE_URL:-http://${HOST}:${PORT}/v1}"
DOCS_URL="http://${HOST}:${PORT}/docs"
if [ -n "${RAPID_MLX_LOAD_MODEL:-}" ]; then
  LOAD_MODEL="$RAPID_MLX_LOAD_MODEL"
else
  LOAD_MODEL="qwen3.6-35b-6bit"
fi
SERVED_MODEL_NAME="${RAPID_MLX_MODEL:-qwen3.6-a3b}"
LOG_DIR="${PR_DAEMON_LOG_DIR:-$HOME/.local/state/pr-daemon}"
if ! mkdir -p "$LOG_DIR" 2>/dev/null; then
  LOG_DIR="${TMPDIR:-/tmp}/pr-daemon-rapid-mlx"
  mkdir -p "$LOG_DIR"
fi
LOG_FILE="${LOG_DIR}/rapid-mlx-${PORT}.log"

health() {
  curl -fs -m 5 "${BASE_URL}/models" >/dev/null
}

print_config() {
  printf 'host: %s\n' "$HOST"
  printf 'port: %s\n' "$PORT"
  printf 'base_url: %s\n' "$BASE_URL"
  printf 'docs_url: %s\n' "$DOCS_URL"
  printf 'load_model: %s\n' "$LOAD_MODEL"
  printf 'served_model_name: %s\n' "$SERVED_MODEL_NAME"
  printf 'log_file: %s\n' "$LOG_FILE"
}

start_server() {
  if health; then
    printf 'Rapid-MLX is already reachable at %s\n' "$BASE_URL"
    curl -fsS -m 5 "${BASE_URL}/models"
    printf '\n'
    return 0
  fi

  if [[ "$LOAD_MODEL" != */* ]]; then
    rapid-mlx info "$LOAD_MODEL" >/dev/null
  fi

  nohup rapid-mlx serve "$LOAD_MODEL" \
    --host "$HOST" \
    --port "$PORT" \
    --served-model-name "$SERVED_MODEL_NAME" \
    --prefill-step-size "${RAPID_MLX_PREFILL_STEP_SIZE:-4096}" \
    --gpu-memory-utilization "${RAPID_MLX_GPU_MEMORY_UTILIZATION:-0.85}" \
    --enable-prefix-cache \
    >"$LOG_FILE" 2>&1 &

  printf 'Started Rapid-MLX in background. Log: %s\n' "$LOG_FILE"
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12; do
    if health; then
      printf 'Rapid-MLX is ready at %s\n' "$BASE_URL"
      return 0
    fi
    sleep 5
  done

  if grep -q "No Metal device available" "$LOG_FILE" 2>/dev/null; then
    cat >&2 <<EOF
Rapid-MLX failed because this process cannot access the Metal device.
Start the model from a normal macOS Terminal/user session, then let PR-Daemon reuse http://127.0.0.1:${PORT}/v1.

Manual command:
  rapid-mlx serve "$LOAD_MODEL" --host "$HOST" --port "$PORT" --served-model-name "$SERVED_MODEL_NAME" --prefill-step-size "${RAPID_MLX_PREFILL_STEP_SIZE:-4096}" --gpu-memory-utilization "${RAPID_MLX_GPU_MEMORY_UTILIZATION:-0.85}" --enable-prefix-cache

Log: $LOG_FILE
EOF
  else
    printf 'Rapid-MLX did not become ready yet. Check log: %s\n' "$LOG_FILE" >&2
  fi
  return 1
}

case "$CMD" in
  status)
    print_config
    if health; then
      printf 'status: reachable\n'
      curl -fsS -m 5 "${BASE_URL}/models"
      printf '\n'
    else
      printf 'status: not reachable\n'
      exit 1
    fi
    ;;
  start|ensure)
    start_server
    ;;
  docs)
    printf '%s\n' "$DOCS_URL"
    curl -fsS -m 5 "$DOCS_URL" >/dev/null
    ;;
  models)
    curl -fsS -m 5 "${BASE_URL}/models"
    printf '\n'
    ;;
  smoke)
    health
    curl -fsS -m 120 "${BASE_URL}/chat/completions" \
      -H 'Content-Type: application/json' \
      -d '{"model":"'"$SERVED_MODEL_NAME"'","messages":[{"role":"user","content":"Return exactly: rapid-mlx-ready"}],"temperature":0,"max_tokens":16}'
    printf '\n'
    ;;
  config)
    print_config
    ;;
  *)
    cat <<EOF
Usage: $0 {status|start|ensure|docs|models|smoke|config}

Environment:
  RAPID_MLX_LOAD_MODEL          Model alias/path loaded by Rapid-MLX. Default: qwen3.6-35b-6bit
                                May be a Rapid-MLX alias/HF repo or a local ~/.omlx/models path.
  RAPID_MLX_MODEL               Model name exposed to the API. Default: qwen3.6-a3b
  RAPID_MLX_PORT                Server port. Default: 8000
  RAPID_MLX_BASE_URL            API base URL. Default: http://127.0.0.1:8000/v1
  RAPID_MLX_PREFILL_STEP_SIZE   Default: 4096
  RAPID_MLX_GPU_MEMORY_UTILIZATION Default: 0.85
EOF
    exit 2
    ;;
esac
