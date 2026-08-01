#!/usr/bin/env bash
# Fallback PK challenger for the pk-review skill when Codex quota is exhausted.
# Sends the same PK-challenge prompt to DeepSeek (deepseek-v4-flash, non-thinking mode)
# instead of codex:codex-rescue, and prints only the model's answer.
set -euo pipefail

PROMPT_FILE="${1:?usage: deepseek_pk_challenge.sh <prompt-file>}"
ENV_FILE="${PR_DAEMON_ENV_FILE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/.env}"
TIMEOUT="${DEEPSEEK_TIMEOUT:-120}"

if [ ! -f "$PROMPT_FILE" ]; then
  echo "ERROR: prompt file not found: $PROMPT_FILE" >&2
  exit 1
fi

KEY="${DEEPSEEK_API_KEY:-}"
if [ -z "$KEY" ] && [ -f "$ENV_FILE" ]; then
  KEY="$(grep '^DEEPSEEK_API_KEY=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"')"
fi
if [ -z "$KEY" ]; then
  echo "ERROR: DEEPSEEK_API_KEY not found (env or $ENV_FILE)" >&2
  exit 1
fi

PROMPT_JSON="$(jq -Rs . < "$PROMPT_FILE")"

RESPONSE="$(curl -s --max-time "$TIMEOUT" https://api.deepseek.com/chat/completions \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"deepseek-v4-flash\",\"messages\":[{\"role\":\"user\",\"content\":${PROMPT_JSON}}],\"max_tokens\":6000,\"thinking\":{\"type\":\"disabled\"}}")"

CONTENT="$(echo "$RESPONSE" | jq -r '.choices[0].message.content // empty')"
if [ -z "$CONTENT" ]; then
  ERR="$(echo "$RESPONSE" | jq -r '.error.message // "unknown error"' 2>/dev/null || echo "unparseable response")"
  echo "ERROR: deepseek_pk_challenge failed: $ERR" >&2
  echo "$RESPONSE" >&2
  exit 1
fi

echo "$CONTENT"
