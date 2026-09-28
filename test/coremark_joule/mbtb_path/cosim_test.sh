#!/bin/sh
# A generated block against its RTL in a random co-simulation (yosys sim,
# cells from the asap7 liberty functions). Not an equivalence proof.
#   cosim_test.sh YOSYS TB GOLD_RTL[,GOLD_RTL...] GATE_NETLIST CYCLES EXPECT LIB...
# MODULE in the environment names the module compared (default
# MainBtbWriteBufferEnq); the gold files may define its submodules.
# EXPECT is pass, or fail for a mutant: a check that cannot fail checks
# nothing. MUTATE=A:B in the environment replaces the first cell A by B
# in a copy of the netlist.
set -eu
yosys=$1 tb=$2 gold=$3 gate=$4 cycles=$5 expect=$6
shift 6
work=${TEST_TMPDIR:-.}
module=${MODULE:-MainBtbWriteBufferEnq}
if [ -n "${MUTATE:-}" ]; then
  from=${MUTATE%%:*} to=${MUTATE#*:}
  awk -v a="$from" -v b="$to" '!done && index($0, a) { sub(a, b); done = 1 } { print }' "$gate" > "$work/mutant.v"
  gate=$work/mutant.v
fi
ys=$work/cosim.ys
: > "$ys"
for lib in "$@"; do
  echo "read_liberty -ignore_miss_func $lib" >> "$ys"
done
cat >> "$ys" <<EOS
read_verilog $gate
rename $module gate
read_verilog -sv $(echo "$gold" | tr , ' ')
rename $module gold
read_verilog -sv $tb
hierarchy -top cosim_tb
proc
chformal -lower
flatten
opt_clean
sim -clock clock -n $cycles -zinit -assert
EOS
if "$yosys" -q -s "$ys" > "$work/cosim.log" 2>&1; then got=pass; else got=fail; fi
grep -E 'ERROR' "$work/cosim.log" | head -3 || true
if [ "$got" != "$expect" ]; then
  echo "cosim: expected $expect, got $got"
  exit 1
fi
echo "cosim: $got over $cycles cycles, as expected"
