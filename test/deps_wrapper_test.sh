#!/usr/bin/env bash
#
# Regression test for deps_wrapper.sh (//:deps).
#
# The tarball is an output of {target}_deps_tar, not of {target}_deps, and
# 'set -euo pipefail' used to abort the script on the non-matching grep
# before the "deps tarball not found" diagnostic could print. Both are
# exercised here with a stub 'bazelisk' placed first on PATH, so no ORFS
# stage has to be built.

set -uo pipefail

WRAPPER="$(readlink -f "$1")"

ROOT="${TEST_TMPDIR}/ws"
STUB="${TEST_TMPDIR}/stub"
mkdir -p "$ROOT" "$STUB"
echo "tmp/" >"$ROOT/.gitignore"
echo "tmp" >"$ROOT/.bazelignore"

# A minimal deploy payload: what the wrapper expects to find after untar.
PAYLOAD="${TEST_TMPDIR}/payload"
mkdir -p "$PAYLOAD/_main"
echo '#!/bin/sh' >"$PAYLOAD/make_mock"
echo "export FOO=bar" >"$PAYLOAD/mock.short.mk"
mkdir -p "$ROOT/bazel-bin/pkg"
tar -czf "$ROOT/bazel-bin/pkg/mock_floorplan_deps_tar.tar.gz" -C "$PAYLOAD" .

# Stub bazelisk. MODE selects what 'cquery --output=files' reports:
#   ok      - the _deps_tar target owns the tarball (the real layout)
#   notar   - no target owns a tarball
#   nobuild - 'build' fails, as for a non-ORFS target
cat >"$STUB/bazelisk" <<'STUBEOF'
#!/usr/bin/env bash
case "$1" in
build)
    if [ "$MODE" = nobuild ]; then
        echo "no such target" >&2
        exit 1
    fi
    exit 0
    ;;
cquery)
    label="${!#}"
    case "$label" in
    *_deps_tar)
        if [ "$MODE" = ok ]; then
            echo "bazel-bin/pkg/mock_floorplan_deps_tar.tar.gz"
        fi
        ;;
    *_deps)
        # The _deps target's own files: never the tarball.
        echo "bazel-bin/pkg/2_floorplan.short.mk"
        echo "bazel-bin/pkg/mock_floorplan_deps.sh"
        ;;
    esac
    exit 0
    ;;
esac
exit 0
STUBEOF
chmod +x "$STUB/bazelisk"

export BUILD_WORKSPACE_DIRECTORY="$ROOT"
export PATH="$STUB:$PATH"

fail=0
check() {
    if ! eval "$2"; then
        echo "FAIL: $1"
        fail=1
    fi
}

# (a) The tarball is located and extracted via the _deps_tar companion.
export MODE=ok
out="$("$WRAPPER" //pkg:mock_floorplan 2>&1)"
rc=$?
echo "--- MODE=ok (rc=$rc) ---"
echo "$out"
check "wrapper should succeed when the _deps_tar target has a tarball" \
    '[ "$rc" -eq 0 ]'
check "wrapper should report the deploy directory" \
    'grep -q "Deployed to: .*/tmp/pkg/mock_floorplan_deps" <<<"$out"'
check "payload should be extracted" \
    '[ -f "$ROOT/tmp/pkg/mock_floorplan_deps/make_mock" ]'
check "make wrapper should be generated" \
    '[ -x "$ROOT/tmp/pkg/mock_floorplan_deps/make" ]'

# (b) No tarball anywhere: the diagnostic must print, and the exit non-zero.
export MODE=notar
out="$("$WRAPPER" //pkg:mock_floorplan 2>&1)"
rc=$?
echo "--- MODE=notar (rc=$rc) ---"
echo "$out"
check "wrapper should fail when no tarball is produced" '[ "$rc" -ne 0 ]'
check "wrapper should print the not-found diagnostic" \
    'grep -q "deps tarball not found" <<<"$out"'
check "wrapper should name the _deps_tar target" \
    'grep -q "_deps_tar" <<<"$out"'

# (c) Not an ORFS stage target: the build fails, with a helpful message.
export MODE=nobuild
out="$("$WRAPPER" //pkg:not_a_stage 2>&1)"
rc=$?
echo "--- MODE=nobuild (rc=$rc) ---"
echo "$out"
check "wrapper should fail when the companion does not build" \
    '[ "$rc" -ne 0 ]'
check "wrapper should explain the missing _deps companion" \
    'grep -q "is it an ORFS stage target" <<<"$out"'

exit "$fail"
