#!/bin/sh
# The stop passes the database CTS wrote and fires, naming the pin, on
# one with a clock pin off its hierarchical net.
set -e
report="$1"
cat "$report"
value() { sed -n "s/^$1 //p" "$report"; }
fail=0
[ "$(value as_written)" = 0 ] || { echo "FAIL: the stop fired on the database CTS wrote"; fail=1; }
[ -n "$(value taken)" ] || { echo "FAIL: no clock pin on a hierarchical net to take off"; fail=1; }
[ "$(value fired)" = 1 ] || { echo "FAIL: the stop did not fire"; fail=1; }
[ "$(value names_it)" = 1 ] || { echo "FAIL: the stop did not name the pin"; fail=1; }
[ $fail = 0 ] && echo PASS
exit $fail
