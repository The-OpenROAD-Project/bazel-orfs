#!/bin/bash
# The ibex arms, serially, so their wall times compare.
set -u
here=$(cd "$(dirname "$0")" && pwd)
# the dirty-lane tree: bazelisk run //:dirty -- start //test/regfile/designs:ibex_core_ibex_flops_1240 place
tree=${TREE:-tmp/test/regfile/designs/ibex_core_ibex_flops_1240}
run() { "$here/run_arm.sh" "$tree" "$@" || echo "arm $1 failed"; }
run tdbase -
run tdvirt - GPL_KEEP_OVERFLOW=0
run tdsta - GPL_KEEP_OVERFLOW=0 env:GPL_TD_SLACKS=sta
run tdfast - GPL_KEEP_OVERFLOW=0 env:GPL_TD_SLACKS=fast
run tdcmp - GPL_KEEP_OVERFLOW=0 env:GPL_TD_SLACKS=fast env:GPL_TD_COMPARE=1
run tdoff - GPL_TIMING_DRIVEN=0
