#!/bin/sh
# What the Top's second pass unfirms, on the toy's floorplan
# (unfirm_check.tcl, which stops on a broken rule and on a control that
# does not stop for its reason): some cells unfirmed, registers and logic
# among them, some left firm, routes dropped, and every control stopped
# with its id. Usage:
#   unfirm_check.sh <unfirm.txt>
set -e
count() {
  sed -n "s/^$1 //p" "$2"
}
for key in unfirmed unfirmed_registers unfirmed_logic left_firm lost_route_nets; do
  n=$(count "$key" "$1")
  case "$n" in
  '' | *[!0-9]* | 0)
    echo "unfirm_check: $key is '$n', expected more than 0" >&2
    exit 1
    ;;
  esac
done
while read -r key id; do
  got=$(count "$key" "$1")
  if [ "$got" != "$id" ]; then
    echo "unfirm_check: $key is '$got', expected the control to stop with $id" >&2
    exit 1
  fi
done <<CONTROLS
control_1_rules FLW-0132
control_2_side FLW-0133
control_2_deep FLW-0133
control_3_extra FLW-0132
control_3_kept FLW-0132
control_4_routability FLW-0134
control_4_timing FLW-0134
control_4_moved FLW-0134
control_5_missing FLW-0130
control_5_empty FLW-0130
control_6_unrouted FLW-0135
CONTROLS
cat "$1"
