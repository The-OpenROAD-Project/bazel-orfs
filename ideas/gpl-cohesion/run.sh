#!/bin/bash
# XSTile's parent re-placed with the cohesion pull (the arm "P3b" of
# ideas/xiangshan-timing.md entry 54): a dirty lane from the parent's
# floorplan, global placement with -clusters_file, then cts and grt, and the
# KPI read at grt. Run from a bazel-orfs checkout whose MODULE.bazel lists
# openroad-gpl-cohesion.patch among OpenROAD's patches (it applies to
# OpenROAD bfac0546; rebase it for a later pin) and whose @openroad is built
# -c opt (bazelisk build -c opt @openroad//:openroad).
set -e
X=test/coremark_joule/designs/asap7/xiangshan
here=$(cd "$(dirname "$0")" && pwd)
T=tmp/gpl-cohesion
bazelisk run //:dirty -- start //$X:XSTile place --dir $T --fresh
g=$T/+orfs_repositories+orfs/flow/scripts/global_place.tcl
sed -i "s|  lappend global_placement_args {-timing_driven}|  lappend global_placement_args {-timing_driven} -clusters_file $here/xstile_clusters.json|" $g
grep -q clusters_file $g
export OPENROAD_EXE=$PWD/$(bazelisk cquery -c opt --output=files @openroad//:openroad 2>/dev/null)
for st in place cts grt; do
  [ $st = place ] || bazelisk run //:dirty -- next $st --dir $T
  $T/make do-$st
done
cp $X/kpi_run.tcl $T/
KPI_OUT=$PWD/$T/kpi.txt KPI_STAGE=grt ORFS_DEPLOY_ANY_STAGE=1 \
  $T/make run RUN_SCRIPT=$(readlink -f $T/kpi_run.tcl)
cat $T/kpi.txt
