#!/usr/bin/env bash
# Per-partition parallel synthesis.
# Synthesizes the kept module SYNTH_PARTITION_MODULE names, or reads
# kept_modules.json and picks the modules where index % N == partition_id. With a pinned SYNTH_KEEP_MODULES the source is
# the module's dedicated per-module RTLIL slice (produced by
# synth_canonicalize_module.tcl, all other kept modules blackboxed);
# with a discovered list it is the global keep checkpoint plus
# the blackbox list. See the comment above the module loop.
#
# The blackbox list goes to synth.tcl in a file, SYNTH_BLACKBOXES_FILE,
# one name per line, not in the SYNTH_BLACKBOXES environment variable:
# Linux caps one environment string at 128 KiB (MAX_ARG_STRLEN), and
# XSTile_flat's 2,250 kept modules are 206 KB of names, so execve of
# synth.sh failed with "Argument list too long" on every partition.
#
# When SYNTH_PARTITION_ID=top, synthesizes the top module (DESIGN_NAME)
# with all kept modules blackboxed against the global checkpoint (the top
# integration partition is the join point — scoping its inputs doesn't
# help wall time, and there's no per-module slice that contains the top).
#
# Environment:
#   SYNTH_PARTITION_MODULE - the one kept module this partition synthesizes
#                            (pinned SYNTH_KEEP_MODULES only); else
#   SYNTH_PARTITION_ID     - this partition's index (0..N-1) or "top"
#   SYNTH_NUM_PARTITIONS   - total number of partitions
#   RESULTS_DIR, SCRIPTS_DIR, etc. - standard ORFS env
set -euo pipefail

BLACKBOXES_FILE="$OBJECTS_DIR/synth_partition_blackboxes.txt"

# Sanitise a module name into a filename component. Must stay in lockstep
# with rules.bzl's per-module artifact naming and parallel_synth.mk's
# do-yosys-canonicalize-module log path.
sanitize() {
  printf '%s' "$1" | tr '$.[]' '____'
}

# A partition log's file name, the module given: past 200 characters its
# first 180 and the whole name's checksum, so the file system takes it
# (255 bytes) and two long names stay apart. A pinned keep list names a
# partition after its module, so the name holds the module twice.
log_name() {
  local n="1_2_yosys_partition_${PARTITION_ID}_$1"
  if [ "${#n}" -gt 200 ]; then
    n="${n:0:180}_$(printf '%s' "$n" | cksum | cut -d' ' -f1)"
  fi
  printf '%s.log' "$n"
}

if [ -n "${SYNTH_PARTITION_MODULE:-}" ]; then
  # The partition is named by its module, not by an index into the kept
  # list, so nothing about the list reaches its action key.
  if [ "${SYNTH_SKIP_KEEP:-0}" != "1" ]; then
    echo "ERROR: SYNTH_PARTITION_MODULE needs a pinned SYNTH_KEEP_MODULES (SYNTH_SKIP_KEEP=1)." >&2
    exit 1
  fi
  PARTITION_ID=$(sanitize "$SYNTH_PARTITION_MODULE")
  OUTPUT="$RESULTS_DIR/partition_${PARTITION_ID}.v"
  MY_MODULES=("$SYNTH_PARTITION_MODULE")
else
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

  if [ "$PARTITION_ID" = "top" ]; then
    # Top integration: synthesize the top module from the global checkpoint
    # with every kept module blackboxed. This path retains the original
    # behavior — top doesn't have a per-module slice, and the macro inputs
    # aren't scoped here anyway.
    if [ "${SYNTH_SKIP_KEEP:-0}" = "1" ]; then
      CHECKPOINT="$RESULTS_DIR/1_1_yosys_canonicalize.rtlil"
      # SYNTH_KEEP_MODULES carries bare names; resolve each to canonical for
      # blackboxing. Same algorithm as synth_canonicalize_module.tcl.
      # rtlil_names.py reads the checkpoint's module names, every spelling
      # yosys gives one, and stops naming any kept module it lacks.
      # shellcheck disable=SC2086
      ALL_MODULES=$("$PYTHON_EXE" "$RTLIL_NAMES_PY" "$CHECKPOINT" $ALL_MODULES)
    else
      CHECKPOINT="$RESULTS_DIR/1_1_yosys_keep.rtlil"
    fi
    mkdir -p "$OBJECTS_DIR"
    printf '%s\n' "$ALL_MODULES" > "$BLACKBOXES_FILE"
    echo "=== Synthesizing top module: $DESIGN_NAME (blackboxes: $(wc -l < "$BLACKBOXES_FILE") kept modules) ==="
    SYNTH_CHECKPOINT="$CHECKPOINT" \
    SYNTH_BLACKBOXES_FILE="$BLACKBOXES_FILE" \
      "$SCRIPTS_DIR/synth.sh" \
      "$SYNTH_TCL" \
      "$LOG_DIR/1_2_yosys_partition_top.log"
    cp "$RESULTS_DIR/1_2_yosys.v" "$OUTPUT"
    exit 0
  fi

  # Pick this partition's modules: index % N == partition_id. An empty
  # kept list is one empty line to `<<<`; skipped, or partition 0 ran
  # synth.sh with DESIGN_NAME="", synthesised the top, and the merge
  # wrote the top twice (once more from the top partition).
  MY_MODULES=()
  idx=0
  while IFS= read -r module; do
    [ -n "$module" ] || continue
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
# kept module blackboxed via SYNTH_BLACKBOXES_FILE. Names in kept_modules.json
# came out of the RTLIL, so they are already canonical. This is the
# original partition loop, before per-module slices (f3c5254) made the
# pinned mode cache-stable; it costs cache stability, not correctness.
> "$OUTPUT"  # truncate output file
for module in "${MY_MODULES[@]}"; do
  # Truncate module name in log filename to avoid filesystem limits
  log_module="${module:0:80}"
  if [ "${SYNTH_SKIP_KEEP:-0}" != "1" ]; then
    mkdir -p "$OBJECTS_DIR"
    while IFS= read -r m; do
      if [ "$m" != "$module" ]; then
        printf '%s\n' "$m"
      fi
    done <<< "$ALL_MODULES" > "$BLACKBOXES_FILE"
    echo "=== Synthesizing module: $module (from 1_1_yosys_keep.rtlil, blackboxes: $(wc -l < "$BLACKBOXES_FILE") other kept modules) ==="
    SYNTH_CHECKPOINT="$RESULTS_DIR/1_1_yosys_keep.rtlil" \
    SYNTH_BLACKBOXES_FILE="$BLACKBOXES_FILE" \
    DESIGN_NAME="$module" \
      "$SCRIPTS_DIR/synth.sh" \
      "$SYNTH_TCL" \
      "$LOG_DIR/$(log_name "$log_module")"
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
    "$LOG_DIR/$(log_name "$log_module")"

  # Append this module's netlist to partition output
  cat "$RESULTS_DIR/1_2_yosys.v" >> "$OUTPUT"
done
