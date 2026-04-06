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
#   bazel run //:deps -- //gallery/picorv32:picorv32_place
#   bazel run //:deps -- //gallery/picorv32:picorv32_place do-3_4_place_resized

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <target> [make-args...]"
    echo ""
    echo "Deploy stage inputs for interactive debugging."
    echo ""
    echo "Examples:"
    echo "  bazel run //:deps -- //gallery/picorv32:picorv32_place"
    echo "  bazel run //:deps -- //gallery/picorv32:picorv32_place do-3_4_place_resized"
    exit 1
fi

TARGET="$1"; shift

# bazel run executes from bazel-bin/; nested bazelisk calls need the workspace.
cd "$BUILD_WORKSPACE_DIRECTORY"

# Derive the _deps companion target name.
DEPS_TARGET="${TARGET}_deps"

# Build the pkg_tar companion target.
bazelisk build "$DEPS_TARGET"

# Locate the tarball.
TARBALL="$(bazelisk cquery --output=files "$DEPS_TARGET" 2>/dev/null \
    | grep '\.tar\.gz$')"

if [ -z "$TARBALL" ]; then
    echo "Error: deps tarball not found for $DEPS_TARGET"
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

# Find the make binary (the stage-specific shell wrapper).
MAKE_BIN="$(echo "$DST"/make_*)"
if [ ! -f "$MAKE_BIN" ]; then
    echo "Error: make binary not found in $DST"
    exit 1
fi

# Find the config file (*.short.mk).
CONFIG="$(echo "$DST"/*.short.mk)"

# Create _main/config.mk from the short config.
if [ -f "$CONFIG" ]; then
    cp "$CONFIG" "$DST/_main/config.mk"
fi

# Create the make wrapper script.
MAKE_REL="$(basename "$MAKE_BIN")"
cat > "$DST/make" <<WRAPPER
#!/usr/bin/env bash
set -exuo pipefail
cd "\$(dirname "\$0")/_main"
find . -not -perm -u+w -exec chmod u+w {} + 2>/dev/null || true
export RUNFILES_DIR="\$(pwd)/.."
exec ../$MAKE_REL "\$@"
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
