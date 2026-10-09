#!/usr/bin/env bash
# Did synthesis read the surgery's copy? vendored_top.v drives y straight
# from a, so a netlist synthesized from it has no cell; the copy inverts
# it, so the netlist synthesized from the copy has an inverter.
set -euo pipefail
netlist=$1
if ! grep -Eq '^\s*INVx[0-9A-Za-z_]*\s' "$netlist"; then
  echo "FAIL: no inverter in $netlist; synthesis read the original, not the surgery's copy" >&2
  exit 1
fi
