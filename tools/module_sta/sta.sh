#!/bin/bash
# Run one of module_sta's Tcl scripts in OpenSTA or OpenROAD, its
# liberty files unpacked beside it.
#
#   sta.sh <opensta or openroad> <script.tcl> <libs.tar> [<memories dir>...]
#
# libs.tar is libs.tcl's: the platform's and the macros' liberty, and the
# memories AUTO_MEMORIES wrote for the whole design. Each memories dir is a
# partition's own (parallel synthesis with verilog_slices writes one per
# partition); a memory's post-layout view is taken over its pre-layout one,
# and one file per name, as several partitions may hold the same memory.
# The script reads the rest of its inputs from the environment.
set -euo pipefail
sta=$1
script=$2
tarf=$3
shift 3
w=$(mktemp -d -p "${PSTA_TMP:-$PWD}")
mkdir "$w/libs"
tar -xf "$tarf" -C "$w/libs"
for d in "$@"; do
  find -L "$d" -name '*.lib' | sort | while read -r f; do
    b=$(basename "$f")
    case "$b" in
    *_pre_layout.lib)
      if [ -e "${f%_pre_layout.lib}.lib" ]; then continue; fi
      ;;
    esac
    if [ ! -e "$w/libs/$b" ]; then cp "$f" "$w/libs/$b"; fi
  done
done
PSTA_LIBS="$(find -L "$w/libs" -type f | sort | tr '\n' ' ')"
export PSTA_LIBS
ulimit -s unlimited 2>/dev/null || true
rc=0
${STA_WRAP:-} "$sta" -no_splash -exit "$script" || rc=$?
rm -rf "$w"
exit $rc
