#!/usr/bin/env bash
# Research Map - install as a personal skill for every agent found on this machine
# (Claude Code and Codex CLI).
#
#   bash install.sh                 # install everywhere it can
#   bash install.sh --claude        # Claude Code only
#   bash install.sh --codex         # Codex only
#   bash install.sh --to <dir>      # a specific skills directory
#
# To install as a plugin instead, see README (plugin marketplace add).
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
src="$here/skills/research-map"
[ -d "$src" ] || { echo "skills/research-map not found next to this script" >&2; exit 1; }

want_claude=1; want_codex=1; explicit=""
while [ $# -gt 0 ]; do
  case "$1" in
    --claude) want_codex=0 ;;
    --codex)  want_claude=0 ;;
    --to)     shift; explicit="${1:-}" ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

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

targets=()
if [ -n "$explicit" ]; then
  targets+=("$explicit/research-map")
else
  [ "$want_claude" = 1 ] && [ -d "$HOME/.claude" ] && targets+=("$HOME/.claude/skills/research-map")
  codex_home="${CODEX_HOME:-$HOME/.codex}"
  [ "$want_codex" = 1 ] && [ -d "$codex_home" ] && targets+=("$codex_home/skills/research-map")
fi

if [ ${#targets[@]} -eq 0 ]; then
  echo "! No agent home found (~/.claude or ~/.codex)." >&2
  echo "  Install one, or pass --to <skills-directory>." >&2
  exit 1
fi

for dst in "${targets[@]}"; do
  mkdir -p "$dst"
  find "$dst" -mindepth 1 -delete 2>/dev/null || true
  cp -R "$src/." "$dst/"
  echo "installed   $dst"
done

if [ -n "$py" ]; then
  echo
  "$py" "${targets[0]}/scripts/extract.py" --doctor || true
fi
echo
echo "Next: ask your agent  'build my research map'"
