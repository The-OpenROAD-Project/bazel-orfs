#!/usr/bin/env bash
# Does discovery-mode parallel synthesis keep the discovered hierarchy?
#
# Arguments: the merged 1_2_yosys.v, then module names. A bare name must
# appear as its own `module` declaration; a name prefixed with `!` must
# not. Partition synthesis emits one netlist per kept module and the
# merge concatenates them, so a flattened result -- or one where a
# partition produced nothing -- fails here even though yosys exited zero;
# and a module that SYNTH_MINIMUM_KEEP_SIZE should have flattened but
# that survives as a boundary fails the `!` form.
set -euo pipefail
netlist=$1
shift
status=0
for spec in "$@"; do
  module=${spec#!}
  if grep -Eq "^module ${module}(\(|\s|$)" "$netlist"; then
    if [ "$spec" != "$module" ]; then
      echo "FAIL: 'module ${module}' present in $netlist but should be flattened" >&2
      status=1
    fi
  elif [ "$spec" = "$module" ]; then
    echo "FAIL: no 'module ${module}' in $netlist" >&2
    status=1
  fi
done
exit $status
