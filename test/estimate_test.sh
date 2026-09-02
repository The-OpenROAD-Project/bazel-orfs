#!/bin/bash
set -eu
json="$1"
for field in clock_target est_achievable_raw wns utilization \
    place_density density_floor gp_overflow_target runtime_s; do
  grep -q "\"$field\"" "$json" || { echo "missing field: $field in $json"; cat "$json"; exit 1; }
done
echo "estimate json ok: $json"
