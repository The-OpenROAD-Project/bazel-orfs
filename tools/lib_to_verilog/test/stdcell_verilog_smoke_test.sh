#!/bin/bash
# Integration smoke test for stdcell_verilog() against a tiny .lib/.lef
# fixture. Verifies the rule wires arguments through the genrule
# correctly and that the emitted .v files contain the expected modules.
set -euo pipefail

DFF_V="$1"
EMPTY_V="$2"

# Sequential / latch / combinational cells from tiny.lib must each appear
# in the main .v file.
for mod in INVx1 DFFx1 LATCHx1; do
    if ! grep -q "^module $mod" "$DFF_V"; then
        echo "FAIL: $DFF_V missing module $mod" >&2
        exit 1
    fi
done

# Combinational INVx1 must materialize the Liberty `function : "!A"`
# as a Verilog `assign Y = ~A`.
if ! grep -q 'assign Y = ~A' "$DFF_V"; then
    echo "FAIL: INVx1 in $DFF_V did not get Verilog `assign Y = ~A`" >&2
    exit 1
fi

# Flip-flop DFFx1 must emit a clocked always block.
if ! grep -q 'always @(posedge CLK)' "$DFF_V"; then
    echo "FAIL: DFFx1 in $DFF_V did not get always@(posedge CLK)" >&2
    exit 1
fi

# Physical-only cells from tiny.lef (no .lib entry) must appear as
# empty-module stubs in the empty .v file.
for mod in FILLER1 TAPCELL; do
    if ! grep -q "^module $mod" "$EMPTY_V"; then
        echo "FAIL: $EMPTY_V missing empty-module stub for $mod" >&2
        exit 1
    fi
done

# Cells that do have a .lib entry must NOT be repeated as empty stubs.
for mod in INVx1 DFFx1 LATCHx1; do
    if grep -q "^module $mod" "$EMPTY_V"; then
        echo "FAIL: $EMPTY_V should not contain stub for $mod" >&2
        exit 1
    fi
done

echo "PASS: stdcell_verilog_smoke_test"
