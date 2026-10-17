#!/bin/bash
# Run every deployed floorplan lane with the instrumented OpenROAD, dump
# mpl's problems, convert them and compare with the exact check.
# env: OPENROAD_DUMP (binary), DRIVER (packing_driver), OUT (dump root)
cd "$(dirname "$0")/../.."
here=test/mpl_exact
while read -r flow; do
  design=$(echo "$flow" | sed 's|@orfs//flow/designs/||; s|:.*||; s|/|_|g')
  tree="tmp/$(echo "$flow" | sed 's|:|/|')"
  out="$OUT/$design"
  if [ ! -x "$tree/make" ]; then echo "NOTREE $design"; continue; fi
  if [ -f "$out/exact.csv" ]; then echo "SKIP $design"; continue; fi
  rm -rf "$out"; mkdir -p "$out"
  start=$(date +%s)
  MPL_DUMP_DIR="$out" OPENROAD_EXE="$OPENROAD_DUMP" timeout 3600 "$tree/make" do-floorplan > "$out/floorplan.log" 2>&1
  status=$?
  secs=$(( $(date +%s) - start ))
  mpl=$(grep -o "MPL-0[0-9]*" "$out/floorplan.log" | grep -v "MPL-0500" | sort -u | tr '\n' ' ')
  if ls "$out"/mpl_dump.*.jsonl > /dev/null 2>&1; then
    python3 $here/dump_to_problems.py "$design" "$out"/mpl_dump.*.jsonl --csv "$out/problems.csv" > "$out/problems.txt"
    timeout 3600 "$DRIVER" 10 < "$out/problems.txt" > "$out/exact.csv"
    summary=$(python3 $here/compare.py "$out/problems.csv" "$out/exact.csv" | tail -1)
  else
    summary="no mpl dump"
  fi
  echo "DONE $design floorplan_exit=$status ${secs}s mpl_msgs=[$mpl] $summary"
done < $here/flows.txt
echo ALLDONE
