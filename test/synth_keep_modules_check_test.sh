#!/bin/bash
set -euo pipefail

YOSYS="$1"
TEST_TCL="$2"
TEST_VERILOG="$3"
SYNTH_TCL="$4"
SYNTH_KEEP_TCL="$5"

# Guard #1: synth.tcl must walk SYNTH_KEEP_MODULES via `catch {rtlil::set_attr
# -mod $module keep_hierarchy 1}` and `error` if any remain unmatched, with a
# `$strict` carve-out for partition mode (SYNTH_BLACKBOXES set).
for f in "$SYNTH_TCL" "$SYNTH_KEEP_TCL"; do
    if ! grep -q 'catch {rtlil::set_attr -mod \$module keep_hierarchy 1}' "$f"; then
        echo "FAIL: $f does not use catch{rtlil::set_attr ...} on SYNTH_KEEP_MODULES" >&2
        grep -n 'SYNTH_KEEP_MODULES\|set_attr' "$f" >&2 || true
        exit 1
    fi
    if ! grep -q 'SYNTH_KEEP_MODULES contains' "$f"; then
        echo "FAIL: $f does not emit a typo-list error" >&2
        exit 1
    fi
done

# Guard #2: synth.tcl (but NOT synth_keep.tcl) must skip the strict check when
# SYNTH_BLACKBOXES is set — the partition's own top is the only module
# present in the elaborated RTL, the other kept names are blackboxes.
if ! grep -q 'SYNTH_BLACKBOXES' "$SYNTH_TCL"; then
    echo "FAIL: synth.tcl missing SYNTH_BLACKBOXES strict-mode carve-out" >&2
    exit 1
fi

# Guard #3: behavioral check — exercise the catch{rtlil::set_attr} mechanism
# itself on a 4-module fixture and assert it accumulates the right names.
TEST_VERILOG="$TEST_VERILOG" "$YOSYS" -Q -ql /dev/stderr -c "$TEST_TCL"
echo "PASS: synth_keep_modules_check_test"
