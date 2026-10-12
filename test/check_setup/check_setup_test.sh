#!/bin/sh
# usage: check_setup_test.sh <openroad> <tcl> <verilog> <lef count> <lef>... <lib>...
set -e
openroad=$1
tcl=$2
VERILOG=$3
n=$4
shift 4
LEFS=""
while [ "$n" -gt 0 ]; do
  LEFS="$LEFS $1"
  shift
  n=$((n - 1))
done
LIBS="$*"
export VERILOG LEFS LIBS
exec "$openroad" -exit -no_init -no_splash "$tcl"
