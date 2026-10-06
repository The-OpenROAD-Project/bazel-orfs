#!/usr/bin/env bash
# OpenROAD's generate_regfile (carried patch 0010) against this tool: for
# every register-file spec the flow uses, both write the same Verilog, DEF,
# abstract LEF and model liberty, byte for byte. The tool retires once its
# callers move to the command; until then this is what proves the move.
#   golden_test.sh <structured_gen> <openroad> <tech.lef> <cells.lef> <spec>...
set -euo pipefail

TOOL="$1" OPENROAD="$2" TECH="$3" CELLS="$4"
shift 4
OUT="${TEST_TMPDIR:-$(mktemp -d)}"
FAILS=0
for spec in "$@"; do
    name="$(basename "$spec" .regfile)"
    a="$OUT/$name.tool" b="$OUT/$name.openroad"
    mkdir -p "$a" "$b"
    "$TOOL" --spec "$spec" --lef "$TECH" --lef "$CELLS" --verilog "$a/rf.v" \
        --def "$a/rf.def" --lef-out "$a/rf.lef" --lib-out "$a/rf.lib" >"$a/log" 2>&1 ||
        { echo "FAIL: $name: structured_gen failed"; tail -3 "$a/log"; FAILS=$((FAILS + 1)); continue; }
    cat >"$b/run.tcl" <<EOF
read_lef $TECH
read_lef $CELLS
generate_regfile -spec $spec -verilog $b/rf.v -def $b/rf.def -lef $b/rf.lef -liberty $b/rf.lib
EOF
    "$OPENROAD" -exit -no_init -no_splash "$b/run.tcl" >"$b/log" 2>&1 ||
        { echo "FAIL: $name: generate_regfile failed"; tail -3 "$b/log"; FAILS=$((FAILS + 1)); continue; }
    for f in rf.v rf.def rf.lef rf.lib rf_pre_layout.lib; do
        if ! cmp -s "$a/$f" "$b/$f"; then
            echo "FAIL: $name: $f differs"
            diff "$a/$f" "$b/$f" | head -5
            FAILS=$((FAILS + 1))
        fi
    done
    echo "ok: $name"
done
[ "$FAILS" -eq 0 ] || { echo "$FAILS failed"; exit 1; }
echo "all identical"
