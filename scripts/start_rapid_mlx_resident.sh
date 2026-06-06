#!/usr/bin/env bash
# Start the PR-Daemon local model server from a normal macOS Terminal session.
# Use this when Codex/headless cannot access Metal.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${PR_DAEMON_ENV_FILE:-$ROOT/.env}"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

HOST="${RAPID_MLX_HOST:-127.0.0.1}"
PORT="${RAPID_MLX_PORT:-8000}"
LOAD_MODEL="${RAPID_MLX_LOAD_MODEL:-qwen3.6-35b-6bit}"
SERVED_MODEL_NAME="${RAPID_MLX_MODEL:-qwen3.6-a3b}"
PREFILL_STEP_SIZE="${RAPID_MLX_PREFILL_STEP_SIZE:-4096}"
GPU_MEMORY_UTILIZATION="${RAPID_MLX_GPU_MEMORY_UTILIZATION:-0.85}"
LOG_DIR="${PR_DAEMON_LOG_DIR:-$HOME/.local/state/pr-daemon}"
LOG_FILE="${LOG_DIR}/rapid-mlx-${PORT}.log"
MAX_LOG_BYTES="${PR_DAEMON_MAX_LOG_BYTES:-52428800}"

mkdir -p "$LOG_DIR"
if [ -f "$LOG_FILE" ]; then
  size="$(wc -c <"$LOG_FILE" 2>/dev/null || echo 0)"
  if [ "${size:-0}" -gt "$MAX_LOG_BYTES" ]; then
    mv "$LOG_FILE" "${LOG_FILE}.$(date +%Y%m%d%H%M%S)"
  fi
fi

echo "Starting resident Rapid-MLX server"
echo "  load model: $LOAD_MODEL"
echo "  API model:  $SERVED_MODEL_NAME"
echo "  base URL:   http://$HOST:$PORT/v1"
echo "  docs:       http://$HOST:$PORT/docs"
echo "  log file:   $LOG_FILE"
echo
echo "Keep this terminal open. Press Ctrl-C to stop."
echo

rapid-mlx serve "$LOAD_MODEL" \
  --host "$HOST" \
  --port "$PORT" \
  --served-model-name "$SERVED_MODEL_NAME" \
  --prefill-step-size "$PREFILL_STEP_SIZE" \
  --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION" \
  --enable-prefix-cache 2>&1 | tee -a "$LOG_FILE"
