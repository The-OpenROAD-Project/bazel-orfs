#!/usr/bin/env bash
# Each spec's measured read arrival, one JSON line per spec.
#   calibrate.sh <openroad> <tcl> <tech.lef> <cells.lef> <setRC.tcl> <out.json> -- <libs>... -- <specs>...
set -euo pipefail
OPENROAD="$1" TCL="$2" TECH_LEF="$3" CELL_LEF="$4" SET_RC="$5" OUT="$6"
shift 6
[ "$1" = "--" ] && shift
LIBS=()
while [ "$1" != "--" ]; do LIBS+=("$1"); shift; done
shift
export TECH_LEF CELL_LEF SET_RC
export LIB_FILES="${LIBS[*]}"
: >"$OUT"
for spec in "$@"; do
    log="$OUT.$(basename "$spec").log"
    SPEC="$spec" "$OPENROAD" -exit -no_init -no_splash "$TCL" >"$log" 2>&1 || { tail -25 "$log" >&2; exit 1; }
    grep -E '^raw_read_ps ' "$log" | awk -v s="$(basename "$spec" .regfile)" \
        '{ printf "{\"spec\": \"%s\", \"raw_read_ps\": %s, \"buffered_read_ps\": %s, \"read_ps\": %s, \"write_ps\": %s, \"buffers\": %s}\n", s, $2, $4, $6, $8, $10 }' >>"$OUT"
done
