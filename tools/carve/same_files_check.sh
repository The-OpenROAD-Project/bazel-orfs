#!/bin/sh
# Pairs of files, a b a b ...: every pair byte-identical; each pair that is
# not is named. Usage: same_files_check.sh <a> <b> [<a> <b> ...]
[ $# -ge 2 ] && [ $(($# % 2)) -eq 0 ] || {
  echo "usage: same_files_check.sh <a> <b> [<a> <b> ...]" >&2
  exit 2
}
status=0
while [ $# -ge 2 ]; do
  if cmp -s "$1" "$2"; then
    echo "same: $1 $2"
  else
    echo "DIFFERENT: $1 $2"
    status=1
  fi
  shift 2
done
exit $status
