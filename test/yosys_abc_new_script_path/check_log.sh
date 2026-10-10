#!/bin/sh
# The liberty file sits under flow-scripts/, so "-script" appears in
# abc_new's arguments without -script being given. abc_new must still
# run its default script (&nf maps to cells), not abc9.script.default
# (&if -v; &mfs, a LUT script that leaves cells unmapped).
log="$1"
fail=0
if ! grep -q "^yosys exit 0$" "$log"; then
    echo "FAIL: yosys did not exit 0:"
    grep -E "ERROR|^yosys exit" "$log"
    fail=1
fi
if ! grep -q "ABC: + &nf" "$log"; then
    echo "FAIL: ABC did not run abc_new's default script (no &nf)"
    fail=1
fi
if grep -q "ABC: + &if -v" "$log"; then
    echo "FAIL: ABC ran abc9.script.default (&if -v)"
    fail=1
fi
exit $fail
