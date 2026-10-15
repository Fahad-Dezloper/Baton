#!/usr/bin/env bash
# Usage: ./setup_level.sh <arm> <level>   e.g. ./setup_level.sh baseline L1
# Copies the pristine fixture to runs/<arm>/<level> and snapshots it with git.
set -euo pipefail
ARM="${1:?arm}"
LEVEL="${2:?level}"
HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="$HERE/runs/$ARM/$LEVEL"
if [ -e "$DEST" ]; then
  echo "refusing to overwrite existing $DEST" >&2
  exit 1
fi
mkdir -p "$HERE/runs/$ARM"
cp -R "$HERE/fixture" "$DEST"
cd "$DEST"
git init -q
git add -A
git -c user.name=clash -c user.email=clash@local commit -q -m "pristine fixture"
echo "$DEST"
