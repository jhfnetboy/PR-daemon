#!/usr/bin/env bash
# Expose the Rapid-MLX Hugging Face cache snapshot under ~/.omlx/models.

set -euo pipefail

MODE="${1:---symlink}"
HF_CACHE_ROOT="${HF_CACHE_ROOT:-$HOME/.cache/huggingface/hub/models--mlx-community--Qwen3.6-35B-A3B-6bit}"
DEST="${OMLX_MODEL_PATH:-$HOME/.omlx/models/Qwen3.6-35B-A3B-MLX-6bit}"

if [ ! -d "$HF_CACHE_ROOT/snapshots" ]; then
  printf 'Missing HF cache snapshot directory: %s\n' "$HF_CACHE_ROOT/snapshots" >&2
  printf 'Try first: rapid-mlx pull qwen3.6-35b-6bit\n' >&2
  exit 1
fi

SNAPSHOT="$(find "$HF_CACHE_ROOT/snapshots" -mindepth 1 -maxdepth 1 -type d | head -1)"
if [ -z "$SNAPSHOT" ]; then
  printf 'No snapshot found under: %s\n' "$HF_CACHE_ROOT/snapshots" >&2
  exit 1
fi

if [ "$MODE" != "--symlink" ] && [ "$MODE" != "--copy" ]; then
  printf 'Usage: %s [--symlink|--copy]\n' "$0" >&2
  printf '  --symlink  Create ~/.omlx/models link to the HF snapshot. Default.\n' >&2
  printf '  --copy     Copy files into ~/.omlx/models, dereferencing HF symlinks.\n' >&2
  exit 2
fi

if [ -e "$DEST" ]; then
  printf 'Destination already exists and is not empty: %s\n' "$DEST" >&2
  printf 'Remove it manually if you want to rebuild it.\n' >&2
  exit 1
fi

mkdir -p "$(dirname "$DEST")"

printf 'Source snapshot: %s\n' "$SNAPSHOT"
printf 'Destination:     %s\n' "$DEST"

if [ "$MODE" = "--symlink" ]; then
  printf 'Creating symlink. This does not duplicate model weights.\n'
  ln -s "$SNAPSHOT" "$DEST"
else
  printf 'Copying with symlinks dereferenced. This may take a while.\n'
  mkdir -p "$DEST"
  rsync -aL --info=progress2 "$SNAPSHOT/" "$DEST/"
fi

printf '\nValidating local model path with rapid-mlx info...\n'
rapid-mlx info "$DEST"

cat <<EOF

Done.

Use this model through PR-Daemon with:

  export RAPID_MLX_LOAD_MODEL="$DEST"
  export RAPID_MLX_MODEL="qwen3.6-a3b"
  scripts/rapid_mlx_daemon.sh ensure

After the local path is verified and you no longer want the HF cache copy:

  rapid-mlx rm mlx-community/Qwen3.6-35B-A3B-6bit

Only run the removal command if you used --copy. If you used --symlink, removing
the HF cache will break the ~/.omlx/models link.

EOF
