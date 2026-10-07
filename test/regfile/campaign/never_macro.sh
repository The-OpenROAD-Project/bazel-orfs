#!/bin/bash
# never_macro.sh <lane>: riscv32i (the flip-flop design, CORE_UTILIZATION
# 62) with src/riscv32i/regfile.v replaced by the register file the
# generator writes for riscv32i-regfile, to global route in a //:deps
# tree under tmp/<lane>: no macro, no dissolve, the array's cells placed
# and sized like any other. Build riscv32i-regfile's synthesis first, with
# the patches as they are in this checkout. Run from the workspace root.
set -eu
T=tmp/$1/tree; mkdir -p tmp/$1
D=external/+orfs_repositories+orfs/flow/designs
B=$(bazelisk info bazel-bin)/$D/asap7/riscv32i-regfile/results/asap7/riscv_top/base/memories/regfile.v
# The taps are the floorplan's to place.
python3 - "$B" tmp/$1/regfile_gen.v <<'PY'
import re, sys
s = open(sys.argv[1]).read()
open(sys.argv[2], "w").write(re.sub(r"\n  TAPCELL_ASAP7_75t_R [^;]*;", "", s))
PY
bazelisk run //:deps -- start @orfs//flow/designs/asap7/riscv32i:riscv_top synth --dir $T
R=$D/asap7/riscv32i/results/asap7/riscv_top/base
sed -i "s#$D/src/riscv32i/regfile.v#$PWD/tmp/$1/regfile_gen.v#" \
  $T/_main/config.mk $T/${R#external/}/1_synth.short.mk
grep -q "tmp/$1/regfile_gen.v" $T/_main/config.mk
$T/make do-yosys-canonicalize do-yosys ./$R/1_2_yosys.sdc do-1_synth
for s in floorplan place cts grt; do
  bazelisk run //:deps -- next $s --dir $T
  $T/make do-$s
done
echo "measure: $T/make run RUN_SCRIPT=\$PWD/tools/odb_debug/daemon.tcl ODB_FILE=<tree results>/5_1_grt.odb ODB_DEBUG_DIR=\$PWD/tmp/$1/daemon, then histogram.tcl and area.tcl"
