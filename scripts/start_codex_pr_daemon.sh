#!/usr/bin/env bash
# Start Codex for PR-Daemon with all review roots added as writable workspaces.
#
# Even with writable roots, PR-Daemon policy forbids editing business repo code.
# Write access is for git fetch/checkout and temporary review artifacts only.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

exec codex \
  --cd "$ROOT" \
  --sandbox workspace-write \
  --add-dir /Users/jason/Dev/aastar \
  --add-dir /Users/jason/Dev/auraai \
  --add-dir /Users/jason/Dev/mycelium
