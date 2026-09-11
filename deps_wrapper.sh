#!/usr/bin/env bash
#
# On-demand deps deployment for ORFS stage targets.
#
# Usage:
#   bazel run //:deps -- //pkg:target [make-args...]
#
# Builds the _deps pkg_tar companion target, extracts it to a local
# directory, and optionally runs a make target.
#
# Examples:
#   bazel run //:deps -- //test/asic:mock_place
#   bazel run //:deps -- //test/asic:mock_place do-3_4_place_resized

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <target> [make-args...]"
    echo ""
    echo "Deploy stage inputs for interactive debugging."
    echo ""
    echo "Examples:"
    echo "  bazel run //:deps -- //test/asic:mock_place"
    echo "  bazel run //:deps -- //test/asic:mock_place do-3_4_place_resized"
    exit 1
fi

TARGET="$1"; shift

# bazel run executes from bazel-bin/; nested bazelisk calls need the workspace.
cd "$BUILD_WORKSPACE_DIRECTORY"

# Derive the _deps companion target names. The tarball is an output of
# the pkg_tar companion, {name}_deps_tar, not of {name}_deps itself.
DEPS_TARGET="${TARGET}_deps"
TAR_TARGET="${DEPS_TARGET}_tar"

# Build the pkg_tar companion target.
if ! bazelisk build "$TAR_TARGET"; then
    echo "Error: failed to build $TAR_TARGET"
    echo "Does the target have a _deps companion (is it an ORFS stage target)?"
    exit 1
fi

# Locate the tarball. grep exits non-zero when nothing matches, which with
# 'set -e -o pipefail' would abort here, before the diagnostic below.
TARBALL="$(bazelisk cquery --output=files "$TAR_TARGET" 2>/dev/null \
    | grep '\.tar\.gz$' || true)"

if [ -z "$TARBALL" ]; then
    echo "Error: deps tarball not found for $TAR_TARGET"
    echo "Does the target have a _deps companion (is it an ORFS stage target)?"
    exit 1
fi

# Determine install directory from the target label.
# //test:tag_array_64x184_floorplan → tmp/test/tag_array_64x184_floorplan_deps
LABEL_PKG="$(echo "$TARGET" | sed 's|^//||; s|:.*||')"
LABEL_NAME="$(echo "$TARGET" | sed 's|.*:||')"
DST="${BUILD_WORKSPACE_DIRECTORY}/tmp/${LABEL_PKG}/${LABEL_NAME}_deps"

