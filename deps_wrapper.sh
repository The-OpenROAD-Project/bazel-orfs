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
    | grep '\.tar$')"

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
tar -xf "$TARBALL" -C "$DST"

# pkg_tar with include_runfiles places files under <target>.runfiles/.
# Move the runfiles tree contents to the top level.
RUNFILES_DIR="$(find "$DST" -maxdepth 1 -name '*.runfiles' -type d | head -1)"
if [ -n "$RUNFILES_DIR" ]; then
    # Move contents up and remove the wrapper directory.
    mv "$RUNFILES_DIR"/* "$DST/" 2>/dev/null || true
    rmdir "$RUNFILES_DIR" 2>/dev/null || true
fi

# Clean up repo_mapping if present.
rm -f "$DST/_repo_mapping"

# Create _main/external/<repo> symlinks for both path styles.
if [ ! -d "$DST/_main/external" ]; then
    mkdir -p "$DST/_main/external"
    for repo_dir in "$DST"/*/; do
        repo_name=$(basename "$repo_dir")
        [ "$repo_name" = "_main" ] && continue
        ln -sf "../../$repo_name" "$DST/_main/external/$repo_name"
    done
fi

# Make all files writable so make targets can overwrite stage outputs.
find "$DST" -not -perm -u+w -exec chmod u+w {} + 2>/dev/null || true

# Read the deploy manifest to find make script and config paths.
MANIFEST="$(find "$DST/_main" -name '*_deploy_manifest.txt' | head -1)"
MAKE_PATH=""
CONFIG_PATH=""
if [ -n "$MANIFEST" ]; then
    while IFS= read -r line; do
        case "$line" in
            make=*)    MAKE_PATH="${line#make=}" ;;
            config=*)  CONFIG_PATH="${line#config=}" ;;
            rename=*)
                rename="${line#rename=}"
                src="${rename%%	*}"
                dst="${rename#*	}"
                mkdir -p "$DST/_main/$(dirname "$dst")"
                cp -f --dereference "$src" "$DST/_main/$dst"
                ;;
        esac
    done < "$MANIFEST"
fi

# Create config.mk symlink at the stable location.
if [ -n "$CONFIG_PATH" ] && [ -f "$DST/_main/$CONFIG_PATH" ]; then
    ln -sf "$CONFIG_PATH" "$DST/_main/config.mk"
fi

# Create top-level make wrapper.
if [ -n "$MAKE_PATH" ]; then
    cat > "$DST/make" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd "\$(dirname "\$0")/_main"
exec ./$MAKE_PATH "\$@"
EOF
    chmod +x "$DST/make"
fi

echo "Deployed to: $DST"

# Run make if extra args provided.
if [ "$#" -gt 0 ]; then
    "$DST/make" "$@"
fi
