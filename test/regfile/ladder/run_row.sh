#!/bin/bash
# run_row.sh <row> <timeout> [label]: build one ladder row (both arms to
# global route) in its own memory-capped scope, keep its JSON under
# tmp/regfile_ladder/rows/<row>[-label].json and regenerate the report.
# Run from the workspace root.
set -u
ROW=$1
LIMIT=$2
LABEL=${3:-}
OUT=tmp/regfile_ladder
mkdir -p $OUT/rows $OUT/logs
NAME=$ROW${LABEL:+-$LABEL}
LOG=$OUT/logs/$NAME.log
START=$(date +%s)
if ! timeout "$LIMIT" systemd-run --user --scope -q -p MemoryMax=48G \
    bazelisk build --jobs=12 //test/regfile/ladder:${ROW}_row >"$LOG" 2>&1; then
  echo "{\"name\": \"$NAME\", \"failed\": true, \"wall_seconds\": $(($(date +%s) - START))," \
    "\"error\": $(grep -hoE '\[ERROR [A-Z]+-[0-9]+\][^"]{0,160}|ERROR: [^"]{0,160}' "$LOG" | head -1 | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().strip()))')}" \
    >$OUT/rows/$NAME.json
  echo "$NAME: FAILED, see $LOG"
else
  cp -f bazel-bin/test/regfile/ladder/${ROW}_row.json $OUT/rows/$NAME.json
  chmod u+w $OUT/rows/$NAME.json
  echo "$NAME: built in $(($(date +%s) - START)) s"
fi
python3 test/regfile/ladder/report.py $OUT/rows >$OUT/report.md
