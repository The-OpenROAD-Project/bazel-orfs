#!/usr/bin/env bash
#
# Regression test for deps_wrapper.sh (//:deps).
#
# Two bugs are pinned here:
#
#  1. The tarball is an output of {target}_deps_tar, not of {target}_deps,
#     and 'set -euo pipefail' used to abort the script on the non-matching
#     grep before the "deps tarball not found" diagnostic could print.
#
#  2. The stage make script is not at the deploy root. It keeps its
#     runfiles path, <repo-dir>/<package>/make_<target>_<variant>_<stage>,
#     and the repo dir depends on which repository the design's package
#     lives in. A root 'make_*' glob matched neither real layout, and the
#     generated ./make wrapper hardcoded 'exec ../<basename>'.
#
# The payloads below mirror a real tarball, as produced by
# //test:lb_32x128_cts_deps_tar:
#
#   4_cts.short.mk
#   lb_32x128_cts_deps_run.sh
#   lb_32x128_cts_deps_run.sh.runfiles/_main/test/make_lb_32x128_cts_base_4_cts
#   lb_32x128_cts_deps_run.sh.runfiles/+orfs_repositories+orfs/...
#
# including ORFS's flow/platforms/asap7/openRoad/make_tracks.tcl, which a
# bare 'make_*' search happily mistakes for the stage make script.
#
# Driven with a stub 'bazelisk' first on PATH, so no ORFS stage has to be
# built.

set -uo pipefail

WRAPPER="$(readlink -f "$1")"

ROOT="${TEST_TMPDIR}/ws"
STUB="${TEST_TMPDIR}/stub"
mkdir -p "$ROOT" "$STUB"
echo "tmp/" >"$ROOT/.gitignore"
echo "tmp" >"$ROOT/.bazelignore"
mkdir -p "$ROOT/bazel-bin/pkg"

# make_payload <tarball> <runner> <script-runfiles-path>...
#
# Builds a tarball shaped like the real one: a short config and the
# *_deps_run.sh launcher at the root, everything else under
# <launcher>.runfiles/<repo-dir>/..., which the wrapper flattens.
make_payload() {
    local tarball="$1" runner="$2"
    shift 2
    local payload="${TEST_TMPDIR}/payload.$$.$RANDOM"
    local runfiles="$payload/$runner.runfiles"
    mkdir -p "$payload" "$runfiles/_main"
    echo "export DESIGN_NAME=mock" >"$payload/4_cts.short.mk"
    echo '#!/bin/sh' >"$payload/$runner"
    # ORFS payload that a bare 'make_*' search would mistake for the
    # stage make script.
    local tracks="$runfiles/+orfs_repositories+orfs/flow/platforms/asap7/openRoad"
    mkdir -p "$tracks"
    echo "# tracks" >"$tracks/make_tracks.tcl"
    local script
    for script in "$@"; do
        mkdir -p "$runfiles/$(dirname "$script")"
        printf '#!/bin/sh\necho "ran $0"\n' >"$runfiles/$script"
        chmod +x "$runfiles/$script"
    done
    tar -czf "$tarball" -C "$payload" .
    rm -rf "$payload"
}

# (i) A design in this repository: _main/<package>/make_<name>.
make_payload "$ROOT/bazel-bin/pkg/main_tar.tar.gz" \
    lb_32x128_cts_deps_run.sh \
    _main/test/make_lb_32x128_cts_base_4_cts

# (ii) A design in @orfs: +orfs_repositories+orfs/<package>/make_<name>.
make_payload "$ROOT/bazel-bin/pkg/orfs_tar.tar.gz" \
    gcd_cts_deps_run.sh \
    +orfs_repositories+orfs/flow/designs/nangate45/gcd/make_gcd_cts_base_4_cts

# (iii) Two candidates for the same target: the wrapper must refuse
# rather than pick one.
make_payload "$ROOT/bazel-bin/pkg/ambiguous_tar.tar.gz" \
    dup_cts_deps_run.sh \
    _main/test/make_dup_cts_base_4_cts \
    +orfs_repositories+orfs/flow/designs/dup/make_dup_cts_base_4_cts

# Stub bazelisk. MODE selects what 'cquery --output=files' reports:
#   main/orfs/ambiguous - the _deps_tar target owns that tarball
#   notar               - no target owns a tarball
#   nobuild             - 'build' fails, as for a non-ORFS target
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
        case "$MODE" in
        notar) ;;
        *) echo "bazel-bin/pkg/${MODE}_tar.tar.gz" ;;
        esac
        ;;
    *_deps)
        # The _deps target's own files: never the tarball.
        echo "bazel-bin/pkg/4_cts.short.mk"
        echo "bazel-bin/pkg/mock_cts_deps.sh"
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

