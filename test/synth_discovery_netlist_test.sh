#!/usr/bin/env bash
# Does discovery-mode parallel synthesis keep the discovered hierarchy?
#
# Arguments: the merged 1_2_yosys.v, then the module names that must
# appear as their own `module` declarations. Partition synthesis emits one
# netlist per kept module and the merge concatenates them, so a flattened
# result -- or one where a partition produced nothing -- fails here even
# though yosys exited zero.
set -euo pipefail
netlist=$1
shift
status=0
for module in "$@"; do
  if ! grep -Eq "^module ${module}(\(|\s|$)" "$netlist"; then
    echo "FAIL: no 'module ${module}' in $netlist" >&2
    status=1
  fi
done
exit $status
