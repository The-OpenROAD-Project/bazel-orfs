#!/usr/bin/env bash
# The kept queues are modules of the netlist by their path names, and no
# generator-numbered Queue is left. slang may append $<instance path>.
set -euo pipefail
netlist=$1
module_names=$2
for module in Queue__Mul__extraQueue Queue__Div__requestQueue; do
  if ! grep -Eq "^module \\\\?${module}[\$ (]" "$netlist"; then
    echo "FAIL: kept module $module is not a module of $netlist" >&2
    exit 1
  fi
done
if grep -Eq '^module \\?Queue(_[0-9]+)?[$ (]' "$netlist"; then
  echo "FAIL: a generator-numbered Queue is left in $netlist" >&2
  exit 1
fi
if ! grep -q '"Queue__Div__requestQueue"' "$module_names"; then
  echo "FAIL: $module_names does not name Queue__Div__requestQueue" >&2
  exit 1
fi
