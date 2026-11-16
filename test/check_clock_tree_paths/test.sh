#!/bin/bash
# test.sh <openroad> <test.tcl> <check_clock_tree_paths.tcl> <a fixture>
set -euo pipefail
CHECK_CLOCK_TREE_PATHS_TCL="$3" FIXTURES="$(dirname "$4")" \
  "$1" -exit -no_init -no_splash "$2" | tee "$TEST_TMPDIR/out"
grep -qx pass "$TEST_TMPDIR/out"
