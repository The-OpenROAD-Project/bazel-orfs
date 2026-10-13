#!/bin/sh
# Usage: <openroad> <lef count> <lefs...> <libs...>
set -e
openroad="$1"
shift
n="$1"
shift
LEFS=""
while [ "$n" -gt 0 ]; do
  LEFS="$LEFS $1"
  shift
  n=$((n - 1))
done
LIBS="$*"
MODEL="${TEST_TMPDIR:-.}/blk.lib"
export LEFS LIBS MODEL
here=$(dirname "$0")
"$openroad" -exit -no_init -no_splash "$here/write_model.tcl"
"$openroad" -exit -no_init -no_splash "$here/check_parent.tcl"
