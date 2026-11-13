#!/bin/sh
# The macros nested in the parent or a block that the Top dissolved, on
# the toy's first pass (dissolve_nested_check.tcl, which stops on a broken
# rule and on a control that does not stop for its reason): each master's
# cells all where its own flow placed them, moved together by less than a
# site across and at most a row up or down onto the Top's rows, none off
# the rows or turned over, every supply pin on the Top's power grid, every
# register of its database dissolved and clocked by the Top's clock tree;
# mirrored MX, MY and R180, its cells as well placed and on the rows; and
# every control, one or two for each stop from FLW 140 to FLW 147, stopped
# with its id. Usage:
#   dissolve_nested_check.sh <nested.txt>
set -e
value() {
  sed -n "s/^$1 //p" "$2"
}
fail() {
  echo "dissolve_nested_check: $1" >&2
  exit 1
}
number() {
  case "$1" in
  '' | *[!0-9]*) return 1 ;;
  esac
}
masters=$(value nested "$1")
[ -n "$masters" ] || fail "no nested macro checked"
for m in $masters; do
  cells=$(value "$m.cells" "$1")
  placed=$(value "$m.where_placed" "$1")
  registers=$(value "$m.registers" "$1")
  number "$cells" && [ "$cells" -gt 0 ] || fail "$m: cells is '$cells', expected more than 0"
  [ "$placed" = "$cells" ] || fail "$m: $placed of $cells cells where its flow placed them"
  number "$registers" && [ "$registers" -gt 0 ] || fail "$m: registers is '$registers'"
  for key in database_registers clocked clocked_by_the_top_tree; do
    got=$(value "$m.$key" "$1")
    [ "$got" = "$registers" ] || fail "$m: $key is '$got', expected $registers, its registers"
  done
  for key in elsewhere missing off_grid flipped supply_pins_off_the_grid; do
    got=$(value "$m.$key" "$1")
    [ "$got" = 0 ] || fail "$m: $key is '$got', expected 0"
  done
  drivers=$(value "$m.tree_drivers" "$1")
  number "$drivers" && [ "$drivers" -gt 0 ] || fail "$m: tree_drivers is '$drivers'"
done
for o in MX MY R180; do
  cells=$(value "probe_$o.cells" "$1")
  number "$cells" && [ "$cells" -gt 0 ] || fail "probe_$o: cells is '$cells', expected more than 0"
  [ "$(value "probe_$o.where_placed" "$1")" = "$cells" ] || fail "probe_$o: not every cell where its flow placed it"
  for key in off_grid flipped; do
    got=$(value "probe_$o.$key" "$1")
    [ "$got" = 0 ] || fail "probe_$o: $key is '$got', expected 0"
  done
done
while read -r key id; do
  got=$(value "$key" "$1")
  [ "$got" = "$id" ] || fail "$key is '$got', expected the control to stop with $id"
done <<CONTROLS
control_absent FLW-0141
control_odb FLW-0140
control_no_clock FLW-0142
control_off_row FLW-0144
control_flipped FLW-0144
control_unplaced FLW-0143
control_fewer FLW-0145
control_unclocked FLW-0146
control_supply FLW-0147
CONTROLS
cat "$1"
