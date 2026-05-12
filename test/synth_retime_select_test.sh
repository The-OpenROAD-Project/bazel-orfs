#!/bin/bash
set -euo pipefail

YOSYS="$1"
TEST_TCL="$2"
TEST_VERILOG="$3"
SYNTH_TCL="$4"

# Guard #1: synth.tcl must use `{*}` list-expansion on SYNTH_RETIME_MODULES,
# not bare `$::env(...)`. Bare substitution passes the whole space-separated
# value as a single arg to `select`, silently turning retime into a no-op.
if ! grep -q 'select {\*}\$::env(SYNTH_RETIME_MODULES)' "$SYNTH_TCL"; then
    echo "FAIL: synth.tcl does not use {*}\$::env(SYNTH_RETIME_MODULES)" >&2
    grep -n 'SYNTH_RETIME_MODULES' "$SYNTH_TCL" >&2 || true
    exit 1
fi

# Guard #2: behavioral check — yosys really does treat `$var` vs `{*}$var`
# the way the patch assumes. Belt-and-braces against a future yosys change.
TEST_VERILOG="$TEST_VERILOG" "$YOSYS" -Q -ql /dev/stderr -c "$TEST_TCL"
echo "PASS: synth_retime_select_test"
