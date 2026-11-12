#!/bin/sh
# The Top's second pass against its first (crossing_verdict.py), after a
# control: a report against itself must do nothing, or the verdict could not
# tell a pass that did nothing from one that moved the crossings.
# Usage: crossing_verdict.sh <crossing_verdict> <budget_ps> <firm crossing.txt>
#          <final crossing.txt> [crossing_verdict options...]
set -e
[ $# -ge 4 ] || {
  echo "usage: crossing_verdict.sh <crossing_verdict> <budget_ps> <firm crossing.txt> <final crossing.txt> [options...]" >&2
  exit 2
}
verdict="$1"
budget="$2"
firm="$3"
final="$4"
shift 4
if ! control=$("$verdict" --expect nothing "$budget" "$firm" "$firm" 2>&1); then
  echo "crossing_verdict.sh: the control failed: the first pass against itself must do nothing" >&2
  printf '%s\n' "$control" >&2
  exit 1
fi
exec "$verdict" "$@" "$budget" "$firm" "$final"