# (a) A design in this repository. The make script sits at
# _main/test/..., so the wrapper -- which cd's into _main -- must exec
# ./test/..., the shape deploy.tpl derives from the script's short_path.
export MODE=main
out="$("$WRAPPER" //test:lb_32x128_cts 2>&1)"
rc=$?
echo "--- MODE=main (rc=$rc) ---"
echo "$out"
DST="$ROOT/tmp/test/lb_32x128_cts_deps"
check "wrapper should succeed when the _deps_tar target has a tarball" \
    '[ "$rc" -eq 0 ]'
check "wrapper should report the deploy directory" \
    'grep -q "Deployed to: $DST\$" <<<"$out"'
check "runfiles should be flattened to the deploy root" \
    '[ -f "$DST/_main/test/make_lb_32x128_cts_base_4_cts" ]'
check "config.mk should be written under _main" \
    '[ -f "$DST/_main/config.mk" ]'
check "make wrapper should be generated" '[ -x "$DST/make" ]'
check "make wrapper should be valid bash" 'bash -n "$DST/make"'
check "make wrapper should exec the _main-relative make script" \
    'grep -qx "exec ./test/make_lb_32x128_cts_base_4_cts \"\$@\"" "$DST/make"'
check "make wrapper's exec target should exist" \
    '[ -x "$DST/_main/test/make_lb_32x128_cts_base_4_cts" ]'
check "make wrapper should actually run the stage make script" \
    '"$DST/make" >/dev/null 2>&1'

# (b) A design in @orfs. The make script sits in the @orfs repo dir, one
# level up from _main, so the wrapper must exec ./../<repo>/... -- the
# same string deploy.tpl generates for this design.
export MODE=orfs
out="$("$WRAPPER" @orfs//flow/designs/nangate45/gcd:gcd_cts 2>&1)"
rc=$?
echo "--- MODE=orfs (rc=$rc) ---"
echo "$out"
ODST="$(sed -n 's/^Deployed to: //p' <<<"$out")"
GCD_MAKE="+orfs_repositories+orfs/flow/designs/nangate45/gcd"
GCD_MAKE="$GCD_MAKE/make_gcd_cts_base_4_cts"
check "wrapper should succeed for a design in an external repository" \
    '[ "$rc" -eq 0 ]'
check "wrapper should report a deploy directory" '[ -n "$ODST" ]'
check "runfiles should be flattened to the deploy root" \
    '[ -f "$ODST/$GCD_MAKE" ]'
check "config.mk should be written under _main" \
    '[ -f "$ODST/_main/config.mk" ]'
check "make wrapper should be valid bash" 'bash -n "$ODST/make"'
check "make wrapper should exec the make script one level above _main" \
    'grep -qx "exec ./../$GCD_MAKE \"\$@\"" "$ODST/make"'
check "make wrapper should actually run the stage make script" \
    '"$ODST/make" >/dev/null 2>&1'

# (c) Two make scripts match: the wrapper must name both and fail rather
# than silently pick one.
export MODE=ambiguous
out="$("$WRAPPER" //pkg:dup_cts 2>&1)"
rc=$?
echo "--- MODE=ambiguous (rc=$rc) ---"
echo "$out"
check "wrapper should fail when the make script is ambiguous" \
    '[ "$rc" -ne 0 ]'
check "wrapper should say the make binaries are ambiguous" \
    'grep -q "multiple make binaries found" <<<"$out"'
check "wrapper should list the first candidate" \
    'grep -q "_main/test/make_dup_cts_base_4_cts" <<<"$out"'
check "wrapper should list the second candidate" \
    'grep -q "+orfs_repositories+orfs/flow/designs/dup/make_dup_cts_base_4_cts" <<<"$out"'
check "wrapper should not generate a make wrapper it cannot aim" \
    '[ ! -e "$ROOT/tmp/pkg/dup_cts_deps/make" ]'

# (d) No tarball anywhere: the diagnostic must print, and the exit non-zero.
export MODE=notar
out="$("$WRAPPER" //test:lb_32x128_cts 2>&1)"
rc=$?
echo "--- MODE=notar (rc=$rc) ---"
echo "$out"
check "wrapper should fail when no tarball is produced" '[ "$rc" -ne 0 ]'
check "wrapper should print the not-found diagnostic" \
    'grep -q "deps tarball not found" <<<"$out"'
check "wrapper should name the _deps_tar target" \
    'grep -q "_deps_tar" <<<"$out"'

# (e) Not an ORFS stage target: the build fails, with a helpful message.
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
