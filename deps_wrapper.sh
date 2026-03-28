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

# bazel run executes from bazel-bin/; nested bazelisk calls need the workspace.
cd "$BUILD_WORKSPACE_DIRECTORY"

# Build ONLY the deps output group.
# This triggers only cheap actions (config write, template expansion)
# and never the main make action (action-level pruning).
bazelisk build --output_groups=deps "$TARGET"

# Locate the deploy script via cquery (handles PDK subdirectories).
# cquery returns a workspace-relative path like bazel-out/.../bin/.../deploy.sh
DEPLOY_SCRIPT="$(bazelisk cquery --output=files --output_groups=deps "$TARGET" 2>/dev/null \
    | grep '_deps_deploy\.sh$')"

if [ -z "$DEPLOY_SCRIPT" ]; then
    echo "Error: deploy script not found for $TARGET"
    echo "Does the target provide OrfsDepInfo (is it an ORFS stage target)?"
    exit 1
fi

# Make absolute (cquery paths are relative to workspace root).
DEPLOY_SCRIPT="$(readlink -f "$DEPLOY_SCRIPT")"

if [ ! -f "$DEPLOY_SCRIPT" ]; then
    echo "Error: deploy script not found at $DEPLOY_SCRIPT"
    exit 1
fi

# Synthesize a runfiles-like tree from bazel-bin so that deploy.tpl
# can find files at their short_path locations.
BAZEL_BIN="$(bazelisk info bazel-bin 2>/dev/null)"
RUNFILES_DIR=$(mktemp -d)
cleanup() { rm -rf "$RUNFILES_DIR"; }
trap cleanup EXIT

# Create _main as a real directory with per-entry symlinks into bazel-bin.
# (A direct symlink _main -> bazel-bin would make deploy.tpl's genfiles cp
# see source and dest as the same file.)
EXEC_ROOT="$(bazelisk info execution_root 2>/dev/null)"
mkdir "$RUNFILES_DIR/_main"
for entry in "$BAZEL_BIN"/*/; do
    [ -d "$entry" ] || continue
    name="$(basename "$entry")"
    # Skip external/ — we build a merged version below.
    [ "$name" = "external" ] && continue
    ln -sfn "$entry" "$RUNFILES_DIR/_main/$name"
done
# Also link top-level files (make scripts, etc.)
for entry in "$BAZEL_BIN"/*; do
    [ -f "$entry" ] || [ -L "$entry" ] || continue
    ln -sfn "$entry" "$RUNFILES_DIR/_main/$(basename "$entry")"
done

# Build a merged _main/external/ from two sources:
# - bazel-bin/external/: built outputs (pip packages, etc.)
# - execroot/external/: source-tree repos (e.g. +orfs_repositories+docker_orfs)
mkdir "$RUNFILES_DIR/_main/external"
for ext_dir in "$EXEC_ROOT/external" "$BAZEL_BIN/external"; do
    [ -d "$ext_dir" ] || continue
    for repo_dir in "$ext_dir"/*/; do
        [ -d "$repo_dir" ] || continue
        repo_name="$(basename "$repo_dir")"
        # bazel-bin wins (listed second, overwrites execroot entries)
        ln -sfn "$repo_dir" "$RUNFILES_DIR/_main/external/$repo_name"
    done
done

# Top-level external repo entries for deploy.tpl's runfiles copy.
for repo_dir in "$RUNFILES_DIR/_main/external"/*/; do
    [ -d "$repo_dir" ] || continue
    repo_name="$(basename "$repo_dir")"
    [ -e "$RUNFILES_DIR/$repo_name" ] && continue
    ln -sfn "$repo_dir" "$RUNFILES_DIR/$repo_name"
done

ln -sfn "$RUNFILES_DIR" "${DEPLOY_SCRIPT}.runfiles"
chmod +x "$DEPLOY_SCRIPT"

export BUILD_WORKSPACE_DIRECTORY="${BUILD_WORKSPACE_DIRECTORY:-$(bazelisk info workspace 2>/dev/null)}"

# deploy.tpl copies genfiles via short_path (e.g. test/results/.../file).
# These paths resolve under bazel-bin.
cd "$BAZEL_BIN"
exec "$DEPLOY_SCRIPT" "$@"
