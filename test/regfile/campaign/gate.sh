#!/bin/bash
# gate.sh <openroad>: generate riscv32i's spec and src/ram's test spec
# standalone, per bit_folds and word_group, and print tile width, die and
# whether the placement is legal. Seconds; no flow. From the workspace
# root, OPENROAD_SRC set to an OpenROAD checkout (for test/asap7).
set -eu
OR=$(readlink -f "$1"); W=tmp/regfile-campaign/gate; mkdir -p $W
L=$OPENROAD_SRC/test/asap7
python3 - $W <<'PY'
import re, sys
def spec(patch, path):
    s = open(patch).read()
    a = s.index("+++ b/%s\n" % path); a = s.index("\n", a) + 1
    m = re.match(r"@@ -0,0 \+1,(\d+) @@\n", s[a:])
    return "\n".join(l[1:] for l in s[a + m.end():].split("\n")[:int(m.group(1))]) + "\n"
open(sys.argv[1] + "/riscv.regfile", "w").write(spec("patches/0089-orfs-auto-memories-regfiles.patch", "flow/designs/asap7/riscv32i-regfile/regfile.regfile"))
open(sys.argv[1] + "/small.regfile", "w").write(spec("patches/0010-openroad-ram-generate-regfile.patch", "src/ram/test/generate_regfile_asap7.regfile"))
PY
cd $W
for spec in riscv small; do for folds in 1 2; do for wg in 1 2; do
  [ $spec = small ] && [ $folds = 2 ] && continue
  f=${spec}_f${folds}_g${wg}.regfile
  grep -v "^bit_folds\|^word_group" $spec.regfile > $f
  echo "bit_folds $folds" >> $f
  echo "word_group $wg" >> $f  # needs word-groups.diff applied
  cat > run.tcl <<TCL
read_lef $L/asap7_tech_1x_201209.lef
read_lef $L/asap7sc7p5t_28_R_1x_220121a.lef
generate_regfile -spec $f -def out.def
check_placement
TCL
  echo "$spec folds=$folds wg=$wg: $($OR -no_init -no_splash -exit run.tcl 2>&1 | grep -oE 'tiles [0-9]+ sites wide|die [0-9.]+ x [0-9.]+ um|RAM-[0-9]+.*|DPL-[0-9]+.*|\[ERROR.*' | tr '\n' ' ')"
done; done; done
