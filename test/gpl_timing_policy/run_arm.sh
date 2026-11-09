#!/bin/bash
# Run one A/B arm in a dirty-lane tree, from global placement through
# global route, with a bring-your-own openroad, and file its logs.
#
# usage: run_arm.sh TREE ARM OPENROAD [VAR=VALUE ...]
#   TREE      the dirty-lane tree (holds ./make)
#   ARM       a name; results land in tmp/gpl-study/arms/<design>/<ARM>
#   OPENROAD  the openroad binary to run
#   VAR=VALUE make variables (GPL_KEEP_OVERFLOW=0) or, prefixed env:,
#             environment for openroad (env:GPL_TD_SLACKS=fast)
set -euo pipefail
tree=$1
arm=$2
openroad=$3
shift 3
make_vars=()
for kv in "$@"; do
  case "$kv" in
  env:*) export "${kv#env:}" ;;
  *) make_vars+=("$kv") ;;
  esac
done
design=$(basename "$tree")
out=${OUT:-tmp/gpl_timing_policy}/arms/$design/$arm
rm -rf "$out"
mkdir -p "$out"
if [ "$openroad" != "-" ]; then export OPENROAD_EXE=$openroad; fi
start=$(date +%s.%N)
for step in do-3_1_place_gp_skip_io do-3_2_place_iop do-3_3_place_gp do-3_4_place_resized do-3_5_place_dp do-3_place do-cts do-grt; do
  "$tree/make" "${make_vars[@]}" "$step" >"$out/$step.out" 2>&1 || {
    echo "$arm: $step failed, see $out/$step.out"
    exit 1
  }
done
end=$(date +%s.%N)
awk -v a="$arm" -v s="$start" -v e="$end" 'BEGIN { printf "%s: done in %.1f s\n", a, e - s }'
logs=$(find "$tree" -path '*/logs/*' -name '3_3_place_gp.log' -printf '%h\n' | head -1)
cp "$logs"/*.log "$out/" 2>/dev/null || true
cp "$logs"/*.json "$out/" 2>/dev/null || true
