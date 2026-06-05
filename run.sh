#!/usr/bin/env bash
set -euo pipefail

codex -a never \
  --sandbox workspace-write \
  -c 'sandbox_workspace_write.network_access=true' \
  --add-dir /Users/jason/Dev/aastar \
  --add-dir /Users/jason/Dev/auraai \
  --add-dir /Users/jason/Dev/mycelium
