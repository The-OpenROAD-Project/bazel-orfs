#!/bin/sh
# Regenerate the checked-in plan of the miniature planned parent from
# mini_gen.py and the planner. Run from the repo root; the drift test
# fails when plan/ no longer matches what this produces.
set -e
out=tmp/planned_parent_regen
rm -rf "$out"
python3 test/planned_parent/mini_gen.py --out "$out"
python3 tools/macro_select/plan_floorplan.py "$out/plan.json" --out "$out/plan_out.json" --emit "$out" > /dev/null
for f in BlockA_pins.tcl BlockB_pins.tcl BlockC_pins.tcl BlockD_pins.tcl place_macros.tcl netlists.txt plan.bzl; do
  cp "$out/$f" test/planned_parent/plan/$f
done
echo "test/planned_parent/plan regenerated"
