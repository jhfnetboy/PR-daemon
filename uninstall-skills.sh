#!/usr/bin/env bash
# uninstall-skills.sh — Remove globally installed PR Daemon skills from ~/.claude/skills/

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_SRC="$ROOT/.claude/skills"

if [[ -t 1 ]]; then RED='\033[0;31m'; NC='\033[0m'; else RED=''; NC=''; fi

removed=0
for skill_dir in "$SKILLS_SRC"/*/; do
  skill_name="$(basename "$skill_dir")"
  dest="$HOME/.claude/skills/$skill_name"
  if [[ -d "$dest" ]]; then
    # Only remove if it was installed from this repo (check origin frontmatter)
    if grep -q "origin: pr-daemon" "$dest/SKILL.md" 2>/dev/null; then
      rm -rf "$dest"
      echo -e "${RED}removed${NC}  $dest"
      ((removed++)) || true
    else
      echo "skipped  $dest  (origin does not match pr-daemon)"
    fi
  fi
done

if [[ $removed -eq 0 ]]; then
  echo "No PR Daemon skills found in ~/.claude/skills/ — nothing removed."
else
  echo ""
  echo "Removed $removed skill(s) from global install."
fi
