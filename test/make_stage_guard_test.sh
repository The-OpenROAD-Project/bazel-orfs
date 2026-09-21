#!/usr/bin/env bash
#
# Regression test for make.tpl's deployed-tree stage guard.
#
# A deployed _deps tree holds one stage's inputs exactly as bazel built
# them. A bare stage target lets ORFS's dependency chain rebuild the
# upstream results from inputs the tree never received, so what the tree
# runs stops matching what the build produced. The guard refuses those
# targets and names the `do-` form instead.
#
# Two things are pinned besides the refusal itself:
#
#  1. `synth` is told to run `do-yosys`. ORFS's Makefile has no do-synth
#     target, so naming one would send the reader into a second error.
#
#  2. The guard is scoped to a deployed tree, which is the case where
#     FLOW_HOME arrives from the template rather than from the build's
#     environment. With FLOW_HOME set, every target passes: bazel's own
#     actions must not be second-guessed by this script.
set -uo pipefail

tpl=$1
status=0

run() {
  # Prints the script's stderr; the exit code is returned in $rc. The
  # guard exits 2 before exec, so an exec failure downstream (this
  # template is unsubstituted, MAKE_PATH is empty) cannot be mistaken
  # for a refusal.
  err=$(FLOW_HOME= sh "$tpl" "$@" 2>&1 >/dev/null)
  rc=$?
}

refuses() {
  run "$1"
  if [ "$rc" != 2 ]; then
    echo "FAIL: '$1' exited $rc, expected 2 (refusal)" >&2
    status=1
  elif ! printf '%s' "$err" | grep -q "refusing target '$1'"; then
    echo "FAIL: '$1' was refused without naming the target: $err" >&2
    status=1
  elif [ -n "${2:-}" ] && ! printf '%s' "$err" | grep -q -- "$2"; then
    echo "FAIL: '$1' refusal does not point at '$2': $err" >&2
    status=1
  fi
}

passes() {
  run "$1"
  if printf '%s' "$err" | grep -q "refusing target"; then
    echo "FAIL: '$1' was refused and should not be: $err" >&2
    status=1
  fi
}

for stage in floorplan place cts grt route final generate_abstract; do
  refuses "$stage" "do-$stage"
done
refuses synth do-yosys
refuses all do-yosys
refuses clean_all "Re-deploy"

for target in do-yosys do-floorplan do-place do-cts do-grt do-route do-final \
  do-generate_abstract run open_floorplan gui_place clean_floorplan; do
  passes "$target"
done

# Build-time: FLOW_HOME comes from the environment, so nothing is refused.
err=$(FLOW_HOME=/nonexistent sh "$tpl" floorplan 2>&1 >/dev/null)
if printf '%s' "$err" | grep -q "refusing target"; then
  echo "FAIL: the guard fired with FLOW_HOME set: $err" >&2
  status=1
fi

exit $status
