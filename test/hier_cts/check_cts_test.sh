#!/bin/sh
# The CTS result of a design with registers in two modules, read back:
# every register is clocked and no pin is off its hierarchical net.
set -e
report="$1"
cat "$report"
value() { sed -n "s/^$1 //p" "$report"; }
fail=0
[ "$(value registers)" = 192 ] || { echo "FAIL: expected 192 registers"; fail=1; }
[ "$(value hier_nets)" -gt 0 ] || { echo "FAIL: no hierarchical nets, the hierarchy was not kept"; fail=1; }
[ "$(value unclocked)" = 0 ] || { echo "FAIL: unclocked registers after CTS"; fail=1; }
[ "$(value off_modnet)" = 0 ] || { echo "FAIL: pins off their hierarchical net after CTS"; fail=1; }
[ $fail = 0 ] && echo PASS
exit $fail
