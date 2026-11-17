#!/bin/bash
set -euo pipefail

YOSYS="$1"
TEST_TCL="$2"
TEST_VERILOG="$3"
SYNTH_TCL="$4"

TEST_VERILOG="$TEST_VERILOG" SYNTH_TCL="$SYNTH_TCL" \
  "$YOSYS" -Q -ql /dev/stderr -c "$TEST_TCL"
echo "PASS: synth_retime_select_test"
