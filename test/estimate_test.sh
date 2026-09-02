#!/bin/bash
set -eu
json="$1"
for field in clock_target est_achievable_raw wns utilization \
    num_macros macro_paths_mean macro_paths_sampled macros_pinned \
    density_lb_addon gp_overflow_target params; do
  grep -q "\"$field\"" "$json" || { echo "missing field: $field in $json"; cat "$json"; exit 1; }
done
echo "estimate json ok: $json"
