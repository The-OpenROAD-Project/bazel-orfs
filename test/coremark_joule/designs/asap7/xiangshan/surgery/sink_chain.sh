#!/bin/bash
# sink_chain.sh SINK YOSYS SLANG SINKS_TXT IN OUT: every sink in SINKS_TXT, in order
set -euo pipefail
SINK=$1 YOSYS=$2 SLANG=$3 LIST=$4 IN=$5 OUT=$6
W=$(dirname $OUT)/$(basename $OUT .sv).work
mkdir -p $W
cur=$IN n=0
while IFS= read -r line; do
  case "$line" in ''|'#'*) continue ;; esac
  n=$((n+1))
  # shellcheck disable=SC2086
  $SINK $line --yosys $YOSYS --slang $SLANG --work $W $cur $W/step$n.sv
  cur=$W/step$n.sv
done < $LIST
cp $cur $OUT
rm -rf $W
