#!/usr/bin/env bash
# install-skills.sh — Install PR Daemon Claude Code skills.
#
# Usage:
#   ./install-skills.sh              # project install (already in .claude/skills/ — no-op reminder)
#   ./install-skills.sh --global     # install to ~/.claude/skills/ with absolute paths patched in
#   ./install-skills.sh --global --dry-run   # preview without writing

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCOPE="${1:-}"
DRY_RUN=0
for arg in "$@"; do [[ "$arg" == "--dry-run" ]] && DRY_RUN=1; done

if [[ -t 1 ]]; then
  GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
else
  GREEN=''; YELLOW=''; NC=''
fi

info() { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}!${NC} $*"; }

SKILLS_SRC="$ROOT/.claude/skills"

if [[ "$SCOPE" == "--global" ]]; then
  DEST="$HOME/.claude/skills"
  [[ $DRY_RUN -eq 1 ]] && warn "dry-run: would install to $DEST"

  for skill_dir in "$SKILLS_SRC"/*/; do
    skill_name="$(basename "$skill_dir")"
    dest_dir="$DEST/$skill_name"

    if [[ $DRY_RUN -eq 1 ]]; then
      warn "dry-run: $skill_name → $dest_dir"
      sed "s|PR_DAEMON_ROOT|$ROOT|g" "$skill_dir/SKILL.md" | head -6
      echo "..."
      continue
    fi

    mkdir -p "$dest_dir"
    # Patch PR_DAEMON_ROOT placeholder with absolute repo path
    sed "s|PR_DAEMON_ROOT|$ROOT|g" "$skill_dir/SKILL.md" > "$dest_dir/SKILL.md"
    info "installed: $skill_name  →  $dest_dir"
  done

  if [[ $DRY_RUN -eq 0 ]]; then
    echo ""
    echo "Global install complete. Skills are now available in all Claude Code sessions."
    echo ""
    echo "Required setup in your shell or .env:"
    echo "  export PR_DAEMON_MAIN_USER=your-github-login"
    echo "  export PR_DAEMON_REVIEW_USER=your-review-account"
    echo "  export PR_DAEMON_REVIEW_TOKEN=ghp_..."
    echo "  export DEEPSEEK_API_KEY=sk-..."
    echo ""
    echo "Launch with:  cd $ROOT && ./run-dpsk-claude.sh"
    echo "Then say:     \"Use \$pr-daemon-loop to start reviewing PRs\""
  fi

else
  # Project-level install: skills are already in .claude/skills/ — just verify
  echo "Project-level skills are already at: $SKILLS_SRC"
  echo ""
  for skill_dir in "$SKILLS_SRC"/*/; do
    skill_name="$(basename "$skill_dir")"
    first_line="$(grep '^name:' "$skill_dir/SKILL.md" | head -1)"
    info "$skill_name  ($first_line)"
  done
  echo ""
  echo "Claude Code auto-discovers these when working in this directory."
  echo "For global install (available in all projects): ./install-skills.sh --global"
fi
