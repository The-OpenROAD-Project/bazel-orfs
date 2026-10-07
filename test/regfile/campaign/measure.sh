#!/bin/bash
# measure.sh <label>: riscv32i-regfile to global route with the patches as
# they are in this checkout, then minimum period, failing endpoints, core
# and standard-cell area (global-route parasitics) appended to
# tmp/regfile-campaign/results.md. Run from the workspace root.
set -u
C=test/regfile/campaign
OUT=tmp/regfile-campaign; mkdir -p $OUT
LABEL="$1"
LOG=$OUT/build-$(date +%H%M%S).log
if ! timeout 40m bazelisk build @orfs//flow/designs/asap7/riscv32i-regfile:riscv_top_grt > $LOG 2>&1; then
  echo "| $(date +%H:%M) | $LABEL | FAILED | | | | $(grep -hoE '\[ERROR [A-Z]+-[0-9]+\][^\r]{0,100}' $LOG | head -1) |" >> $OUT/results.md
  exit 1
fi
D=$PWD/$OUT/daemon-$$; mkdir -p $D
(nohup timeout 30m bazelisk run //test/regfile:riscv32i_regfile_grt_odb_debug -- ODB_DEBUG_DIR=$D ODB_DEBUG_IDLE_SECS=120 > $D/launch.log 2>&1 &)
for i in $(seq 150); do [ -f $D/daemon.json ] && break; sleep 2; done
q() { python3 tools/odb_debug/odbdebug.py $D --tcl "$(cat $C/$1)" 2>&1; }
H=$(q histogram.tcl | head -1); A=$(q area.tcl | tail -1)
q worst_path.tcl > $OUT/worst-$(echo "$LABEL" | tr -c 'a-zA-Z0-9' _).txt
P=$(echo "$H" | sed -n 's/.*minperiod \([0-9]*\).*/\1/p'); F=$(echo "$H" | sed -n 's/.*failing \(.*\)/\1/p')
CO=$(echo "$A" | sed -n 's/core \([0-9]*\).*/\1/p'); SC=$(echo "$A" | sed -n 's/.*std cells \([0-9]*\).*/\1/p')
echo "| $(date +%H:%M) | $LABEL | $P | $F | $CO | $SC | |" >> $OUT/results.md
kill $(python3 -c "import json;print(json.load(open('$D/daemon.json'))['pid'])") 2>/dev/null
echo "$LABEL: $P ps"
