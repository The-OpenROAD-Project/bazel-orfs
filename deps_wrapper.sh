#!/usr/bin/env bash
#
# On-demand deps deployment for ORFS stage targets.
#
# Usage:
#   bazel run //:deps -- //pkg:target [make-args...]
#
# Builds only the deps output group (config + previous stage artifacts),
# skipping the expensive main make action via Bazel's action-level pruning.
# Then deploys the stage inputs to a local directory for interactive use.
#
# Examples:
#   bazel run //:deps -- //gallery/picorv32:picorv32_place
#   bazel run //:deps -- //gallery/picorv32:picorv32_place do-3_4_place_resized

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <target> [make-args...]"
    echo ""
    echo "Deploy stage inputs for interactive debugging."
    echo "Only builds the deps output group (cheap), never the main make action."
    echo ""
    echo "Examples:"
    echo "  bazel run //:deps -- //gallery/picorv32:picorv32_place"
    echo "  bazel run //:deps -- //gallery/picorv32:picorv32_place do-3_4_place_resized"
    exit 1
fi

TARGET="$1"; shift

# Build ONLY the deps output group.
# This triggers only cheap actions (config write, template expansion)
# and never the main make action (action-level pruning).
bazelisk build --output_groups=deps "$TARGET"

# Resolve paths from the target label.
BAZEL_BIN="$(bazelisk info bazel-bin 2>/dev/null)"
LABEL="${TARGET#//}"
PKG="${LABEL%%:*}"
NAME="${LABEL##*:}"

DEPLOY_SCRIPT="${BAZEL_BIN}/${PKG}/results/${NAME}_deps_deploy.sh"

if [ ! -f "$DEPLOY_SCRIPT" ]; then
    echo "Error: deploy script not found at $DEPLOY_SCRIPT"
    echo "Does the target provide OrfsDepInfo (is it an ORFS stage target)?"
    exit 1
fi

# Synthesize a runfiles-like tree from bazel-bin so that deploy.tpl
# can find files at their short_path locations.
RUNFILES_DIR=$(mktemp -d)
cleanup() { rm -rf "$RUNFILES_DIR"; }
trap cleanup EXIT

# Main repo files: short_path maps directly under bazel-bin
ln -sfn "$BAZEL_BIN" "$RUNFILES_DIR/_main"

# External repos: bazel-bin/external/<repo>/ -> runfiles/<repo>/
if [ -d "$BAZEL_BIN/external" ]; then
    for repo_dir in "$BAZEL_BIN/external"/*/; do
        [ -d "$repo_dir" ] || continue
        ln -sfn "$repo_dir" "$RUNFILES_DIR/$(basename "$repo_dir")"
    done
fi

ln -sfn "$RUNFILES_DIR" "${DEPLOY_SCRIPT}.runfiles"
chmod +x "$DEPLOY_SCRIPT"

export BUILD_WORKSPACE_DIRECTORY="${BUILD_WORKSPACE_DIRECTORY:-$(bazelisk info workspace 2>/dev/null)}"
exec "$DEPLOY_SCRIPT" "$@"