# Verify tmp/ is in .gitignore and .bazelignore.
missing=()
grep -qxF "tmp/" "$BUILD_WORKSPACE_DIRECTORY/.gitignore" 2>/dev/null || missing+=(".gitignore")
grep -qxF "tmp" "$BUILD_WORKSPACE_DIRECTORY/.bazelignore" 2>/dev/null || missing+=(".bazelignore")
if [ ${#missing[@]} -gt 0 ]; then
    echo "Error: 'tmp' entry missing from: ${missing[*]}"
    echo "Add 'tmp/' to .gitignore and 'tmp' to .bazelignore"
    exit 1
fi

# Extract (clean first if exists).
if [ -d "$DST" ]; then
    chmod -R u+w "$DST" 2>/dev/null || true
    rm -rf "$DST"
fi
mkdir -p "$DST"
tar -xzf "$TARBALL" -C "$DST"

# Flatten the runfiles directory: pkg_tar packages runfiles under
# <binary>.runfiles/, but the deploy layout expects them at the root.
RUNFILES_DIR="$(echo "$DST"/*.runfiles)"
if [ -d "$RUNFILES_DIR" ]; then
    mv "$RUNFILES_DIR"/* "$DST"/
    rmdir "$RUNFILES_DIR"
fi

# Find the make script (the stage-specific shell wrapper). It is NOT at
# the deploy root: it keeps its runfiles path, <repo-dir>/<package>/
# make_<target>_<variant>_<stage>, and the repo dir depends on which
# repository the design's package lives in:
#   _main/test/make_lb_32x128_cts_base_4_cts
#   +orfs_repositories+orfs/flow/designs/nangate45/gcd/make_gcd_cts_base_4_cts
# So search the deployed tree, keyed on the target name -- a bare
# 'make_*' also matches unrelated ORFS payload such as
# flow/platforms/asap7/openRoad/make_tracks.tcl.
# mapfile keeps the search out of a pipeline whose failure would, under
# 'set -euo pipefail', abort before any diagnostic could print.
MAKE_CANDIDATES=()
mapfile -t MAKE_CANDIDATES < <(
    find "$DST" -type f -name "make_${LABEL_NAME}_*" | sort
)

if [ "${#MAKE_CANDIDATES[@]}" -eq 0 ]; then
    echo "Error: make binary not found in $DST"
    echo "Searched the deployed tree for a regular file named" \
        "'make_${LABEL_NAME}_*'."
    echo "Does the target have a _deps companion (is it an ORFS stage target)?"
    exit 1
fi
if [ "${#MAKE_CANDIDATES[@]}" -gt 1 ]; then
    echo "Error: multiple make binaries found in $DST"
    printf '  %s\n' "${MAKE_CANDIDATES[@]}"
    echo "Refusing to guess which one drives the stage."
    exit 1
fi
MAKE_BIN="${MAKE_CANDIDATES[0]}"

# Find the config file (*.short.mk).
CONFIG="$(echo "$DST"/*.short.mk)"

# Create _main/config.mk from the short config.
if [ -f "$CONFIG" ]; then
    cp "$CONFIG" "$DST/_main/config.mk"
fi

# Create the make wrapper script. The wrapper cd's into _main, so the
# exec target is the make script's path relative to _main -- the same
# shape deploy.tpl gets from the script's Bazel short_path: <package>/...
# for a design in this repo, ../<repo>/<package>/... for an external one.
MAKE_REL="${MAKE_BIN#"$DST"/}"
case "$MAKE_REL" in
_main/*) MAKE_EXEC="./${MAKE_REL#_main/}" ;;
*) MAKE_EXEC="./../$MAKE_REL" ;;
esac
cat > "$DST/make" <<WRAPPER
#!/usr/bin/env bash
set -exuo pipefail
cd "\$(dirname "\$0")/_main"
find . -not -perm -u+w -exec chmod u+w {} + 2>/dev/null || true
export RUNFILES_DIR="\$(pwd)/.."
exec $MAKE_EXEC "\$@"
WRAPPER
chmod +x "$DST/make"

# Make all files writable so make targets can overwrite stage outputs.
find "$DST" -not -perm -u+w -exec chmod u+w {} + 2>/dev/null || true

# Bazel >= 8: _main/external/<repo> must resolve.
if [ ! -d "$DST/_main/external" ]; then
    mkdir -p "$DST/_main/external"
    for repo_dir in "$DST"/*/; do
        repo_name=$(basename "$repo_dir")
        [ "$repo_name" = "_main" ] && continue
        [ "$repo_name" = "_repo_mapping" ] && continue
        ln -sf "$repo_dir" "$DST/_main/external/$repo_name"
    done
fi

# Bazel modules use canonical names with '+' suffix (e.g. tcl_lang+).
# C++ runfiles libraries look up apparent names without '+' (e.g. tcl_lang).
# Create symlinks so both names resolve.
for repo_dir in "$DST"/*+/; do
    [ -d "$repo_dir" ] || continue
    apparent="${repo_dir%+/}"
    [ -e "$apparent" ] && continue
    ln -sf "$(basename "$repo_dir")" "$apparent"
done

echo "Deployed to: $DST"

# Run make if extra args provided.
if [ "$#" -gt 0 ]; then
    "$DST/make" "$@"
fi
