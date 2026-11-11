#!/usr/bin/env bash
# Pairs of files, a b a b ...: every pair byte-identical.
set -u
status=0
while [ $# -ge 2 ]; do
  if cmp -s "$1" "$2"; then
    echo "same: $(basename "$1")"
  else
    echo "DIFFERENT: $1 $2"
    status=1
  fi
  shift 2
done
exit $status
