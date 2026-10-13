#!/usr/bin/env bash
# OpenROAD's generate_ram, through ORFS's translation of a spec
# (regfile_ram.py, what AUTO_MEMORIES_REGFILES runs), builds every spec
# here in the spec's mode (a macro unless it says netlist) and writes all
# its views. The specs cover every spec feature; whether what they build
# computes the RTL's function is test/regfile/sim's to check. This tool's
# own output is no longer the reference: generate_ram has moved past it
# (inverting read gates, the clock gate per word).
#   golden_test.sh <ram_gen> <regfile_ram.py> <openroad> <tech.lef>
#                  <cells.lef> <libs> <spec>...
# <libs> is one argument, the liberty files separated by spaces.
set -euo pipefail

RAM_GEN="$1" REGFILE_RAM="$2" OPENROAD="$3" TECH="$4" CELLS="$5" LIBS="$6"
shift 6
OUT="${TEST_TMPDIR:-$(mktemp -d)}"
FAILS=0
lib_args=()
for lib in $LIBS; do
    lib_args+=(--lib "$lib")
done
for spec in "$@"; do
    name="$(basename "$spec" .regfile)"
    module="$(sed -n 's/^module[[:space:]]*//p' "$spec")"
    shape="$(sed -n 's/^mode[[:space:]]*//p' "$spec")"
    [ "$shape" = netlist ] || shape=macro
    b="$OUT/$name"
    if ! "$RAM_GEN" --regfile-ram "$REGFILE_RAM" --spec "$spec" \
        --module "$module" --openroad "$OPENROAD" --lef "$TECH" \
        --lef "$CELLS" "${lib_args[@]}" --shape "$shape" --out "$b" \
        >"$OUT/$name.log" 2>&1; then
        echo "FAIL: $name: generate_ram failed"
        tail -3 "$OUT/$name.log"
        FAILS=$((FAILS + 1))
        continue
    fi
    block="${module}_ram"
    [ -s "$b/${block}_core.odb" ] && block="${block}_core"
    for f in "$block.odb" "$block.v" "$block.place" "$block.lef" "$block.lib"; do
        [ -s "$b/$f" ] || { echo "FAIL: $name: no $f"; FAILS=$((FAILS + 1)); }
    done
    echo "ok: $name ($shape)"
done
[ "$FAILS" -eq 0 ] || { echo "$FAILS failed"; exit 1; }
echo "all built"
