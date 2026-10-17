#!/bin/bash
# aes-block floorplan across core sizes, instrumented: does mpl place, how
# long it takes, and what the exact check says about each problem.
cd "$(dirname "$0")/../.."
tree="tmp/@orfs//flow/designs/asap7/aes-block/aes_cipher_top"
here=test/mpl_exact
for top in "$@"; do
  out="$OUT/aes_core_$top"
  rm -rf "$out"; mkdir -p "$out"
  start=$(date +%s.%N)
  CORE_AREA="2.052 2.160 $top $top" MPL_DUMP_DIR="$out" OPENROAD_EXE="$OPENROAD_DUMP" \
    timeout 1800 "$tree/make" do-floorplan > "$out/floorplan.log" 2>&1
  status=$?
  secs=$(echo "$(date +%s.%N) - $start" | bc)
  mpl=$(grep -o "MPL-0[0-9]*" "$out/floorplan.log" | grep -v MPL-0500 | sort -u | tr '\n' ' ')
  runtime=$(grep -o "MPL-0500\] Runtime: [0-9.]*" "$out/floorplan.log" | awk '{print $3}')
  python3 $here/dump_to_problems.py aes_$top "$out"/mpl_dump.*.jsonl --csv "$out/problems.csv" > "$out/problems.txt"
  "$DRIVER" 10 < "$out/problems.txt" > "$out/exact.csv"
  summary=$(python3 $here/compare.py "$out/problems.csv" "$out/exact.csv" | tail -1)
  echo "core_top=$top exit=$status floorplan=${secs}s mpl_runtime=${runtime}s msgs=[$mpl] $summary"
done
