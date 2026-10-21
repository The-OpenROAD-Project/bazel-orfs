#!/bin/sh
# One arm of the isolate_loop_sinks sweep: a dirty lane of an ORFS design from
# its floorplan through place, CTS and global route, then measure.tcl.
#
#   tools/headroom/sweep/arm.sh <flow target prefix> <name> <base|iso> <seed>
#   tools/headroom/sweep/arm.sh @orfs//flow/designs/asap7/jpeg:jpeg_encoder jpeg iso 2
#
# Run from the workspace root. Appends one line to $SWEEP_OUT/results.txt
# (default tmp/sweep). "iso" sources isolate_loop_sinks.tcl before CTS.
set -u
D=$1 N=$2 ARM=$3 SEED=$4
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=${SWEEP_OUT:-tmp/sweep}
mkdir -p "$OUT"
OUT=$(cd "$OUT" && pwd)
T=tmp/sw_${N}_${ARM}_${SEED}
LOG=$OUT/${N}_${ARM}_${SEED}
EXTRA="GPL_RANDOM_SEED=$SEED"
if [ "$ARM" = iso ]; then
  EXTRA="$EXTRA PRE_CTS_TCL=$HERE/../isolate_loop_sinks.tcl ISOLATE_LOOP_SINKS=100"
fi
if ! bazelisk run //:dirty -- start "$D" place --dir "$T" --fresh >"$LOG.start.log" 2>&1; then
  echo "$N $ARM seed$SEED start FAILED" >>"$OUT/results.txt"
  exit 1
fi
t0=$(date +%s)
for st in place cts grt; do
  [ "$st" = place ] || bazelisk run //:dirty -- next "$st" --dir "$T" >>"$LOG.start.log" 2>&1
  # shellcheck disable=SC2086
  if ! "$T/make" "do-$st" $EXTRA >"$LOG.$st.log" 2>&1; then
    echo "$N $ARM seed$SEED $st FAILED" >>"$OUT/results.txt"
    exit 1
  fi
done
MEASURE_OUT=$LOG.txt "$T/make" run RUN_SCRIPT="$HERE/measure.tcl" >"$LOG.measure.log" 2>&1
iso=$(grep -a 'Isolated' "$LOG.cts.log" | head -1)
echo "$N $ARM seed$SEED ($(($(date +%s) - t0))s) $(cat "$LOG.txt" 2>/dev/null) $iso" >>"$OUT/results.txt"
[ -s "$LOG.txt" ] && rm -rf "$T"
