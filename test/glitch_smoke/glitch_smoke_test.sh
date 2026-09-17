#!/bin/sh
# A glitch exists with annotated delays and does not exist without them.
#
# The toolchain comes in as runfiles paths rather than being searched
# for: iverilog is two binaries plus a directory of code generators it
# finds through IVL_BASE, and a test that guesses where those are is a
# test that passes for the wrong reason the day the layout moves.
set -e

# The test starts in the _main tree of the runfiles, and $(rootpath)
# spells an external repository relative to exactly that -- as
# ../iverilog+/... -- so these resolve from here and nowhere else.
IV=$1
VVP=$2
SRC=$(dirname "$3")
# ivl_base sits beside the driver's own directory in the same repo.
BASE=$(dirname "$(dirname "$IV")")/ivl_base

for path in "$IV" "$VVP" "$BASE" "$SRC/glitch.v" "$SRC/glitch.sdf"; do
  test -e "$path" || { echo "glitch_smoke: missing $path" >&2; exit 1; }
done

OUT=${TEST_TMPDIR:-.}/smoke.vvp
IVL_BASE=$BASE "$IV" -gspecify -o "$OUT" "$SRC/tb.v" "$SRC/glitch.v"

pulses() {
  IVL_BASE=$BASE "$VVP" -M "$BASE" "$OUT" "$@" \
    | sed -n 's/^glitch_smoke: .* \([0-9]*\) time unit.*/\1/p'
}

zero=$(pulses)
annotated=$(pulses "+sdf=$SRC/glitch.sdf")
echo "glitch_smoke: y high for $zero time unit(s) at zero delay, \
$annotated annotated"

if [ -z "$zero" ] || [ -z "$annotated" ]; then
  echo "glitch_smoke: the simulation printed no verdict" >&2
  exit 1
fi
if [ "$zero" -ne 0 ]; then
  echo "glitch_smoke: a zero-delay simulation produced a pulse with width" >&2
  exit 1
fi
if [ "$annotated" -lt 1 ]; then
  echo "glitch_smoke: annotation produced no glitch -- the chain is broken" >&2
  exit 1
fi
