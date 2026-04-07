#!/usr/bin/env bash
# Bazel-native deps deployment test.
#
# Extracts a _deps tarball and runs assertions, replacing the nested
# bazelisk invocations in deps_integration_test.sh with a pure-shell
# test that Bazel can cache and parallelize.
#
# Usage (called by Bazel sh_test):
#   deps_deploy_test.sh <tarball> <check> [check-args...]
#
# Checks:
#   dir_exists        — deploy dir created with make wrapper
#   config_contains   — config.mk contains a string (arg: pattern)
#   print_flow_home   — make print-FLOW_HOME returns non-empty
#   make_passthrough  — make print-DESIGN_NAME succeeds
#   run_substep       — make do-2_1_floorplan succeeds

set -euo pipefail

TARBALL="$1"; shift
CHECK="$1"; shift

# --- Deploy (mirrors deps_wrapper.sh logic) ---

DST="$(mktemp -d)"
trap 'rm -rf "$DST"' EXIT

tar -xzf "$TARBALL" -C "$DST"

# Flatten runfiles directory
RUNFILES_DIR="$(echo "$DST"/*.runfiles)"
if [ -d "$RUNFILES_DIR" ]; then
    mv "$RUNFILES_DIR"/* "$DST"/
    rmdir "$RUNFILES_DIR"
fi

# Find the make binary
MAKE_BIN="$(echo "$DST"/make_*)"
if [ ! -f "$MAKE_BIN" ]; then
    echo "FAIL: make binary not found in $DST"
    exit 1
fi

# Find the config file (*.short.mk)
CONFIG="$(echo "$DST"/*.short.mk)"

# Create _main/config.mk from the short config
if [ -f "$CONFIG" ]; then
    cp "$CONFIG" "$DST/_main/config.mk"
fi

# Create the make wrapper script
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

# Make all files writable
find "$DST" -not -perm -u+w -exec chmod u+w {} + 2>/dev/null || true

# Bazel >= 8: _main/external/<repo> must resolve
if [ ! -d "$DST/_main/external" ]; then
    mkdir -p "$DST/_main/external"
    for repo_dir in "$DST"/*/; do
        repo_name=$(basename "$repo_dir")
        [ "$repo_name" = "_main" ] && continue
        [ "$repo_name" = "_repo_mapping" ] && continue
        ln -sf "$repo_dir" "$DST/_main/external/$repo_name"
    done
fi

# Module canonical name symlinks
for repo_dir in "$DST"/*+/; do
    [ -d "$repo_dir" ] || continue
    apparent="${repo_dir%+/}"
    [ -e "$apparent" ] && continue
    ln -sf "$(basename "$repo_dir")" "$apparent"
done

# --- Assertions ---

case "$CHECK" in
    dir_exists)
        [ -d "$DST" ] || { echo "FAIL: deploy dir not found"; exit 1; }
        [ -x "$DST/make" ] || { echo "FAIL: make not executable"; exit 1; }
        [ -f "$DST/_main/config.mk" ] || { echo "FAIL: config.mk missing"; exit 1; }
        echo "PASS: dir_exists"
        ;;
    config_contains)
        PATTERN="$1"
        grep -q "$PATTERN" "$DST/_main/config.mk" || {
            echo "FAIL: config.mk does not contain '$PATTERN'"
            exit 1
        }
        echo "PASS: config_contains $PATTERN"
        ;;
    print_flow_home)
        FLOW_HOME=$("$DST/make" print-FLOW_HOME 2>&1 | tail -1)
        [ -n "$FLOW_HOME" ] || { echo "FAIL: print-FLOW_HOME returned empty"; exit 1; }
        echo "PASS: print-FLOW_HOME returned: $FLOW_HOME"
        ;;
    make_passthrough)
        "$DST/make" print-DESIGN_NAME || { echo "FAIL: make passthrough failed"; exit 1; }
        echo "PASS: make_passthrough"
        ;;
    run_substep)
        "$DST/make" do-2_1_floorplan || { echo "FAIL: make do-2_1_floorplan failed"; exit 1; }
        echo "PASS: run_substep"
        ;;
    *)
        echo "Unknown check: $CHECK"
        exit 1
        ;;
esac
