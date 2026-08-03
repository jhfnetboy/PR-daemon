#!/usr/bin/env bash

if [ -z "${PR_DAEMON_ROOT:-}" ]; then
  PR_DAEMON_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi

ENV_FILE="${PR_DAEMON_ENV_FILE:-$PR_DAEMON_ROOT/.env}"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

proxy_pick() {
  local target="$1"
  shift
  local current="${!target:-}"
  if [ -n "$current" ]; then
    export "$target=$current"
    return
  fi
  local alias_name
  for alias_name in "$@"; do
    local value="${!alias_name:-}"
    if [ -n "$value" ]; then
      export "$target=$value"
      return
    fi
  done
}

# An explicitly-empty PR_DAEMON_*_PROXY in .env means "force NO proxy" — clear any proxy the
# daemon inherited from the launching shell (e.g. a stale HTTPS_PROXY/ALL_PROXY=127.0.0.1:7890),
# which proxy_pick below would otherwise preserve because it prefers an already-set target value.
# Only clear when .env actually DEFINES the var as empty (not merely absent).
if [ "${PR_DAEMON_HTTPS_PROXY+def}" = "def" ] && [ -z "${PR_DAEMON_HTTPS_PROXY}" ]; then unset HTTPS_PROXY https_proxy; fi
if [ "${PR_DAEMON_HTTP_PROXY+def}" = "def" ]  && [ -z "${PR_DAEMON_HTTP_PROXY}" ];  then unset HTTP_PROXY http_proxy; fi
if [ "${PR_DAEMON_ALL_PROXY+def}" = "def" ]   && [ -z "${PR_DAEMON_ALL_PROXY}" ];   then unset ALL_PROXY all_proxy; fi

proxy_pick HTTPS_PROXY PR_DAEMON_HTTPS_PROXY https_proxy HTTP_PROXY http_proxy ALL_PROXY all_proxy
proxy_pick HTTP_PROXY PR_DAEMON_HTTP_PROXY http_proxy HTTPS_PROXY https_proxy ALL_PROXY all_proxy
proxy_pick ALL_PROXY PR_DAEMON_ALL_PROXY all_proxy HTTPS_PROXY https_proxy HTTP_PROXY http_proxy
proxy_pick NO_PROXY PR_DAEMON_NO_PROXY no_proxy

if [ -n "${HTTPS_PROXY:-}" ] && [ -z "${https_proxy:-}" ]; then
  export https_proxy="$HTTPS_PROXY"
fi
if [ -n "${HTTP_PROXY:-}" ] && [ -z "${http_proxy:-}" ]; then
  export http_proxy="$HTTP_PROXY"
fi
if [ -n "${ALL_PROXY:-}" ] && [ -z "${all_proxy:-}" ]; then
  export all_proxy="$ALL_PROXY"
fi
if [ -n "${NO_PROXY:-}" ] && [ -z "${no_proxy:-}" ]; then
  export no_proxy="$NO_PROXY"
fi
