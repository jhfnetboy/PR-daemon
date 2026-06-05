#!/usr/bin/env bash
# Start the PR-Daemon local model server from a normal macOS Terminal session.
# Use this when Codex/headless cannot access Metal.

set -euo pipefail

HOST="${RAPID_MLX_HOST:-127.0.0.1}"
PORT="${RAPID_MLX_PORT:-8000}"
LOAD_MODEL="${RAPID_MLX_LOAD_MODEL:-qwen3.6-35b-6bit}"
SERVED_MODEL_NAME="${RAPID_MLX_MODEL:-qwen3.6-a3b}"
PREFILL_STEP_SIZE="${RAPID_MLX_PREFILL_STEP_SIZE:-4096}"
GPU_MEMORY_UTILIZATION="${RAPID_MLX_GPU_MEMORY_UTILIZATION:-0.85}"

echo "Starting resident Rapid-MLX server"
echo "  load model: $LOAD_MODEL"
echo "  API model:  $SERVED_MODEL_NAME"
echo "  base URL:   http://$HOST:$PORT/v1"
echo "  docs:       http://$HOST:$PORT/docs"
echo
echo "Keep this terminal open. Press Ctrl-C to stop."
echo

exec rapid-mlx serve "$LOAD_MODEL" \
  --host "$HOST" \
  --port "$PORT" \
  --served-model-name "$SERVED_MODEL_NAME" \
  --prefill-step-size "$PREFILL_STEP_SIZE" \
  --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION" \
  --enable-prefix-cache
