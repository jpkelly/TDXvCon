#!/usr/bin/env bash
# Copy a freshly built transcoder.toe into the installed vcon package.
#
# Why this exists: when vcon is installed with pipx, the command runs from an
# isolated environment whose copy of the toe is a SNAPSHOT taken at install
# time. Rebuilding toe/transcoder.toe in the repo does not update it, so the
# installed command would keep using a stale toe. Run this after a rebuild.
#
# Usage:  ./scripts/sync-toe.sh [path/to/transcoder.toe]
#
# Alternative for development: skip copying entirely and point vcon at the
# repo copy with an environment variable:
#     export VCON_TOE=/path/to/vCon/src/vcon/data/transcoder.toe

set -euo pipefail

REPO_TOE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_TOE="${1:-$REPO_TOE_DIR/src/vcon/data/transcoder.toe}"

if [[ ! -f "$SRC_TOE" ]]; then
  echo "error: no toe at $SRC_TOE" >&2
  echo "Make it first: python scripts/release_toe.py (see PUBLISHING.md, step 3)." >&2
  exit 1
fi

echo "==> source toe: $SRC_TOE"
echo "    $(du -h "$SRC_TOE" | cut -f1), modified $(date -r "$SRC_TOE" '+%Y-%m-%d %H:%M')"

# Where is the installed package? Ask vcon itself.
PKG_DATA="$(python3 - <<'PY' 2>/dev/null || true
import importlib.util, pathlib
spec = importlib.util.find_spec("vcon")
if spec and spec.submodule_search_locations:
    print(pathlib.Path(list(spec.submodule_search_locations)[0]) / "data")
PY
)"

if [[ -z "$PKG_DATA" || ! -d "$PKG_DATA" ]]; then
  # Fall back to the well-known pipx location. The DISTRIBUTION is tdxvcon
  # (the PyPI name "vcon" is taken), but the import name and command are
  # still "vcon".
  for pv in "$HOME/.local/pipx/venvs/tdxvcon" "$HOME/.local/pipx/venvs/vcon"; do
    for py in "$pv"/lib/python*/site-packages/vcon/data; do
      [[ -d "$py" ]] && PKG_DATA="$py" && break 2
    done
  done
fi

if [[ ! -d "$PKG_DATA" ]]; then
  echo "error: could not locate the installed vcon package data dir." >&2
  echo "Find it with:  python3 -c 'import vcon, pathlib; print(pathlib.Path(vcon.__file__).parent / \"data\")'" >&2
  exit 1
fi

echo "==> target:     $PKG_DATA"
cp -f "$SRC_TOE" "$PKG_DATA/transcoder.toe"
echo "==> copied transcoder.toe"

# TD writes a versioned backup alongside; don't ship it.
for stale in "$PKG_DATA"/transcoder.[0-9]*.toe; do
  [[ -e "$stale" ]] && rm -f "$stale" && echo "==> removed $(basename "$stale")"
done

echo
echo "Done. Verify with:  vcon -doctor"
