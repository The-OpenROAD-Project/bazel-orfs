#!/bin/bash
# The peel only regroups: Src flattened from its wrapper and core is the
# same circuit as Src from the RTL, which yosys proves with equiv_*. And
# the flops really moved: the output register is in the wrapper, and the
# core has none of it.
set -euo pipefail
yosys=$1
rtl=$2
wrapper=$3
core=$4
"$yosys" -q -p "
  read_verilog -sv $rtl
  hierarchy -top Src
  proc; opt_clean
  rename Src gold
  design -stash gold
  read_verilog $wrapper $core
  hierarchy -top Src
  proc; flatten; opt_clean
  rename Src gate
  design -stash gate
  design -copy-from gold -as gold gold
  design -copy-from gate -as gate gate
  equiv_make gold gate equiv
  hierarchy -top equiv
  equiv_simple -seq 2
  equiv_induct
  equiv_status -assert
"
grep -q "reg \[31:0\] r_out" "$wrapper"
if grep -q "r_out" "$core"; then
  echo "Src_core still has r_out" >&2
  exit 1
fi
echo "peel_equiv_test: Src = Src(wrapper) + Src_core, r_out in the wrapper"
