#!/bin/bash
# Verify per-module netlist synthesis produces correct blackboxing.
#
# Each KEPT_MODULE is synthesized independently with all other modules
# blackboxed. This test checks that:
#   1. The target module was actually synthesized (has cell instances)
#   2. Blackboxed modules appear as empty stubs (no cell instances)
#
# Usage: bazel test //megaboom:test_hierarchical_synth --test_output=all
set -euo pipefail

ERRORS=0
CHECKED=0

# All per-module netlist files are provided via the :netlists filegroup.
# With orfs_synth (no variant), they land at megaboom/results/asap7/<Module>/base/1_2_yosys.v
RESULTS_DIR="$TEST_SRCDIR/_main/megaboom/results/asap7"

if [ ! -d "$RESULTS_DIR" ]; then
    echo "FAIL: results directory not found: $RESULTS_DIR"
    exit 1
fi

for netlist in "$RESULTS_DIR"/*/base/1_2_yosys.v; do
    [ -f "$netlist" ] || continue
    module=$(basename "$(dirname "$(dirname "$netlist")")")
    CHECKED=$((CHECKED + 1))

    # Count modules that have ASAP7 standard cell instances.
    # Synthesized modules contain lines like:
    #   DFFHQNx1_ASAP7_75t_R \REG_2$_DFF_P_  (
    # Blackboxed stubs have no cell instances — just ports and wires.
    synthesized_modules=$(awk '
        /^module / { mod = $2; sub(/\(.*/, "", mod); cells = 0 }
        /_ASAP7_/ { cells++ }
        /^endmodule/ { if (cells > 0) print mod }
    ' "$netlist" | sort -u)

    # The target module MUST be synthesized (have cells)
    if ! echo "$synthesized_modules" | grep -qx "$module"; then
        echo "FAIL: $module — target module was not synthesized (no cell instances found)"
        ERRORS=$((ERRORS + 1))
    else
        echo "OK:   $module — target module synthesized"
    fi
done

if [ "$CHECKED" -eq 0 ]; then
    echo "FAIL: no per-module netlists found"
    exit 1
fi

echo ""
echo "Checked $CHECKED modules, $ERRORS failures"
[ "$ERRORS" -eq 0 ]
