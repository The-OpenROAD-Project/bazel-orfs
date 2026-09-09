#!/bin/sh
# Profile one global placement run inside a deployed ORFS place tree.
#
#   test/gpl_runtime/profile.sh <deployed_tree> <out_dir> [threads] [script]
#
# <deployed_tree> is what `bazelisk run //:deps -- <label>_place` produced
# (the directory holding ./make). <out_dir> collects the log, perf.data,
# the perf stat counters and the flat reports. OPENROAD_EXE in the
# environment is honored by the deployed make, so the same command profiles
# the flow's binary or a bring-your-own build.
#
# The run is the study's unit of measurement, so only one may be in flight
# on the machine at a time; the wall and CPU numbers are meaningless
# otherwise.
set -eu

tree=$(cd "$1" && pwd)
out=$2
threads=${3:-$(nproc)}
script=${4:-$(dirname "$0")/gpl_place_ios.tcl}
script=$(cd "$(dirname "$script")" && pwd)/$(basename "$script")
stem=$(basename "$script" .tcl)
repo=$(cd "$(dirname "$0")/../.." && pwd)
freq=${PERF_FREQ:-199}
# CALLGRAPH=1 records frame-pointer call chains; only meaningful with a
# binary built -fno-omit-frame-pointer (the BYO build), and it makes
# perf.data large, so it is off by default.
callgraph=${CALLGRAPH:+--call-graph fp}

mkdir -p "$out"
out=$(cd "$out" && pwd)

# Every logged line gets an elapsed-seconds stamp, so the log itself says
# where the wall went between the placer's own progress lines.
run_cmd="python3 $repo/log_timestamps.py"

{
  echo "tree=$tree"
  echo "threads=$threads"
  echo "script=$script"
  echo "openroad=${OPENROAD_EXE:-deployed}"
  echo "start=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$out/run.txt"

perf stat -o "$out/stat.txt" \
  -e task-clock,context-switches,cpu-migrations,page-faults,cycles,instructions,cache-misses \
  perf record -q -F "$freq" $callgraph -o "$out/perf.data" -- \
  "$tree/make" run \
    "RUN_SCRIPT=$script" \
    "RUN_LOG_NAME_STEM=$stem" \
    "RUN_CMD=$run_cmd" \
    "NUM_CORES=$threads" \
  > "$out/make.stdout" 2>&1 || { echo "run failed, see $out/make.stdout"; exit 1; }

# LOG_DIR sits under the design's own package inside the deployed tree.
log=$(find "$tree" -name "$stem.log" -path "*/logs/*" | head -1)
cp "$log" "$out/$stem.log"

# --no-inline: resolving inlined frames through addr2line takes minutes on
# a 380 MB binary and adds nothing to a self-time table. -G folds the
# call chains out of the flat report; samples.txt keeps them for the
# flame graph.
perf report -i "$out/perf.data" --no-children --no-inline -G --stdio --sort comm,dso,sym \
  --percent-limit 0.05 2>/dev/null > "$out/flat.txt"
perf script -i "$out/perf.data" --no-inline 2>/dev/null > "$out/samples.txt"

# The result fingerprint, for the QoR axis: a byte-identical ODB is the
# strongest statement a change can make.
odb=$(find "$tree" -name "3_1_place_gp_ios.odb" | head -1)
{
  echo "odb_sha1=$(sha1sum "$odb" | cut -c1-40)"
  echo "hpwl_line=$(grep -E '^\[.*\]\s+[0-9]+ \|' "$out/$stem.log" | tail -1 | tr -s ' ')"
  echo "end=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} >> "$out/run.txt"
grep -h 'Elapsed time' "$out/$stem.log" | tail -1
