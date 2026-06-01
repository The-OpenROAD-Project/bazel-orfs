#!/usr/bin/env bash
# Per-partition parallel synthesis.
# Reads kept_modules.json, picks modules where index % N == partition_id,
# and synthesizes each from its dedicated per-module RTLIL slice (produced
# by synth_canonicalize_module.tcl). The per-module slice already has all
# other kept modules blackboxed and the target renamed to its bare name,
# so synth.tcl just needs DESIGN_NAME=<bare> and SYNTH_CHECKPOINT=<slice>.
#
# When SYNTH_PARTITION_ID=top, synthesizes the top module (DESIGN_NAME)
# with all kept modules blackboxed against the global checkpoint (the top
# integration partition is the join point — scoping its inputs doesn't
# help wall time, and there's no per-module slice that contains the top).
#
# Environment:
#   SYNTH_PARTITION_ID   - this partition's index (0..N-1) or "top"
#   SYNTH_NUM_PARTITIONS - total number of partitions
#   RESULTS_DIR, SCRIPTS_DIR, etc. - standard ORFS env
set -euo pipefail

PARTITION_ID=${SYNTH_PARTITION_ID:?}
NUM_PARTITIONS=${SYNTH_NUM_PARTITIONS:?}
KEPT_JSON="$RESULTS_DIR/kept_modules.json"
OUTPUT="$RESULTS_DIR/partition_${PARTITION_ID}.v"

# Parse module list from JSON. Module names can contain '[' and ']'
# (slang elaborates parameterized instances to names like
# 'foo$bar.gen_tiles[0].i_tile.gen_banks[3]'), so a greedy sed regex is
# unsafe. Module names cannot contain '"', so extracting all quoted
# strings and skipping the first ("modules" key) is correct.
ALL_MODULES=$(grep -oE '"[^"]+"' "$KEPT_JSON" | tail -n +2 | sed 's/"//g')

# Sanitise a module name into a filename component. Must stay in lockstep
# with rules.bzl's per-module artifact naming and parallel_synth.mk's
# do-yosys-canonicalize-module log path.
sanitize() {
  printf '%s' "$1" | tr '$.[]' '____'
}

if [ "$PARTITION_ID" = "top" ]; then
  # Top integration: synthesize the top module from the global checkpoint
  # with every kept module blackboxed. This path retains the original
  # behavior — top doesn't have a per-module slice, and the macro inputs
  # aren't scoped here anyway.
  if [ "${SYNTH_SKIP_KEEP:-0}" = "1" ]; then
    CHECKPOINT="$RESULTS_DIR/1_1_yosys_canonicalize.rtlil"
    # SYNTH_KEEP_MODULES carries bare names; resolve each to canonical for
    # blackboxing. Same algorithm as synth_canonicalize_module.tcl.
    RTLIL_MODULES_FILE=$(mktemp)
    grep '^module \\' "$CHECKPOINT" | sed 's/^module \\//;s/ .*//' | grep -v '^$' > "$RTLIL_MODULES_FILE"
    RESOLVED_MODULES=()
    for module in $ALL_MODULES; do
      if grep -qxF "$module" "$RTLIL_MODULES_FILE"; then
        RESOLVED_MODULES+=("$module")
      else
        canonical=$(grep -m1 "^$(printf '%s' "$module" | sed 's/[.[\*^$()+?{|\\]/\\&/g')\\$" "$RTLIL_MODULES_FILE" || true)
        if [ -z "$canonical" ]; then
          echo "ERROR: SYNTH_KEEP_MODULES lists '$module' but it does not exist in the design." >&2
          echo "Available modules: $(tr '\n' ' ' < "$RTLIL_MODULES_FILE")" >&2
          rm -f "$RTLIL_MODULES_FILE"
          exit 1
        fi
        RESOLVED_MODULES+=("$canonical")
      fi
    done
    rm -f "$RTLIL_MODULES_FILE"
    ALL_MODULES=$(printf '%s\n' "${RESOLVED_MODULES[@]}")
  else
    CHECKPOINT="$RESULTS_DIR/1_1_yosys_keep.rtlil"
  fi
  BLACKBOXES=$(echo "$ALL_MODULES" | tr '\n' ' ')
  echo "=== Synthesizing top module: $DESIGN_NAME (blackboxes: $BLACKBOXES) ==="
  SYNTH_CHECKPOINT="$CHECKPOINT" \
  SYNTH_BLACKBOXES="$BLACKBOXES" \
    "$SCRIPTS_DIR/synth.sh" \
    "$SYNTH_TCL" \
    "$LOG_DIR/1_2_yosys_partition_top.log"
  cp "$RESULTS_DIR/1_2_yosys.v" "$OUTPUT"
  exit 0
fi

# Pick this partition's modules: index % N == partition_id
MY_MODULES=()
idx=0
while IFS= read -r module; do
  if (( idx % NUM_PARTITIONS == PARTITION_ID )); then
    MY_MODULES+=("$module")
  fi
  ((idx++)) || true
done <<< "$ALL_MODULES"

if [ ${#MY_MODULES[@]} -eq 0 ]; then
  # No modules assigned to this partition — produce empty output
  touch "$OUTPUT"
  exit 0
fi

echo "Partition $PARTITION_ID: synthesizing ${#MY_MODULES[@]} modules: ${MY_MODULES[*]}"

# Each MY_MODULES[i] is synthesised from its dedicated per-module RTLIL
# slice, which has all other kept modules blackboxed. The slice keeps
# the target module under its canonical (slang-elaborated) name — the
# canonical name is in a sidecar .name file produced by
# synth_canonicalize_module.tcl, and we pass it to synth.tcl as
# DESIGN_NAME so the emitted 1_2_yosys.v keeps the canonical name that
# downstream OpenROAD parent placement expects.
> "$OUTPUT"  # truncate output file
for module in "${MY_MODULES[@]}"; do
  sanitized=$(sanitize "$module")
  MODULE_CHECKPOINT="$RESULTS_DIR/partition_${sanitized}_canonical.rtlil"
  MODULE_NAME_FILE="$RESULTS_DIR/partition_${sanitized}_canonical.name"
  if [ ! -f "$MODULE_CHECKPOINT" ]; then
    echo "ERROR: per-module checkpoint missing: $MODULE_CHECKPOINT" >&2
    exit 1
  fi
  if [ ! -f "$MODULE_NAME_FILE" ]; then
    echo "ERROR: per-module canonical-name sidecar missing: $MODULE_NAME_FILE" >&2
    exit 1
  fi
  canonical_name=$(cat "$MODULE_NAME_FILE")
  echo "=== Synthesizing module: $module → $canonical_name (from $(basename "$MODULE_CHECKPOINT")) ==="
  # Truncate module name in log filename to avoid filesystem limits
  log_module="${module:0:80}"
  SYNTH_CHECKPOINT="$MODULE_CHECKPOINT" \
  DESIGN_NAME="$canonical_name" \
    "$SCRIPTS_DIR/synth.sh" \
    "$SYNTH_TCL" \
    "$LOG_DIR/1_2_yosys_partition_${PARTITION_ID}_${log_module}.log"

  # Append this module's netlist to partition output
  cat "$RESULTS_DIR/1_2_yosys.v" >> "$OUTPUT"
done
