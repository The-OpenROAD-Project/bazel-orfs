#!/bin/bash
# Pin a generated io-placement.tcl file to the source tree.
# Usage: bazelisk run //test:pin_lb_32x128
set -euo pipefail

src="$1"
dest="$BUILD_WORKSPACE_DIRECTORY/$2"

# Resolve runfiles path
if [[ ! -f "$src" && -n "${RUNFILES_DIR:-}" ]]; then
  src="$RUNFILES_DIR/_main/$src"
fi

mkdir -p "$(dirname "$dest")"
install -m 644 "$src" "$dest"
echo "Pinned: $2"
