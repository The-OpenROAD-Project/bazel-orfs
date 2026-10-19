#!/usr/bin/env bash
# //:dirty without building a stage: a stub 'bazelisk' on PATH records each
# call and fails every build, so the test sees which stage target and output
# group a command asks for, the refusals, and status on a hand-made tree.
set -uo pipefail

DIRTY="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
WS="$TEST_TMPDIR/ws"
STUB="$TEST_TMPDIR/bin"
CALLS="$TEST_TMPDIR/calls"
mkdir -p "$WS" "$STUB"
printf 'tmp/\n' >"$WS/.gitignore"
printf 'tmp\n' >"$WS/.bazelignore"
cat >"$STUB/bazelisk" <<'EOF'
#!/usr/bin/env bash
echo "$*" >>"$CALLS"
exit 1
EOF
chmod +x "$STUB/bazelisk"
export PATH="$STUB:$PATH" CALLS BUILD_WORKSPACE_DIRECTORY="$WS" BUILD_WORKING_DIRECTORY="$WS"

FAILS=0
run() {
    : >"$CALLS"
    OUT="$("$DIRTY" "$@" 2>&1)"
    RC=$?
}
check() {
    if eval "$2"; then
        echo "PASS: $1"
    else
        echo "FAIL: $1"
        echo "  output: $OUT"
        echo "  calls: $(cat "$CALLS")"
        FAILS=$((FAILS + 1))
    fi
}

run
check "no arguments prints usage and fails" '[ $RC -ne 0 ] && grep -q "start" <<<"$OUT"'

check "usage offers --qt" 'grep -q -- "--qt" <<<"$OUT"'

run start //test:lb place --qt
check "--qt is an option of start, not a stray argument" \
    '! grep -q "unexpected arguments" <<<"$OUT" && grep -q -- "--output_groups=deps_files //test:lb_place" "$CALLS"'
check "--qt does not build Qt before the tree is installed" \
    '! grep -q -- "deps_qt" "$CALLS"'

run frobnicate
check "an unknown command is named" '[ $RC -ne 0 ] && grep -q "unknown command .frobnicate." <<<"$OUT"'

run start //test:lb banana
check "a word that is not a stage is named" '[ $RC -ne 0 ] && grep -q "banana. is not a stage" <<<"$OUT"'

run start //test:lb place
check "start builds the stage target's deps_files group" \
    'grep -q -- "build --output_groups=deps_files //test:lb_place" "$CALLS"'
check "a failed build is reported, not a bare set -e abort" \
    '[ $RC -ne 0 ] && grep -q "bazelisk build --output_groups=deps_files //test:lb_place failed" <<<"$OUT"'

run start //test:lb_place
check "a stage target's label stands for <flow> <stage>" \
    'grep -q -- "--output_groups=deps_files //test:lb_place" "$CALLS"'

run start //p:blk grt --variant probe
check "--variant names the variant's stage target" \
    'grep -q -- "--output_groups=deps_files //p:blk_probe_grt" "$CALLS"'

DIRTY_STARTUP_OPTS="--output_base=/ob" DIRTY_BUILD_OPTS="--jobs=3" run start //test:lb place
check "DIRTY_STARTUP_OPTS and DIRTY_BUILD_OPTS reach the nested build" \
    'grep -q -- "--output_base=/ob build --jobs=3 --output_groups=deps_files" "$CALLS"'

mkdir -p "$WS/tmp/orfs/flow/designs/asap7/gcd/gcd"
echo keep >"$WS/tmp/orfs/flow/designs/asap7/gcd/gcd/mine"
run start @orfs//flow/designs/asap7/gcd:gcd final
check "a flow in another repository has its tree under tmp/<repo>/<package>/<flow>" \
    '[ $RC -ne 0 ] && grep -q "refusing to replace tmp/orfs/flow/designs/asap7/gcd/gcd" <<<"$OUT"'
rm -rf "$WS/tmp/orfs"

mkdir -p "$WS/tmp/test/lb"
echo keep >"$WS/tmp/test/lb/mine"
run start //test:lb place
check "start refuses to replace a tree" \
    '[ $RC -ne 0 ] && grep -q "refusing to replace" <<<"$OUT" && [ -f "$WS/tmp/test/lb/mine" ] && [ ! -s "$CALLS" ]'

run next place --dir "$WS/tmp/nowhere"
check "next without a tree refuses" '[ $RC -ne 0 ] && grep -q "no tree" <<<"$OUT"'

run next banana
check "next names a word that is not a stage" '[ $RC -ne 0 ] && grep -q "banana. is not a stage" <<<"$OUT"'

T="$WS/tmp/test/lb"
mkdir -p "$T/_main"
cat >"$T/.dirty" <<'EOF'
flow //test:lb
variant base
tree 0123 dirty
stage floorplan scripts, earlier stages' results from bazel (2026-10-06 08:00)
ran do-floorplan 2026-10-06 08:01 exit 0
EOF
echo "export A?=1" >"$T/.config.mk.installed"
printf 'export A?=1\nexport PLACE_DENSITY = 0.5\n' >"$T/_main/config.mk"
run status --dir "$T"
check "status shows the history" 'grep -q "ran do-floorplan" <<<"$OUT"'
check "status shows an edited setting" 'grep -q "PLACE_DENSITY = 0.5" <<<"$OUT"'
check "status says a number from the tree needs the caveat" 'grep -q "from the dirty lane, not a clean build" <<<"$OUT"'

mkdir -p "$WS/tmp/old"
touch "$WS/tmp/old/.deps"
run status --dir "$WS/tmp/old"
check "a tree //:deps installed is named, with the move that carries it on" \
    '[ $RC -ne 0 ] && grep -q "installed by //:deps, now //:dirty" <<<"$OUT" && grep -q "mv tmp/old/.deps tmp/old/.dirty" <<<"$OUT"'

run next place --dir "$T"
check "next asks Bazel for the stage's inputs, not its results" \
    'grep -q -- "--output_groups=deps_inputs //test:lb_place" "$CALLS"'

if [ "$FAILS" -gt 0 ]; then
    echo "$FAILS failed"
    exit 1
fi
echo "all passed"
