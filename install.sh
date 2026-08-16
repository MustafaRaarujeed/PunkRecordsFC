#!/usr/bin/env bash
# Install the fpl-manager skill and fpl-scout agent into an agent config dir.
#
# Usage:
#   ./install.sh                    # -> $AGENT_CONFIG_DIR, $CODEX_HOME, or ~/.codex
#   ./install.sh ~/.other-agent     # -> an explicit agent config directory
#
# Only SKILL.md, its references, and the agent are copied. scripts/, state/ and
# data/ stay here and are referenced by absolute path: state/squad.json is the
# single source of truth for the squad, and a second copy of it would drift.
#
# The copies have {{PROJECT_ROOT}} substituted for this directory, so they work
# from any working directory.

set -euo pipefail

DEFAULT_TARGET_DIR="${AGENT_CONFIG_DIR:-${CODEX_HOME:-$HOME/.codex}}"
TARGET_DIR="${1:-$DEFAULT_TARGET_DIR}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SKILL_NAME="fpl-manager"
AGENT_NAME="fpl-scout"

SKILL_SRC="$PROJECT_ROOT/skills/$SKILL_NAME"
AGENT_SRC="$PROJECT_ROOT/agents/$AGENT_NAME.md"

[ -d "$SKILL_SRC" ] || { echo "missing skill source: $SKILL_SRC" >&2; exit 1; }
[ -f "$AGENT_SRC" ] || { echo "missing agent source: $AGENT_SRC" >&2; exit 1; }

SKILL_DEST="$TARGET_DIR/skills/$SKILL_NAME"
AGENT_DEST="$TARGET_DIR/agents/$AGENT_NAME.md"

mkdir -p "$TARGET_DIR/skills" "$TARGET_DIR/agents"

# Remove first: `cp -R src dest` nests into dest when dest already exists,
# which on a reinstall would give skills/fpl-manager/fpl-manager.
rm -rf "$SKILL_DEST"
cp -R "$SKILL_SRC" "$SKILL_DEST"
cp "$AGENT_SRC" "$AGENT_DEST"

# Templating is why these are copies rather than symlinks: the installed files
# need an absolute path back to the scripts and state they drive.
find "$SKILL_DEST" -name '*.md' -type f -exec \
  sed -i '' "s|{{PROJECT_ROOT}}|$PROJECT_ROOT|g" {} +
sed -i '' "s|{{PROJECT_ROOT}}|$PROJECT_ROOT|g" "$AGENT_DEST"

if grep -rq '{{PROJECT_ROOT}}' "$SKILL_DEST" "$AGENT_DEST"; then
  echo "warning: unsubstituted {{PROJECT_ROOT}} remains" >&2
fi

echo "installed:"
echo "  skill  $SKILL_DEST"
echo "  agent  $AGENT_DEST"
echo "  root   $PROJECT_ROOT"
echo
echo "These are COPIES. After editing anything under skills/ or agents/,"
echo "rerun ./install.sh or your change will not take effect."
