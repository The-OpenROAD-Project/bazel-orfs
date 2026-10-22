#!/bin/bash
# A/B of patch 0145 (study/exception-to-fast-path): VecRegionModule cts and
# grt in two dirty-lane trees laid out by
#   bazelisk run //:dirty -- start //test/coremark_joule/designs/asap7/xiangshan:VecRegionModule cts --dir tmp/ab/{A,B}
# A = bazelisk build -c opt @openroad//:openroad at main, B = the same
# with 0145, copied to tmp/pinplan/openroad_{base,exc}; interleaved, 3
# repeats each.
# Wall time per run and the stage's .odb kept for a byte comparison.
cd "$(dirname "$0")/../.."
R=_main/test/coremark_joule/designs/asap7/xiangshan/results/asap7/VecRegionModule/base
P=//test/coremark_joule/designs/asap7/xiangshan
declare -A EXE=([A]=$PWD/tmp/pinplan/openroad_base [B]=$PWD/tmp/pinplan/openroad_exc)
idle() { echo "load $(cut -d' ' -f1-3 /proc/loadavg); other builds: $(pgrep -fc '[b]azel(isk)? (build|test|run) ')"; }
run() { # stage target odb
  local stage=$1 target=$2 odb=$3
  for rep in 1 2 3; do
    for arm in A B; do
      echo "$(date +%H:%M:%S) $stage $arm rep $rep start; $(idle)"
      s=$(date +%s.%N)
      OPENROAD_EXE=${EXE[$arm]} tmp/ab/$arm/make $target > tmp/ab/out/${stage}_${arm}_$rep.log 2>&1
      rc=$?
      e=$(date +%s.%N)
      cp tmp/ab/$arm/$R/$odb tmp/ab/out/${stage}_${arm}_$rep.odb
      echo "RESULT $stage $arm $rep rc=$rc wall=$(echo "$e - $s" | bc) s md5=$(md5sum < tmp/ab/$arm/$R/$odb | cut -c1-12)"
    done
  done
}
date
run cts do-cts 4_cts.odb
for arm in A B; do
  t=$(bazelisk run @bazel-orfs//:dirty -- next grt --dir tmp/ab/$arm 2>&1 | sed -n 's|^next: .*/make ||p')
  echo "grt target in $arm: $t"
done
run grt "$t" 5_1_grt.odb
date
echo DONE
