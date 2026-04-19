#!/usr/bin/env bash
# Per-partition parallel synthesis.
# Reads kept_modules.json, picks modules where index % N == partition_id,
# and synthesizes each sequentially with all others blackboxed.
#
# When SYNTH_PARTITION_ID=top, synthesizes the top module (DESIGN_NAME)
# with all kept modules blackboxed.
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

# Parse module list from JSON using sed (avoids python wrapper issues)
# JSON format: {"modules": ["mod1", "mod2", ...]}
ALL_MODULES=$(sed 's/.*\[//;s/\].*//;s/"//g;s/,/\n/g;s/ //g' "$KEPT_JSON")

# When SYNTH_SKIP_KEEP is set, the keep-hierarchy discovery was skipped.
# Partitions read from canonical RTLIL and run full synthesis (coarse+fine).
if [ -n "${SYNTH_SKIP_KEEP:-}" ]; then
  CHECKPOINT="$RESULTS_DIR/1_1_yosys_canonicalize.rtlil"
  # Validate that every SYNTH_KEEP_MODULES entry exists in the canonical RTLIL
  RTLIL_MODULES_FILE=$(mktemp)
  grep '^module \\' "$CHECKPOINT" | sed 's/^module \\//;s/ .*//' | grep -v '^$' > "$RTLIL_MODULES_FILE"
  # Map bare module names to canonical names. HDL frontends like slang add
  # "$instance_path" suffixes during elaboration (e.g. AluDataModule becomes
  # AluDataModule$ProcessingUnit.slices_0.execute.alu). Resolve each entry
  # to its canonical form so that DESIGN_NAME is set correctly later.
  RESOLVED_MODULES=()
  for module in $ALL_MODULES; do
    if grep -qxF "$module" "$RTLIL_MODULES_FILE"; then
      RESOLVED_MODULES+=("$module")
    else
      # Try prefix match: "Name" matches "Name$..." in the RTLIL
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
  # Replace ALL_MODULES with the resolved canonical names
  ALL_MODULES=$(printf '%s\n' "${RESOLVED_MODULES[@]}")
else
  CHECKPOINT="$RESULTS_DIR/1_1_yosys_keep.rtlil"
fi

if [ "$PARTITION_ID" = "top" ]; then
  # Synthesize the top module with all kept modules blackboxed
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

# Build blackbox list: all modules except the one being synthesized
> "$OUTPUT"  # truncate output file
for module in "${MY_MODULES[@]}"; do
  BLACKBOXES=""
  while IFS= read -r m; do
    if [ "$m" != "$module" ]; then
      BLACKBOXES="${BLACKBOXES:+$BLACKBOXES }$m"
    fi
  done <<< "$ALL_MODULES"

  echo "=== Synthesizing module: $module (blackboxes: $BLACKBOXES) ==="

  # Run synthesis from keep checkpoint for this module.
  # SYNTH_CHECKPOINT: skip coarse synth + keep_hierarchy (already done)
  # SYNTH_BLACKBOXES: all other kept modules are blackboxed
  # DESIGN_NAME: override to this module
  # Truncate module name in log filename to avoid filesystem limits
  log_module="${module:0:80}"
  SYNTH_CHECKPOINT="$CHECKPOINT" \
  SYNTH_BLACKBOXES="$BLACKBOXES" \
  DESIGN_NAME="$module" \
    "$SCRIPTS_DIR/synth.sh" \
    "$SYNTH_TCL" \
    "$LOG_DIR/1_2_yosys_partition_${PARTITION_ID}_${log_module}.log"

  # Append this module's netlist to partition output
  cat "$RESULTS_DIR/1_2_yosys.v" >> "$OUTPUT"
done
