#!/bin/sh
# abc_new maps big, small and top in turn; ABC's &verify must find each
# mapped network equivalent to its input. A failed ABC run that already
# wrote output.aig is only a warning in yosys, so look for that too.
log="$1"
fail=0
if grep -q "ABC: execution of command" "$log"; then
    echo "FAIL: an ABC run failed:"
    grep "ABC: execution of command" "$log"
    fail=1
fi
n=$(grep -c "Networks are equivalent" "$log")
if [ "$n" -ne 3 ]; then
    echo "FAIL: ABC verified $n of 3 modules as equivalent"
    fail=1
fi
exit $fail
