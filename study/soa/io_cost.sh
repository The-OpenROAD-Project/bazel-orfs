#!/usr/bin/env bash
# What the field-major format costs in time and memory, measured rather than
# argued: read and write of the same design, three runs, best of three.
#
# Write time is the difference between a read-and-write run and a read-only
# run of the same binary and file, which keeps the process start-up and the
# read itself out of the number.
#
# usage: io_cost.sh <openroad> <design.odb> <label> [csv]
set -euo pipefail

binary="$(readlink -f "${1:?openroad binary}")"
design="$(readlink -f "${2:?design .odb}")"
label="${3:?label}"
csv="${4:-/dev/stdout}"

work="$(mktemp -d ./tmp/io_cost.XXXXXX)"
trap 'rm -rf "$work"' EXIT

printf 'read_db %s\n' "$design" > "$work/read.tcl"
printf 'read_db %s\nwrite_db %s/out.odb\n' "$design" "$work" > "$work/readwrite.tcl"

best() {  # echoes "<seconds>,<peak rss kb>" for the best of three runs
  local script="$1" best_time="" best_rss=""
  for _ in 1 2 3; do
    local stats
    stats="$(/usr/bin/time -f '%e,%M' "$binary" -no_init -exit "$script" \
        2>&1 >/dev/null | tail -1)"
    local seconds="${stats%%,*}" rss="${stats##*,}"
    if [ -z "$best_time" ] || awk "BEGIN{exit !($seconds < $best_time)}"; then
      best_time="$seconds"
      best_rss="$rss"
    fi
  done
  echo "$best_time,$best_rss"
}

read_stats="$(best "$work/read.tcl")"
both_stats="$(best "$work/readwrite.tcl")"
read_s="${read_stats%%,*}"
both_s="${both_stats%%,*}"

if [ ! -s "$csv" ]; then
  echo "label,design,read_s,write_s,peak_rss_kb,bytes" > "$csv"
fi
echo "${label},$(basename "$design"),${read_s},$(awk "BEGIN{printf \"%.2f\", $both_s - $read_s}"),${read_stats##*,},$(stat -c %s "$design")" >> "$csv"
