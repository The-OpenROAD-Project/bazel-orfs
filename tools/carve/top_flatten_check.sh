#!/bin/sh
# crossing_cones' flatten mode on the toy's top level
# (top_flatten_check.tcl, which stops on a broken rule): some cells
# movable, and combinational logic and registers left fixed. Usage:
#   top_flatten_check.sh <flatten.txt>
set -e
count() {
  sed -n "s/^$1 //p" "$2"
}
for key in crossing_nets movable unrouted_nets fixed_logic fixed_stops fixed_nets; do
  n=$(count "$key" "$1")
  if [ -z "$n" ] || [ "$n" -le 0 ]; then
    echo "top_flatten_check: $key is '$n', expected more than 0" >&2
    exit 1
  fi
done
cat "$1"
