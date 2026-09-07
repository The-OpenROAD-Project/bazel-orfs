#!/usr/bin/env bash
# Cost of loading one .odb: wall time and peak RSS, repeated, reported as a
# CSV row per run. This is the baseline the in-memory half of the SoA study
# moves: the slot layouts say what the per-slot saving is, and this says how
# much RSS there is to save it from.
#
# usage: read_db_cost.sh <openroad-binary> <design.odb> [repeats] [csv]
set -euo pipefail

binary="${1:?openroad binary}"
odb="${2:?.odb file}"
repeats="${3:-3}"
csv="${4:-/dev/stdout}"

script="$(mktemp)"
trap 'rm -f "$script"' EXIT
cat > "$script" <<TCL
read_db ${odb}
TCL

echo "run,wall_s,peak_rss_kb,odb_bytes" > "$csv"
for run in $(seq 1 "$repeats"); do
  # %e wall seconds, %M peak resident set size in KiB.
  stats="$(/usr/bin/time -f '%e,%M' "$binary" -no_init -exit "$script" \
      2>&1 >/dev/null | tail -1)"
  echo "${run},${stats},$(stat -c %s "$odb")" >> "$csv"
done
