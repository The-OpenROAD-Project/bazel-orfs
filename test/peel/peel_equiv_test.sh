#!/bin/bash
# The peel only regroups: the block flattened from its wrapper and core
# is the same circuit as the block from the RTL, which yosys proves with
# equiv_* (async2sync on both sides, the same model of an asynchronous
# reset for gold and gate). And the flops really moved: the named output register is in
# the wrapper, and the core has none of it.
#
# usage: peel_equiv_test.sh YOSYS RTL WRAPPER CORE MODULE REGISTER [NAME=VALUE ...]
#
# NAME=VALUE sets the RTL's parameters to match a split
# made with the same PEEL_PARAMS: a 32-bit multiply is beyond equiv's
# SAT in minutes, a 4-bit one is not, and the split does not depend on
# the width.
set -euo pipefail
yosys=$1
rtl=$2
wrapper=$3
core=$4
module=$5
register=$6
shift 6
chparam=""
for p in "$@"; do
  chparam="$chparam chparam -set ${p%%=*} ${p#*=} $module;"
done
"$yosys" -q -p "
  read_verilog -sv $rtl
  $chparam
  hierarchy -top $module
  proc; async2sync; opt_clean
  rename $module gold
  design -stash gold
  read_verilog $wrapper $core
  hierarchy -top $module
  proc; flatten; async2sync; opt_clean
  rename $module gate
  design -stash gate
  design -copy-from gold -as gold gold
  design -copy-from gate -as gate gate
  equiv_make gold gate equiv
  hierarchy -top equiv
  equiv_simple -seq 2
  equiv_induct
  equiv_status -assert
"
grep -Eq "reg (\[[0-9]+:0\] )?$register;" "$wrapper"
if grep -q "$register" "$core"; then
  echo "${module}_core still has $register" >&2
  exit 1
fi
echo "peel_equiv_test: $module = $module(wrapper) + ${module}_core, $register in the wrapper"
