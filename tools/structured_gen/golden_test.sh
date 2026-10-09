#!/usr/bin/env bash
# OpenROAD's generate_regfile (carried patch 0010) builds every spec here
# and writes all its views. The specs cover every spec feature; whether
# what they build computes the RTL's function is test/regfile/sim's to
# check. This tool's own output is no longer the reference:
# generate_regfile has moved past it (inverting read gates, the clock
# gate per word).
#   golden_test.sh <openroad> <tech.lef> <cells.lef> <spec>...
set -euo pipefail

OPENROAD="$1" TECH="$2" CELLS="$3"
shift 3
OUT="${TEST_TMPDIR:-$(mktemp -d)}"
FAILS=0
for spec in "$@"; do
    name="$(basename "$spec" .regfile)"
    b="$OUT/$name"
    mkdir -p "$b"
    cat >"$b/run.tcl" <<TCL
read_lef $TECH
read_lef $CELLS
generate_regfile -spec $spec -verilog $b/rf.v -def $b/rf.def -lef $b/rf.lef -liberty $b/rf.lib
TCL
    if ! "$OPENROAD" -exit -no_init -no_splash "$b/run.tcl" >"$b/log" 2>&1; then
        echo "FAIL: $name: generate_regfile failed"
        tail -3 "$b/log"
        FAILS=$((FAILS + 1))
        continue
    fi
    for f in rf.v rf.def rf.lef rf.lib rf_pre_layout.lib; do
        [ -s "$b/$f" ] || { echo "FAIL: $name: no $f"; FAILS=$((FAILS + 1)); }
    done
    echo "ok: $name"
done
[ "$FAILS" -eq 0 ] || { echo "$FAILS failed"; exit 1; }
echo "all built"
