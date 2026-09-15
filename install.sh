#!/usr/bin/env bash
# Research Map — install as a personal Claude Code skill (macOS / Linux / Git Bash)
#
#   bash install.sh
#
# Copies skills/research-map into ~/.claude/skills/ so Claude Code picks it up.
# If you would rather install it as a plugin, see README (plugin marketplace add).
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
src="$here/skills/research-map"
dst="$HOME/.claude/skills/research-map"

[ -d "$src" ] || { echo "skills/research-map not found next to this script" >&2; exit 1; }

py=""
for c in python3 python py; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys;assert sys.version_info>=(3,8)' 2>/dev/null; then
    py="$c"; break
  fi
done
if [ -z "$py" ]; then
  echo "! Python 3.8+ not found on PATH. Install it, then re-run." >&2
else
  echo "python      $py ($("$py" -c 'import sys;print("%d.%d"%sys.version_info[:2])'))"
fi

mkdir -p "$dst"
find "$dst" -mindepth 1 -delete 2>/dev/null || true
cp -R "$src/." "$dst/"
echo "installed   $dst"

if [ -n "$py" ]; then
  echo
  "$py" "$dst/scripts/extract.py" --doctor || true
fi
echo
echo "Next: open Claude Code and say  'build my research map'"
