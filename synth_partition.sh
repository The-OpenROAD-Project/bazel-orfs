#!/usr/bin/env bash
# Per-partition parallel synthesis.
# Reads kept_modules.json, picks modules where index % N == partition_id,
# and synthesizes each one. With a pinned SYNTH_KEEP_MODULES the source is
# the module's dedicated per-module RTLIL slice (produced by
# synth_canonicalize_module.tcl, all other kept modules blackboxed);
# with a discovered list it is the global keep checkpoint plus
# SYNTH_BLACKBOXES. See the comment above the module loop.
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

# The design's name for an RTLIL module, stripped of yosys's mangling.
# "\\serv_alu" and "$paramod\\serv_alu\\W=1" and
# "$paramod$<hash>\\serv_alu" all name serv_alu: the design's name is the
# component after the first backslash in every form.
rtlil_base_name() {
  printf '%s' "$1" | awk '{
    if (substr($0, 1, 1) == "\\") { print substr($0, 2) }
    else { n = split($0, parts, "\\\\"); if (n >= 2) print parts[2] }
  }'
}

rtlil_base_names() {
  while IFS= read -r line; do
    base=$(rtlil_base_name "$line")
    [ -n "$base" ] && printf '%s\n' "$base"
  done < "$1"
}

# The canonical RTLIL name for a module the design calls $1, or empty.
# A parameterized module instantiated once has exactly one mangled name;
# one instantiated with several parameter sets has several, and this
# takes the first -- which is wrong for such a design and is why the
# caller's error message is worth reading rather than guessing.
rtlil_module_for() {
  while IFS= read -r line; do
    if [ "$(rtlil_base_name "$line")" = "$1" ]; then
      printf '%s' "$line"
      return 0
    fi
  done < "$2"
  return 0
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
    # Every module in the checkpoint, as yosys names it. An
    # unparameterized module is "\name"; a parameterized one is
    # "$paramod\name\param=value" or "$paramod$<hash>\name". Matching
    # only the first form finds nothing in a design that parameterizes
    # its submodules -- SERV parameterizes all of them -- and
    # SYNTH_KEEP_MODULES then fails on names that are present under a
    # mangled spelling.
    grep '^module ' "$CHECKPOINT" | sed 's/^module //;s/ .*//' | grep -v '^$' > "$RTLIL_MODULES_FILE"
    RESOLVED_MODULES=()
    for module in $ALL_MODULES; do
      canonical=$(rtlil_module_for "$module" "$RTLIL_MODULES_FILE")
      if [ -z "$canonical" ]; then
        echo "ERROR: SYNTH_KEEP_MODULES lists '$module' but it does not exist in the design." >&2
        echo "Available modules: $(rtlil_base_names "$RTLIL_MODULES_FILE" | tr '\n' ' ')" >&2
        rm -f "$RTLIL_MODULES_FILE"
        exit 1
      fi
      RESOLVED_MODULES+=("$canonical")
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

# Two modes, decided by whether SYNTH_KEEP_MODULES was pinned:
#
# Pinned (SYNTH_SKIP_KEEP=1): each module is synthesised from its
# dedicated per-module RTLIL slice, which has all other kept modules
# blackboxed. The slice keeps the target module under its canonical
# (slang-elaborated) name — the canonical name is in a sidecar .name
# file produced by synth_canonicalize_module.tcl, and we pass it to
# synth.tcl as DESIGN_NAME so the emitted 1_2_yosys.v keeps the
# canonical name that downstream OpenROAD parent placement expects.
# The slices exist because bazel could declare one action per name at
# analysis time.
#
# Discovered (no list): the kept modules were found by synth_keep.tcl
# inside a build action, so no per-module slice could be declared. Each
# module is synthesised from the global keep checkpoint with every other
# kept module blackboxed via SYNTH_BLACKBOXES. Names in kept_modules.json
# came out of the RTLIL, so they are already canonical. This is the
# original partition loop, before per-module slices (f3c5254) made the
# pinned mode cache-stable; it costs cache stability, not correctness.
> "$OUTPUT"  # truncate output file
for module in "${MY_MODULES[@]}"; do
  # Truncate module name in log filename to avoid filesystem limits
  log_module="${module:0:80}"
  if [ "${SYNTH_SKIP_KEEP:-0}" != "1" ]; then
    BLACKBOXES=""
    while IFS= read -r m; do
      if [ "$m" != "$module" ]; then
        BLACKBOXES="${BLACKBOXES:+$BLACKBOXES }$m"
      fi
    done <<< "$ALL_MODULES"
    echo "=== Synthesizing module: $module (from 1_1_yosys_keep.rtlil, blackboxes: $BLACKBOXES) ==="
    SYNTH_CHECKPOINT="$RESULTS_DIR/1_1_yosys_keep.rtlil" \
    SYNTH_BLACKBOXES="$BLACKBOXES" \
    DESIGN_NAME="$module" \
      "$SCRIPTS_DIR/synth.sh" \
      "$SYNTH_TCL" \
      "$LOG_DIR/1_2_yosys_partition_${PARTITION_ID}_${log_module}.log"
    cat "$RESULTS_DIR/1_2_yosys.v" >> "$OUTPUT"
    continue
  fi

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
  SYNTH_CHECKPOINT="$MODULE_CHECKPOINT" \
  DESIGN_NAME="$canonical_name" \
    "$SCRIPTS_DIR/synth.sh" \
    "$SYNTH_TCL" \
    "$LOG_DIR/1_2_yosys_partition_${PARTITION_ID}_${log_module}.log"

  # Append this module's netlist to partition output
  cat "$RESULTS_DIR/1_2_yosys.v" >> "$OUTPUT"
done
